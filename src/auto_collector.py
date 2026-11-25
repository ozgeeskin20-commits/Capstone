"""
Automatic EPDK Data Acquisition Module.

Provides transparent snapshot management for the dashboard:
- Checks for existing recent snapshots in local storage.
- Automatically runs a collection cycle when data is stale or missing.
- Prevents duplicate API calls via session-state caching and collector locks.
- Converts timestamps to Europe/Istanbul for user-facing display.

This module bridges the collector subsystem with the Streamlit dashboard,
ensuring the dashboard opens with current data without user interaction.
"""

import json
import os
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from src.collector.api_client import EPDKApiClient
from src.collector.validator import CollectorValidator
from src.collector.storage import LocalStorageAdapter
from src.collector.collector_service import CollectorService
from src.data_loader import load_dataset


# Default freshness threshold: 24 hours
DEFAULT_FRESHNESS_HOURS = 24

# Istanbul timezone offset (UTC+3)
try:
    from zoneinfo import ZoneInfo
    TZ_ISTANBUL = ZoneInfo("Europe/Istanbul")
except ImportError:
    TZ_ISTANBUL = timezone(timedelta(hours=3))


@dataclass
class AutoCollectionResult:
    """Result of an automatic data acquisition attempt."""
    success: bool
    source: str  # "cache", "existing_snapshot", "fresh_collection", "error"
    manifest: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    is_stale: bool = False
    collection_report: Optional[Dict[str, Any]] = None


def get_local_data_dir() -> Path:
    """Returns the local data directory path."""
    base_dir = Path(__file__).resolve().parent.parent
    return Path(os.getenv("LOCAL_DATA_DIR", base_dir / "_local_data"))


def parse_manifest_timestamp(manifest: Dict[str, Any]) -> Optional[datetime]:
    """Parses the timestamp_utc field from a manifest into a timezone-aware datetime."""
    ts_str = manifest.get("timestamp_utc") or manifest.get("snapshot_timestamp")
    if not ts_str:
        return None
    try:
        # Handle ISO format with or without timezone
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def format_timestamp_istanbul(dt: datetime) -> str:
    """Formats a datetime in Europe/Istanbul timezone for display."""
    istanbul_dt = dt.astimezone(TZ_ISTANBUL)
    return istanbul_dt.strftime("%d.%m.%Y %H:%M:%S")


def is_snapshot_fresh(manifest: Dict[str, Any], max_age_hours: float = DEFAULT_FRESHNESS_HOURS) -> bool:
    """Checks whether a manifest's snapshot is within the freshness threshold."""
    ts = parse_manifest_timestamp(manifest)
    if ts is None:
        return False
    now = datetime.now(timezone.utc)
    age = now - ts
    return age < timedelta(hours=max_age_hours)


def load_snapshot_from_manifest(manifest: Dict[str, Any], data_dir: Path) -> Tuple[Optional[Any], Optional[str]]:
    """
    Loads the DataFrame from a manifest's storage_path.
    Returns (df, error_message).
    """
    storage_path = manifest.get("storage_path")
    if not storage_path:
        return None, "Manifest'te storage_path alanı bulunamadı."

    target = Path(storage_path)
    if not target.is_absolute():
        target = data_dir / target

    if not target.exists():
        # Try just the filename in data_dir
        filename = manifest.get("filename")
        if filename:
            target = data_dir / filename
        if not target.exists():
            return None, f"Anlık görüntü dosyası bulunamadı: {target}"

    try:
        df, mappings = load_dataset(target, filename_hint=target.name)
        return df, None
    except Exception as e:
        return None, f"Veri yükleme hatası: {e}"


def run_auto_collection(
    data_dir: Optional[Path] = None,
    freshness_hours: float = DEFAULT_FRESHNESS_HOURS,
    force_refresh: bool = False,
) -> AutoCollectionResult:
    """
    Automatic data acquisition pipeline:
    1. Check existing manifest for a fresh snapshot.
    2. If stale or missing (or force_refresh), run a live collection cycle.
    3. Return the result with manifest metadata.

    The caller is responsible for session-state caching to avoid re-runs on Streamlit rerenders.
    """
    if data_dir is None:
        data_dir = get_local_data_dir()

    storage = LocalStorageAdapter(base_dir=data_dir)

    # 1. Check existing manifest
    if not force_refresh:
        try:
            existing_manifest = storage.get_latest_manifest()
        except Exception:
            existing_manifest = None

        if existing_manifest and existing_manifest.get("status") == "success":
            if is_snapshot_fresh(existing_manifest, freshness_hours):
                return AutoCollectionResult(
                    success=True,
                    source="existing_snapshot",
                    manifest=existing_manifest,
                    is_stale=False,
                )
            else:
                # Existing but stale — will try to refresh
                pass

    # 2. Enable collection for this process
    os.environ["EPDK_COLLECTION_ENABLED"] = "true"

    # 3. Run collection
    try:
        api_client = EPDKApiClient()
        validator = CollectorValidator(
            min_stations_threshold=int(os.getenv("MIN_STATIONS_THRESHOLD", "50"))
        )
        service = CollectorService(
            api_client=api_client,
            validator=validator,
            storage=storage,
        )

        report = service.run_collection()
        status = report.get("status")

        if status == "success":
            # Read the updated manifest
            updated_manifest = storage.get_latest_manifest()
            return AutoCollectionResult(
                success=True,
                source="fresh_collection",
                manifest=updated_manifest or report,
                is_stale=False,
                collection_report=report,
            )
        elif status == "skipped":
            # Another process is collecting — try to use existing data
            try:
                existing = storage.get_latest_manifest()
            except Exception:
                existing = None
            if existing and existing.get("status") == "success":
                return AutoCollectionResult(
                    success=True,
                    source="existing_snapshot",
                    manifest=existing,
                    is_stale=not is_snapshot_fresh(existing, freshness_hours),
                    collection_report=report,
                )
            return AutoCollectionResult(
                success=False,
                source="error",
                error_message="Başka bir toplama işlemi devam ediyor ve mevcut veri bulunamadı.",
                collection_report=report,
            )
        else:
            # Collection failed — try to fall back to existing stale data
            try:
                existing = storage.get_latest_manifest()
            except Exception:
                existing = None
            if existing and existing.get("status") == "success":
                return AutoCollectionResult(
                    success=True,
                    source="existing_snapshot",
                    manifest=existing,
                    is_stale=True,
                    collection_report=report,
                )
            error_detail = report.get("details", {}).get("error", "Bilinmeyen hata")
            stage = report.get("stage", "bilinmiyor")
            return AutoCollectionResult(
                success=False,
                source="error",
                error_message=f"EPDK veri toplama başarısız ({stage}): {error_detail}",
                collection_report=report,
            )

    except Exception as e:
        # Network/system error — try existing data
        try:
            existing = storage.get_latest_manifest()
        except Exception:
            existing = None
        if existing and existing.get("status") == "success":
            return AutoCollectionResult(
                success=True,
                source="existing_snapshot",
                manifest=existing,
                is_stale=True,
                error_message=f"Bağlantı hatası: {e}",
            )
        return AutoCollectionResult(
            success=False,
            source="error",
            error_message=f"EPDK API bağlantı hatası: {e}",
        )
