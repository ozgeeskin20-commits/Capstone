"""
EPDK Collector Orchestration Service.
Coordinates API fetching, validation, immutable storage, read-back verification,
manifest promotion, and exclusive atomic locking.
"""

from datetime import datetime, timezone
import hashlib
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from src.collector.api_client import EPDKApiClient
from src.collector.validator import CollectorValidator
from src.collector.storage import StorageAdapter, LocalStorageAdapter


class CollectorService:
    """Orchestrates daily EPDK snapshots collection, verification, and atomic promotion."""

    def __init__(
        self,
        api_client: Optional[EPDKApiClient] = None,
        validator: Optional[CollectorValidator] = None,
        storage: Optional[StorageAdapter] = None,
        lock_file_path: Optional[Path] = None,
    ):
        self.api_client = api_client or EPDKApiClient()
        self.validator = validator or CollectorValidator()
        self.storage = storage or LocalStorageAdapter()
        
        default_lock = Path(__file__).resolve().parent.parent.parent / "_local_data" / ".collector.lock"
        self.lock_file = lock_file_path or default_lock
        self._held_token: Optional[str] = None

    def _acquire_lock(self) -> bool:
        """
        Atomically acquires an exclusive lock using OS-level create-only semantics ('x' mode).
        Stores an execution-specific token to prevent accidental cross-process release.
        """
        try:
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Check for stale lock (> 30 minutes)
            if self.lock_file.exists():
                try:
                    mtime = self.lock_file.stat().st_mtime
                    import time
                    if time.time() - mtime > 1800:
                        self.lock_file.unlink(missing_ok=True)
                except Exception:
                    pass

            token = f"pid={os.getpid()}_uuid={uuid.uuid4().hex}"
            # Atomic exclusive file creation
            with open(self.lock_file, "x", encoding="utf-8") as f:
                f.write(token)
            self._held_token = token
            return True
        except FileExistsError:
            return False
        except Exception:
            return False

    def _release_lock(self) -> None:
        """Releases the lock ONLY if owned by this execution instance."""
        if not self._held_token:
            return
        try:
            if self.lock_file.exists():
                content = self.lock_file.read_text(encoding="utf-8").strip()
                if content == self._held_token:
                    self.lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        finally:
            self._held_token = None

    def run_collection(self) -> Dict[str, Any]:
        """
        Executes a single collection cycle with read-back verification and atomic promotion.
        Returns detailed sanitized report dictionary.
        """
        now_dt = datetime.now(timezone.utc)
        # Collision-resistant snapshot identifier
        snapshot_id = f"{now_dt.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        timestamp_utc = now_dt.isoformat()

        # 1. Exclusive concurrency lock
        if not self._acquire_lock():
            report = {
                "status": "skipped",
                "reason": "Another collector execution is currently active (exclusive lock held).",
                "timestamp_utc": timestamp_utc
            }
            return report

        try:
            # 2. Fetch data from EPDK API
            fetch_result = self.api_client.fetch()
            if not fetch_result.is_success:
                failure_entry = {
                    "snapshot_id": snapshot_id,
                    "timestamp_utc": timestamp_utc,
                    "status_code": fetch_result.status_code,
                    "duration_seconds": round(fetch_result.duration_seconds, 2),
                    "error": fetch_result.error_message or f"HTTP {fetch_result.status_code}",
                    "stage": "http_fetch",
                }
                self.storage.record_failure(failure_entry)
                return {
                    "status": "failed",
                    "stage": "http_fetch",
                    "details": failure_entry
                }

            # 3. Validate structural integrity and completeness
            validation = self.validator.validate_payload(fetch_result.content)
            if not validation.is_structurally_valid:
                failure_entry = {
                    "snapshot_id": snapshot_id,
                    "timestamp_utc": timestamp_utc,
                    "status_code": fetch_result.status_code,
                    "duration_seconds": round(fetch_result.duration_seconds, 2),
                    "error": validation.fatal_error,
                    "station_count": validation.station_count,
                    "stage": "validation",
                }
                self.storage.record_failure(failure_entry)
                return {
                    "status": "failed",
                    "stage": "validation",
                    "details": failure_entry
                }

            # Canonical SHA-256 of uncompressed bytes
            original_sha256 = hashlib.sha256(fetch_result.content).hexdigest()
            original_byte_len = len(fetch_result.content)

            # 4. Prepare metadata
            metadata = {
                "snapshot_id": snapshot_id,
                "timestamp_utc": timestamp_utc,
                "endpoint_url": self.api_client.endpoint_url,
                "status": "success",
                "sha256_hash": original_sha256,
                "station_count": validation.station_count,
                "socket_count": validation.socket_count,
                "warnings": validation.warnings,
                "fetch_duration_seconds": round(fetch_result.duration_seconds, 2),
            }

            # 5. Persist snapshot and metadata in create-only mode
            try:
                storage_path = self.storage.save_snapshot(snapshot_id, fetch_result.content, metadata)
            except Exception as ex:
                failure_entry = {
                    "snapshot_id": snapshot_id,
                    "timestamp_utc": timestamp_utc,
                    "error": f"Storage save failure: {type(ex).__name__}: {ex}",
                    "stage": "storage_save",
                }
                self.storage.record_failure(failure_entry)
                return {
                    "status": "failed",
                    "stage": "storage_save",
                    "details": failure_entry
                }

            # 6. Read-back verification before manifest promotion
            try:
                read_back_bytes = self.storage.get_snapshot_bytes(storage_path)
                read_back_sha = hashlib.sha256(read_back_bytes).hexdigest()
                read_back_len = len(read_back_bytes)

                if read_back_sha != original_sha256 or read_back_len != original_byte_len:
                    failure_entry = {
                        "snapshot_id": snapshot_id,
                        "timestamp_utc": timestamp_utc,
                        "error": (
                            f"Stored snapshot verification failed: checksum mismatch "
                            f"(original={original_sha256[:12]}, stored={read_back_sha[:12]})"
                        ),
                        "stage": "read_back_verification",
                    }
                    self.storage.record_failure(failure_entry)
                    return {
                        "status": "failed",
                        "stage": "read_back_verification",
                        "details": failure_entry
                    }
            except Exception as ex:
                failure_entry = {
                    "snapshot_id": snapshot_id,
                    "timestamp_utc": timestamp_utc,
                    "error": f"Failed reading back stored snapshot for verification: {ex}",
                    "stage": "read_back_verification",
                }
                self.storage.record_failure(failure_entry)
                return {
                    "status": "failed",
                    "stage": "read_back_verification",
                    "details": failure_entry
                }

            # 7. Promote to latest manifest ONLY after read-back verification passes
            manifest = {
                "snapshot_id": snapshot_id,
                "timestamp_utc": timestamp_utc,
                "snapshot_timestamp": timestamp_utc,
                "filename": metadata["filename"],
                "sha256_hash": original_sha256,
                "raw_byte_size": original_byte_len,
                "compressed_byte_size": metadata.get("compressed_byte_size", 0),
                "station_count": validation.station_count,
                "socket_count": validation.socket_count,
                "storage_path": storage_path,
                "status": "success",
            }
            manifest_ok = self.storage.update_latest_manifest(manifest)
            if not manifest_ok:
                failure_entry = {
                    "snapshot_id": snapshot_id,
                    "timestamp_utc": timestamp_utc,
                    "error": "Manifest update rejected (older execution cannot replace newer manifest, or storage write failed).",
                    "stage": "manifest_promotion",
                }
                self.storage.record_failure(failure_entry)
                return {
                    "status": "failed",
                    "stage": "manifest_promotion",
                    "details": failure_entry
                }

            return {
                "status": "success",
                "snapshot_id": snapshot_id,
                "timestamp_utc": timestamp_utc,
                "storage_path": storage_path,
                "sha256_hash": original_sha256,
                "station_count": validation.station_count,
                "socket_count": validation.socket_count,
                "warnings": validation.warnings,
            }

        finally:
            self._release_lock()
