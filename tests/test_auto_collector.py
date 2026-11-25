"""
Unit tests for the Auto-Collector module (src/auto_collector.py).
Verifies freshness checks, timestamp parsing, fallback to stale snapshots,
and session-state friendly auto-collection lifecycle.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from src.auto_collector import (
    parse_manifest_timestamp,
    format_timestamp_istanbul,
    is_snapshot_fresh,
    load_snapshot_from_manifest,
    run_auto_collection,
    DEFAULT_FRESHNESS_HOURS,
)
from src.collector.storage import LocalStorageAdapter


def test_parse_manifest_timestamp_formats():
    # ISO format with Z
    m1 = {"timestamp_utc": "2026-11-24T10:00:00Z"}
    dt1 = parse_manifest_timestamp(m1)
    assert dt1 is not None
    assert dt1.tzinfo is not None

    # ISO format with offset
    m2 = {"timestamp_utc": "2026-11-24T10:00:00+00:00"}
    dt2 = parse_manifest_timestamp(m2)
    assert dt2 is not None

    # snapshot_timestamp fallback
    m3 = {"snapshot_timestamp": "2026-10-30T08:27:29.644664+00:00"}
    dt3 = parse_manifest_timestamp(m3)
    assert dt3 is not None

    # Missing or invalid
    assert parse_manifest_timestamp({}) is None
    assert parse_manifest_timestamp({"timestamp_utc": "invalid"}) is None


def test_format_timestamp_istanbul():
    # UTC 10:00:00 -> Istanbul 13:00:00 (+03:00)
    dt = datetime(2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc)
    formatted = format_timestamp_istanbul(dt)
    assert "24.11.2026 13:00:00" in formatted


def test_is_snapshot_fresh():
    now = datetime.now(timezone.utc)

    # Fresh snapshot (1 hour old)
    fresh_ts = (now - timedelta(hours=1)).isoformat()
    assert is_snapshot_fresh({"timestamp_utc": fresh_ts}, max_age_hours=24) is True

    # Stale snapshot (25 hours old)
    stale_ts = (now - timedelta(hours=25)).isoformat()
    assert is_snapshot_fresh({"timestamp_utc": stale_ts}, max_age_hours=24) is False

    # Historical snapshot (e.g., 30 October 2026)
    historical = {"timestamp_utc": "2026-10-30T08:27:29+00:00"}
    assert is_snapshot_fresh(historical, max_age_hours=24) is False


def test_auto_collection_returns_existing_fresh_manifest(tmp_path):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    now = datetime.now(timezone.utc)
    fresh_manifest = {
        "snapshot_id": "test_fresh_123",
        "timestamp_utc": now.isoformat(),
        "status": "success",
        "station_count": 100,
        "socket_count": 300,
        "filename": "epdk_raw_test.json.gz",
        "storage_path": str(tmp_path / "epdk_raw_test.json.gz"),
    }
    storage.update_latest_manifest(fresh_manifest)

    # Call run_auto_collection with mock tmp_path
    result = run_auto_collection(data_dir=tmp_path, freshness_hours=24, force_refresh=False)
    assert result.success is True
    assert result.source == "existing_snapshot"
    assert result.is_stale is False
    assert result.manifest["snapshot_id"] == "test_fresh_123"


def test_auto_collection_falls_back_to_stale_when_collection_fails(tmp_path, monkeypatch):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    stale_manifest = {
        "snapshot_id": "test_stale_123",
        "timestamp_utc": "2026-10-30T08:27:29+00:00",
        "status": "success",
        "station_count": 50,
        "socket_count": 120,
        "filename": "epdk_raw_stale.json.gz",
        "storage_path": str(tmp_path / "epdk_raw_stale.json.gz"),
    }
    storage.update_latest_manifest(stale_manifest)

    # Make CollectorService fail
    from src.collector.collector_service import CollectorService
    def mock_run_collection(self):
        return {
            "status": "failed",
            "stage": "http_fetch",
            "details": {"error": "Connection refused"}
        }

    monkeypatch.setattr(CollectorService, "run_collection", mock_run_collection)

    result = run_auto_collection(data_dir=tmp_path, freshness_hours=24, force_refresh=False)
    assert result.success is True
    assert result.source == "existing_snapshot"
    assert result.is_stale is True
    assert result.manifest["snapshot_id"] == "test_stale_123"
