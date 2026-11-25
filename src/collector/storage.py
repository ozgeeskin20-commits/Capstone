"""
Collector Storage Adapters Module.
Provides pluggable storage backends for immutable compressed snapshot persistence:
- LocalStorageAdapter: Local filesystem storage with create-only writes, atomic manifest update,
  monotonic timestamp protection, and failure logging.
- S3StorageAdapter: Configurable S3-compatible private object storage (AWS S3, Cloudflare R2, MinIO).
"""

import abc
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


class StorageAdapter(abc.ABC):
    """Abstract interface for snapshot persistence and manifest operations."""

    @abc.abstractmethod
    def save_snapshot(self, snapshot_id: str, raw_bytes: bytes, metadata: Dict[str, Any]) -> str:
        """Compresses and saves snapshot in create-only mode. Returns storage location."""
        pass

    @abc.abstractmethod
    def update_latest_manifest(self, manifest: Dict[str, Any]) -> bool:
        """Atomically updates latest_manifest.json with monotonic timestamp protection."""
        pass

    @abc.abstractmethod
    def get_latest_manifest(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest verified snapshot manifest."""
        pass

    @abc.abstractmethod
    def get_snapshot_bytes(self, storage_path: str) -> bytes:
        """Retrieves and decompresses snapshot bytes for read-back verification."""
        pass

    @abc.abstractmethod
    def record_failure(self, failure_info: Dict[str, Any]) -> None:
        """Records sanitized failure event without corrupting latest successful manifest."""
        pass


class LocalStorageAdapter(StorageAdapter):
    """Local filesystem storage adapter with create-only semantics."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir is None:
            default_dir = Path(__file__).resolve().parent.parent.parent / "_local_data"
            base_dir = Path(os.getenv("LOCAL_DATA_DIR", default_dir))
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.base_dir / "latest_manifest.json"
        self.failure_log_path = self.base_dir / "collector_failure_log.jsonl"

    def save_snapshot(self, snapshot_id: str, raw_bytes: bytes, metadata: Dict[str, Any]) -> str:
        # Calculate SHA-256 on raw uncompressed canonical bytes
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        metadata["sha256_hash"] = sha256_hash
        metadata["raw_byte_size"] = len(raw_bytes)

        # 1. Compress with gzip without modifying original values
        compressed_bytes = gzip.compress(raw_bytes, compresslevel=6)
        metadata["compressed_byte_size"] = len(compressed_bytes)

        filename = f"epdk_raw_{snapshot_id}.json.gz"
        target_path = self.base_dir / filename

        # Create-only write: prevent snapshot overwrites
        if target_path.exists():
            raise FileExistsError(f"Snapshot file already exists (overwrite prevented): {target_path}")

        try:
            with open(target_path, "xb") as f:
                f.write(compressed_bytes)
        except FileExistsError:
            raise FileExistsError(f"Snapshot collision: file already exists: {target_path}")

        # 2. Save individual immutable metadata (create-only)
        metadata["filename"] = filename
        metadata["storage_path"] = str(target_path)
        meta_filename = f"epdk_meta_{snapshot_id}.json"
        meta_target = self.base_dir / meta_filename

        try:
            with open(meta_target, "x", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except FileExistsError:
            # Clean up snapshot file if metadata write collides
            target_path.unlink(missing_ok=True)
            raise FileExistsError(f"Metadata collision: file already exists: {meta_target}")

        return str(target_path)

    def update_latest_manifest(self, manifest: Dict[str, Any]) -> bool:
        # Monotonic timestamp check: prevent older execution from replacing newer manifest
        new_ts = manifest.get("timestamp_utc", "")
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    current_manifest = json.load(f)
                current_ts = current_manifest.get("timestamp_utc", "")
                if current_ts and new_ts and current_ts > new_ts:
                    # Current manifest is newer than this candidate; reject regression
                    return False
            except Exception:
                pass

        temp_manifest = self.base_dir / "latest_manifest.json.tmp"
        try:
            with open(temp_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            temp_manifest.replace(self.manifest_path)
            return True
        except Exception:
            temp_manifest.unlink(missing_ok=True)
            return False

    def get_latest_manifest(self) -> Optional[Dict[str, Any]]:
        if not self.manifest_path.exists():
            return None
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError(f"Manifest root must be a JSON object (dict), found {type(data).__name__}")
                return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed manifest JSON at {self.manifest_path}: {e}") from e
        except PermissionError:
            raise
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise RuntimeError(f"Error reading manifest at {self.manifest_path}: {e}") from e

    def get_snapshot_bytes(self, storage_path: str) -> bytes:
        p = Path(storage_path)
        if not p.is_absolute():
            p = self.base_dir / p
        with open(p, "rb") as f:
            data = f.read()
        # Decompress if gzipped
        if data.startswith(b"\x1f\x8b"):
            return gzip.decompress(data)
        return data

    def record_failure(self, failure_info: Dict[str, Any]) -> None:
        # Sanitize failure entry to ensure no payloads or credentials leak
        sanitized = {
            k: v for k, v in failure_info.items()
            if k in ("snapshot_id", "timestamp_utc", "status_code", "duration_seconds", "error", "stage", "station_count")
        }
        with open(self.failure_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(sanitized, ensure_ascii=False) + "\n")


def _is_precondition_failed(ex: Exception) -> bool:
    """Checks whether an exception represents an S3 PreconditionFailed (412) error."""
    if hasattr(ex, "response") and isinstance(ex.response, dict):
        err_code = ex.response.get("Error", {}).get("Code", "")
        status = ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if err_code in ("PreconditionFailed", "412") or status == 412:
            return True
    err_str = str(ex).lower()
    return "preconditionfailed" in err_str or "precondition failed" in err_str or "412" in err_str


def _is_not_found(ex: Exception) -> bool:
    """Checks whether an exception represents a genuine S3 NoSuchKey / 404 Not Found error."""
    if hasattr(ex, "response") and isinstance(ex.response, dict):
        err_code = ex.response.get("Error", {}).get("Code", "")
        status = ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if err_code in ("NoSuchKey", "NotFound", "404") or status == 404:
            return True
        return False
    err_str = str(ex).lower()
    return "nosuchkey" in err_str or "not found" in err_str or "404" in err_str


def _is_permission_error(ex: Exception) -> bool:
    """Checks whether an exception represents an S3 AccessDenied / 403 Forbidden error."""
    if hasattr(ex, "response") and isinstance(ex.response, dict):
        err_code = ex.response.get("Error", {}).get("Code", "")
        status = ex.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if err_code in ("AccessDenied", "Forbidden", "403") or status == 403:
            return True
        return False
    err_str = str(ex).lower()
    return "accessdenied" in err_str or "forbidden" in err_str or "403" in err_str


class S3StorageAdapter(StorageAdapter):
    """
    S3-compatible Object Storage Adapter.
    Configurable for AWS S3, Cloudflare R2, MinIO, or Ceph.
    Enforces atomic conditional writes using IfNoneMatch="*" and IfMatch=<etag>.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region_name: Optional[str] = None,
        prefix: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        self.bucket_name = bucket_name or os.getenv("S3_BUCKET_NAME")
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
        self.access_key_id = access_key_id or os.getenv("S3_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.getenv("S3_SECRET_ACCESS_KEY")
        self.region_name = region_name or os.getenv("S3_REGION_NAME", "auto")
        self.prefix = (prefix or os.getenv("S3_PREFIX", "epdk/")).rstrip("/") + "/"

        self._injected_client = client
        self._client = None

    def _get_client(self):
        if self._injected_client is not None:
            return self._injected_client
        if self._client is not None:
            return self._client

        if not (self.bucket_name and self.access_key_id and self.secret_access_key):
            raise ValueError(
                "S3 configuration is missing. Required environment variables: "
                "S3_BUCKET_NAME, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY"
            )

        try:
            import boto3
            client_kwargs = {
                "service_name": "s3",
                "aws_access_key_id": self.access_key_id,
                "aws_secret_access_key": self.secret_access_key,
                "region_name": self.region_name,
            }
            if self.endpoint_url:
                client_kwargs["endpoint_url"] = self.endpoint_url
            self._client = boto3.client(**client_kwargs)
            return self._client
        except ImportError:
            raise ImportError(
                "boto3 package is required for S3StorageAdapter. Install with: pip install boto3"
            )

    def save_snapshot(self, snapshot_id: str, raw_bytes: bytes, metadata: Dict[str, Any]) -> str:
        client = self._get_client()
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        metadata["sha256_hash"] = sha256_hash
        metadata["raw_byte_size"] = len(raw_bytes)

        # Compress
        compressed = gzip.compress(raw_bytes, compresslevel=6)
        metadata["compressed_byte_size"] = len(compressed)

        filename = f"epdk_raw_{snapshot_id}.json.gz"
        s3_key = f"{self.prefix}snapshots/{filename}"
        metadata["filename"] = filename
        metadata["storage_path"] = s3_key

        # 1. Atomic conditional write for snapshot: IfNoneMatch="*"
        try:
            client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=compressed,
                ContentType="application/gzip",
                Metadata={"sha256": sha256_hash},
                IfNoneMatch="*"
            )
        except Exception as ex:
            if _is_precondition_failed(ex):
                raise FileExistsError(f"S3 snapshot collision (atomic IfNoneMatch failed): {s3_key}") from ex
            raise

        # 2. Atomic conditional write for snapshot-specific metadata: IfNoneMatch="*"
        meta_key = f"{self.prefix}snapshots/epdk_meta_{snapshot_id}.json"
        meta_bytes = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            client.put_object(
                Bucket=self.bucket_name,
                Key=meta_key,
                Body=meta_bytes,
                ContentType="application/json",
                IfNoneMatch="*"
            )
        except Exception as ex:
            if _is_precondition_failed(ex):
                raise FileExistsError(f"S3 metadata collision (atomic IfNoneMatch failed): {meta_key}") from ex
            raise

        return s3_key

    def get_manifest_with_etag(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Retrieves the latest verified snapshot manifest and its ETag.
        Returns:
            (manifest_dict, etag) if found.
            (None, None) ONLY if object genuinely does not exist (NoSuchKey / 404).
        Raises:
            PermissionError: on access denied / forbidden.
            ValueError: on malformed JSON payload.
            Exception: on timeouts, network or server errors.
        """
        client = self._get_client()
        manifest_key = f"{self.prefix}latest_manifest.json"
        try:
            resp = client.get_object(Bucket=self.bucket_name, Key=manifest_key)
        except Exception as ex:
            if _is_not_found(ex):
                return None, None
            if _is_permission_error(ex):
                raise PermissionError(f"Access denied retrieving S3 manifest at {manifest_key}: {ex}") from ex
            raise

        raw_etag = resp.get("ETag", "")
        etag = raw_etag.strip('"') if raw_etag else None
        body_stream = resp.get("Body")
        body_bytes = body_stream.read() if hasattr(body_stream, "read") else body_stream

        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError(f"Manifest root must be a JSON object (dict), found {type(parsed).__name__}")
            return parsed, etag
        except Exception as e:
            if isinstance(e, ValueError) and "Manifest root" in str(e):
                raise
            raise ValueError(f"Malformed manifest JSON in S3 at {manifest_key}: {e}") from e

    def get_latest_manifest(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the latest verified snapshot manifest.
        Returns None ONLY if object genuinely does not exist.
        Propagates permission errors, server errors, and malformed manifest errors.
        """
        manifest, _ = self.get_manifest_with_etag()
        return manifest

    def update_latest_manifest(self, manifest: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Atomically updates latest_manifest.json using conditional PutObject:
        - If manifest does not exist: uses IfNoneMatch="*" for atomic initial creation.
        - If manifest exists: uses IfMatch=<current_etag> for optimistic concurrency.
        - Compares candidate timestamp vs current timestamp before writing.
        - On 412 PreconditionFailed, performs bounded reread and re-evaluates.
        - NEVER falls back to an unconditional overwrite.
        - Preserves the newer manifest when another writer wins.
        """
        client = self._get_client()
        manifest_key = f"{self.prefix}latest_manifest.json"
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        new_ts = manifest.get("timestamp_utc", "")

        for attempt in range(max_retries):
            # 1. Read current manifest and ETag (only genuinely missing returns None)
            current_manifest, current_etag = self.get_manifest_with_etag()

            # 2. Timestamp check if manifest already exists
            if current_manifest is not None:
                current_ts = current_manifest.get("timestamp_utc", "")
                if current_ts and new_ts and current_ts > new_ts:
                    # Current manifest in S3 is newer than this candidate; reject regression and preserve newer
                    return False
                if not current_etag:
                    raise ValueError(f"Cannot perform atomic update on {manifest_key}: current object lacks ETag")

            # 3. Build conditional put_object kwargs
            put_kwargs = {
                "Bucket": self.bucket_name,
                "Key": manifest_key,
                "Body": manifest_bytes,
                "ContentType": "application/json",
            }

            if current_manifest is None:
                # Initial creation: require that object does NOT exist
                put_kwargs["IfNoneMatch"] = "*"
            else:
                # Existing update: require matching ETag
                put_kwargs["IfMatch"] = f'"{current_etag}"'

            try:
                client.put_object(**put_kwargs)
                return True
            except Exception as ex:
                if _is_precondition_failed(ex):
                    # Precondition conflict: another writer created or updated the manifest concurrently
                    # Bounded reread and re-evaluation in next loop iteration
                    continue
                # For non-precondition errors (permissions, network, timeouts), propagate
                raise

        # Max retries exhausted on precondition conflicts
        # Re-check one final time: if prevailing manifest is newer, preserve it and return False
        try:
            latest_manifest, _ = self.get_manifest_with_etag()
            if latest_manifest:
                latest_ts = latest_manifest.get("timestamp_utc", "")
                if latest_ts and new_ts and latest_ts >= new_ts:
                    return False
        except Exception:
            pass

        return False

    def get_snapshot_bytes(self, storage_path: str) -> bytes:
        client = self._get_client()
        resp = client.get_object(Bucket=self.bucket_name, Key=storage_path)
        body_stream = resp.get("Body")
        data = body_stream.read() if hasattr(body_stream, "read") else body_stream
        if data.startswith(b"\x1f\x8b"):
            return gzip.decompress(data)
        return data

    def record_failure(self, failure_info: Dict[str, Any]) -> None:
        client = self._get_client()
        sanitized = {
            k: v for k, v in failure_info.items()
            if k in ("snapshot_id", "timestamp_utc", "status_code", "duration_seconds", "error", "stage", "station_count")
        }
        ts_id = failure_info.get("timestamp_utc", "unknown").replace(":", "-")
        fail_key = f"{self.prefix}failures/fail_{ts_id}.json"
        try:
            client.put_object(
                Bucket=self.bucket_name,
                Key=fail_key,
                Body=json.dumps(sanitized, ensure_ascii=False, indent=2).encode("utf-8"),
                ContentType="application/json"
            )
        except Exception:
            pass
