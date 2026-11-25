"""Tests for the daily archive builder."""

import gzip
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.archive import daily_archive as archive


def make_payload(station_count: int, start: int = 0):
    """Builds an EPDK-shaped payload. Every seventh station has no sockets."""
    records = []
    for index in range(start, start + station_count):
        sockets = [
            {"soketNo": f"{index}-1", "soketTipi": "DC", "soketTuru": "CCS2", "soketGucu": 180},
            {"soketNo": f"{index}-2", "soketTipi": "AC", "soketTuru": "Type 2", "soketGucu": 22},
        ]
        if index % 7 == 0:
            sockets = []
        records.append(
            {
                "sarjIstasyonuNo": str(index),
                "sarjIstasyonuAdi": f"Istasyon {index}",
                "adres": "Mahalle / MELIKGAZI / KAYSERI",
                "sarjAgiIsletmecisiUnvan": f"Operator {index % 3}",
                "sarjAgiIsletmecisiLisansNo": f"L{index % 3}",
                "enlem": 38.7,
                "boylam": 35.5,
                "sarjIstasyonuIsletmecisi": "Gercek Kisi Adi",
                "soketler": sockets,
            }
        )
    return {"data": records}


@pytest.fixture
def archive_env(tmp_path, monkeypatch):
    """Points the archive module at a temporary data directory and output directory."""
    data_dir = tmp_path / "_local_data"
    out_dir = tmp_path / "archive"
    data_dir.mkdir()
    monkeypatch.setattr(archive, "ARCHIVE_DIR", out_dir)
    monkeypatch.setattr(archive, "DAILY_DIR", out_dir / "daily")
    monkeypatch.setattr(archive, "DIM_PATH", out_dir / "stations_dim.csv")
    monkeypatch.setattr(archive, "TOTALS_PATH", out_dir / "daily_totals.csv")
    return data_dir, out_dir


def write_snapshot(data_dir, payload, snapshot_id):
    """Writes a snapshot and manifest the way the collector's local adapter does."""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    filename = f"epdk_raw_{snapshot_id}.json.gz"
    with gzip.open(data_dir / filename, "wb") as handle:
        handle.write(raw)
    manifest = {
        "snapshot_id": snapshot_id,
        "status": "success",
        "filename": filename,
        "storage_path": str(data_dir / filename),
        "sha256_hash": hashlib.sha256(raw).hexdigest(),
        "station_count": len(payload["data"]),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    (data_dir / "latest_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def build_on(data_dir, day):
    return archive.build_archive(data_dir=data_dir, now=datetime(*day, 9, 0, tzinfo=timezone.utc))


def test_archive_date_uses_istanbul_time():
    """A UTC instant late in the day belongs to the next Istanbul day."""
    assert archive.archive_date(datetime(2026, 11, 25, 22, 30, tzinfo=timezone.utc)) == "2026-11-26"


def test_missing_manifest_raises(archive_env):
    data_dir, _ = archive_env
    with pytest.raises(FileNotFoundError):
        archive.build_archive(data_dir=data_dir)


def test_socketless_stations_are_preserved_with_zero_counts(archive_env):
    data_dir, out_dir = archive_env
    write_snapshot(data_dir, make_payload(20), "20261124_090000_aaa")
    result = build_on(data_dir, (2026, 11, 24))

    facts = pd.read_csv(out_dir / "daily" / "2026-11-24.csv.gz", dtype={"station_id": str})
    assert len(facts) == result["totals"]["station_count"] == 20
    assert (facts["socket_count"] == 0).sum() == 3  # stations 0, 7 and 14
    assert facts["socket_count"].sum() == 34


def test_ac_dc_counts_reconcile_with_socket_count(archive_env):
    data_dir, out_dir = archive_env
    write_snapshot(data_dir, make_payload(20), "20261124_090000_aaa")
    build_on(data_dir, (2026, 11, 24))

    totals = pd.read_csv(out_dir / "daily_totals.csv").iloc[0]
    assert totals["ac_socket_count"] + totals["dc_socket_count"] == totals["socket_count"]
    assert totals["total_power_kw"] == pytest.approx(17 * 202.0)


def test_personal_data_field_is_never_written(archive_env):
    """`sarjIstasyonuIsletmecisi` may hold a natural person's name and must not be archived."""
    data_dir, out_dir = archive_env
    write_snapshot(data_dir, make_payload(10), "20261124_090000_aaa")
    build_on(data_dir, (2026, 11, 24))

    dimension = pd.read_csv(out_dir / "stations_dim.csv", dtype=str)
    assert not any("Isletmecisi" in column for column in dimension.columns)
    assert not dimension.apply(lambda col: col.str.contains("Gercek Kisi", na=False).any()).any()


def test_first_seen_is_set_once_and_last_seen_advances(archive_env):
    data_dir, out_dir = archive_env

    write_snapshot(data_dir, make_payload(20), "20261124_090000_aaa")
    build_on(data_dir, (2026, 11, 24))

    write_snapshot(data_dir, make_payload(23), "20261125_090000_bbb")
    result = build_on(data_dir, (2026, 11, 25))

    assert result["new_station_ids_today"] == 3

    dimension = pd.read_csv(out_dir / "stations_dim.csv", dtype={"station_id": str})
    existing = dimension.set_index("station_id").loc["5"]
    assert existing["first_seen"] == "2026-11-24"
    assert existing["last_seen"] == "2026-11-25"

    newcomer = dimension.set_index("station_id").loc["21"]
    assert newcomer["first_seen"] == "2026-11-25"


def test_delisted_station_keeps_its_last_seen(archive_env):
    data_dir, out_dir = archive_env

    write_snapshot(data_dir, make_payload(23), "20261125_090000_bbb")
    build_on(data_dir, (2026, 11, 25))

    write_snapshot(data_dir, make_payload(21), "20261126_090000_ccc")
    build_on(data_dir, (2026, 11, 26))

    dimension = pd.read_csv(out_dir / "stations_dim.csv", dtype={"station_id": str}).set_index("station_id")
    assert len(dimension) == 23
    assert dimension.loc["22", "last_seen"] == "2026-11-25"
    assert dimension.loc["20", "last_seen"] == "2026-11-26"


def test_rerun_on_same_day_replaces_rather_than_duplicates(archive_env):
    data_dir, out_dir = archive_env

    write_snapshot(data_dir, make_payload(20), "20261124_090000_aaa")
    build_on(data_dir, (2026, 11, 24))
    write_snapshot(data_dir, make_payload(22), "20261124_170000_ddd")
    build_on(data_dir, (2026, 11, 24))

    totals = pd.read_csv(out_dir / "daily_totals.csv")
    assert len(totals) == 1
    assert totals.iloc[0]["station_count"] == 22


def test_dimension_is_sorted_to_keep_diffs_small(archive_env):
    data_dir, out_dir = archive_env
    write_snapshot(data_dir, make_payload(30), "20261124_090000_aaa")
    build_on(data_dir, (2026, 11, 24))

    dimension = pd.read_csv(out_dir / "stations_dim.csv", dtype={"station_id": str})
    assert list(dimension["station_id"]) == sorted(dimension["station_id"])
