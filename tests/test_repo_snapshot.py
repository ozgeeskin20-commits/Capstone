"""Tests for the repository snapshot and the dashboard's preference for it."""

import json
from datetime import datetime, timezone, timedelta

import pandas as pd
import pytest

from src.archive import repo_snapshot
from src import auto_collector
from src.data_loader import load_dataset
from src.validator import validate_charging_dataset
from src.metrics import compute_kpis


def make_validated_frame(rows: int = 12) -> pd.DataFrame:
    """Builds a socket-level frame in canonical column names, as the archive holds it."""
    records = []
    for index in range(rows):
        station = f"S{index // 2:03d}"
        records.append(
            {
                "station_id": station,
                "station_name": f"Istasyon {station}",
                "operator_name": f"Operator {index % 3}",
                "operator_license_no": f"L{index % 3}",
                "socket_id": f"{station}-{index}",
                "socket_type": "DC" if index % 2 else "AC",
                "socket_sub_type": "CCS2" if index % 2 else "Type 2",
                "power_kw": 180.0 if index % 2 else 22.0,
                "address": "Mahalle / MELIKGAZI / KAYSERI",
                "_is_valid": True,
                "_validation_errors": [],
            }
        )
    return pd.DataFrame(records)


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "sockets_latest.csv", tmp_path / "manifest.json"


def source_manifest(when: datetime) -> dict:
    return {
        "snapshot_id": "20261125_121851_3d6b2f",
        "timestamp_utc": when.isoformat(),
        "sha256_hash": "78857e95" + "0" * 56,
    }


def test_only_declared_columns_are_written(paths):
    snapshot_path, manifest_path = paths
    repo_snapshot.write_snapshot(
        make_validated_frame(), source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path
    )

    written = pd.read_csv(snapshot_path)
    assert list(written.columns) == repo_snapshot.SNAPSHOT_COLUMNS
    assert "address" not in written.columns
    assert "_validation_errors" not in written.columns


def test_rows_are_sorted_so_daily_revisions_stay_small(paths):
    snapshot_path, manifest_path = paths
    frame = make_validated_frame().sample(frac=1.0, random_state=7)
    repo_snapshot.write_snapshot(frame, source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path)

    written = pd.read_csv(snapshot_path)
    pairs = list(zip(written["station_id"], written["socket_id"]))
    assert pairs == sorted(pairs)


def test_manifest_stores_no_absolute_path_but_read_resolves_one(paths):
    snapshot_path, manifest_path = paths
    repo_snapshot.write_snapshot(
        make_validated_frame(), source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path
    )

    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "storage_path" not in on_disk  # clones live at different paths

    resolved = repo_snapshot.read_manifest(snapshot_path, manifest_path)
    assert resolved["storage_path"] == str(snapshot_path.resolve())
    assert resolved["station_count"] == 6
    assert resolved["socket_count"] == 12


def test_read_manifest_returns_none_when_either_file_is_missing(paths):
    snapshot_path, manifest_path = paths
    assert repo_snapshot.read_manifest(snapshot_path, manifest_path) is None

    repo_snapshot.write_snapshot(
        make_validated_frame(), source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path
    )
    snapshot_path.unlink()
    assert repo_snapshot.read_manifest(snapshot_path, manifest_path) is None


def test_read_manifest_returns_none_on_corrupt_manifest(paths):
    snapshot_path, manifest_path = paths
    repo_snapshot.write_snapshot(
        make_validated_frame(), source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path
    )
    manifest_path.write_text("{ not json", encoding="utf-8")
    assert repo_snapshot.read_manifest(snapshot_path, manifest_path) is None


def test_round_trip_preserves_the_figures_the_dashboard_reports(paths):
    """Reloading the written file through the normal pipeline must yield the same KPIs."""
    snapshot_path, manifest_path = paths
    original = make_validated_frame()
    before, _ = validate_charging_dataset(original.drop(columns=["_is_valid", "_validation_errors"]))
    kpis_before = compute_kpis(before)

    repo_snapshot.write_snapshot(original, source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path)

    reloaded, _ = load_dataset(snapshot_path, filename_hint=snapshot_path.name)
    after, _ = validate_charging_dataset(reloaded)
    kpis_after = compute_kpis(after)

    for key in ("unique_stations", "unique_sockets", "ac_socket_count", "dc_socket_count", "total_socket_power_kw"):
        assert kpis_after[key] == kpis_before[key], key


class ExplodingApiClient:
    """Fails loudly if the collector is reached; used to prove no request was made."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("The endpoint must not be contacted when a fresh snapshot is available.")


def test_fresh_repository_snapshot_is_used_instead_of_calling_the_endpoint(tmp_path, monkeypatch, paths):
    snapshot_path, manifest_path = paths
    repo_snapshot.write_snapshot(
        make_validated_frame(), source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path
    )
    monkeypatch.setattr(repo_snapshot, "SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(repo_snapshot, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(auto_collector, "EPDKApiClient", ExplodingApiClient)

    empty_local_dir = tmp_path / "_local_data"
    empty_local_dir.mkdir()

    result = auto_collector.run_auto_collection(data_dir=empty_local_dir)

    assert result.success is True
    assert result.source == "repository_snapshot"
    assert result.is_stale is False


def test_stale_repository_snapshot_does_not_prevent_a_live_collection(tmp_path, monkeypatch, paths):
    snapshot_path, manifest_path = paths
    stale_moment = datetime.now(timezone.utc) - timedelta(hours=40)
    repo_snapshot.write_snapshot(make_validated_frame(), source_manifest(stale_moment), snapshot_path, manifest_path)
    monkeypatch.setattr(repo_snapshot, "SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(repo_snapshot, "MANIFEST_PATH", manifest_path)

    reached = {"collection": False}

    class RecordingApiClient:
        def __init__(self, *args, **kwargs):
            reached["collection"] = True
            raise RuntimeError("no network in tests")

    monkeypatch.setattr(auto_collector, "EPDKApiClient", RecordingApiClient)

    empty_local_dir = tmp_path / "_local_data"
    empty_local_dir.mkdir()

    result = auto_collector.run_auto_collection(data_dir=empty_local_dir)

    assert reached["collection"] is True
    # Collection failed, so the stale repository snapshot is served with a warning.
    assert result.source == "repository_snapshot"
    assert result.is_stale is True


def test_force_refresh_skips_the_repository_snapshot(tmp_path, monkeypatch, paths):
    snapshot_path, manifest_path = paths
    repo_snapshot.write_snapshot(
        make_validated_frame(), source_manifest(datetime.now(timezone.utc)), snapshot_path, manifest_path
    )
    monkeypatch.setattr(repo_snapshot, "SNAPSHOT_PATH", snapshot_path)
    monkeypatch.setattr(repo_snapshot, "MANIFEST_PATH", manifest_path)

    reached = {"collection": False}

    class RecordingApiClient:
        def __init__(self, *args, **kwargs):
            reached["collection"] = True
            raise RuntimeError("no network in tests")

    monkeypatch.setattr(auto_collector, "EPDKApiClient", RecordingApiClient)

    empty_local_dir = tmp_path / "_local_data"
    empty_local_dir.mkdir()

    auto_collector.run_auto_collection(data_dir=empty_local_dir, force_refresh=True)
    assert reached["collection"] is True
