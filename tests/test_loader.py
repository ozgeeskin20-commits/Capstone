"""
Unit tests for EPDK Charging Market Data Loader and Normalization Module.
"""

import io
import json
import zipfile
import pytest
import pandas as pd
from src.data_loader import (
    normalize_schema,
    load_from_csv,
    load_from_json,
    load_from_zip,
    load_dataset,
    generate_synthetic_fixture
)


def test_normalize_schema_turkish_aliases():
    df = pd.DataFrame([{
        "istasyon_id": "STN-001",
        "soket_id": "SCK-001",
        "isletmeci": "ZES",
        "soket_tipi": "AC",
        "guc_kw": 22.0
    }])

    norm_df, mappings = normalize_schema(df)

    assert "station_id" in norm_df.columns
    assert "socket_id" in norm_df.columns
    assert "operator_name" in norm_df.columns
    assert "socket_type" in norm_df.columns
    assert "power_kw" in norm_df.columns
    assert mappings["istasyon_id"] == "station_id"
    assert mappings["isletmeci"] == "operator_name"


def test_load_from_csv():
    csv_content = "istasyon_id;soket_id;isletmeci;soket_tipi;guc_kw\nSTN-1;SCK-1;Trugo;DC;180\n"
    bio = io.BytesIO(csv_content.encode("utf-8"))

    df, mappings = load_dataset(bio, filename_hint="test.csv")

    assert len(df) == 1
    assert df["operator_name"].iloc[0] == "Trugo"
    assert float(df["power_kw"].iloc[0]) == 180.0


def test_load_from_json_nested():
    data = {
        "result": [
            {
                "station_id": "STN-10",
                "operator_name": "E-Sarj",
                "sockets": [
                    {"socket_id": "SCK-1", "socket_type": "AC", "power_kw": 22},
                    {"socket_id": "SCK-2", "socket_type": "DC", "power_kw": 120}
                ]
            }
        ]
    }
    bio = io.BytesIO(json.dumps(data).encode("utf-8"))
    df, mappings = load_dataset(bio, filename_hint="test.json")

    assert len(df) == 2
    assert "station_id" in df.columns
    assert df["station_id"].iloc[0] == "STN-10"
    assert df["socket_id"].iloc[1] == "SCK-2"


def test_load_from_zip():
    csv_content = "station_id,socket_id,operator_name,socket_type,power_kw\nSTN-1,SCK-1,Voltrun,AC,22\n"
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as z:
        z.writestr("stations.csv", csv_content)
    zip_buffer.seek(0)

    df, mappings = load_dataset(zip_buffer, filename_hint="archive.zip")
    assert len(df) == 1
    assert df["operator_name"].iloc[0] == "Voltrun"


def test_synthetic_fixture():
    df = generate_synthetic_fixture(num_records=50, seed=123)
    assert len(df) == 50
    assert "station_id" in df.columns
    assert "socket_id" in df.columns
    assert "power_kw" in df.columns
    assert df["socket_id"].nunique() == 50


def test_paired_csv_loading_preserves_stations_without_sockets(tmp_path):
    station_csv = tmp_path / "istasyonlar_test.csv"
    socket_csv = tmp_path / "soketler_test.csv"

    # Station 0 has socket, Station 1 has no socket
    station_content = "_row_id,istasyonId,istasyonAdi,isletmeciAdi\n0,STN-1,Station A,ZES\n1,STN-2,Station B,Trugo\n"
    socket_content = "_row_id,soketNo,soketTipi,soketGucu\n0,SCK-1,AC,22.0\n"

    station_csv.write_text(station_content, encoding="utf-8")
    socket_csv.write_text(socket_content, encoding="utf-8")

    df, mappings = load_dataset(station_csv)

    assert len(df) == 2
    assert set(df["station_id"]) == {"STN-1", "STN-2"}
    # Station 2 should have None socket_id
    stn2_row = df[df["station_id"] == "STN-2"].iloc[0]
    assert pd.isna(stn2_row["socket_id"])

    # Verify metadata shows paired source
    meta = df.attrs.get("metadata", {})
    assert "soketler_test.csv" in meta.get("source_file", "")


def test_station_csv_without_socket_csv_handled_gracefully(tmp_path):
    station_csv = tmp_path / "istasyonlar_only.csv"
    station_content = "_row_id,istasyonId,istasyonAdi,isletmeciAdi\n0,STN-1,Station A,ZES\n"
    station_csv.write_text(station_content, encoding="utf-8")

    df, mappings = load_dataset(station_csv)
    assert len(df) == 1
    assert df.attrs.get("metadata", {}).get("has_socket_data") is False


def test_load_from_gzip_json(tmp_path):
    import gzip
    gz_file = tmp_path / "epdk_raw_20261105_090000.json.gz"
    payload = {
        "data": [
            {
                "sarjIstasyonuNo": "STN-GZ-1",
                "istasyonAdi": "Gz Station",
                "sarjAgiIsletmecisiUnvan": "ZES",
                "soketler": [
                    {"soketNo": "SCK-GZ-1", "soketTipi": "AC", "soketGucu": 22.0}
                ]
            }
        ]
    }
    with gzip.open(gz_file, "wt", encoding="utf-8") as f:
        json.dump(payload, f)

    df, mappings = load_dataset(gz_file)
    assert len(df) == 1
    assert df["station_id"].iloc[0] == "STN-GZ-1"
    assert df["socket_id"].iloc[0] == "SCK-GZ-1"
    assert "content_hash" in df.attrs.get("metadata", {})


def test_snapshot_provenance_binding_with_manifest_and_hash(tmp_path):
    raw_file = tmp_path / "epdk_raw_20261105_120000.json"
    manifest_file = tmp_path / "latest_manifest.json"

    payload = [{"sarjIstasyonuNo": "STN-1", "soketler": []}]
    raw_file.write_text(json.dumps(payload), encoding="utf-8")

    import hashlib
    hasher = hashlib.sha256()
    hasher.update(raw_file.read_bytes())
    h = hasher.hexdigest()

    manifest_data = {
        "snapshot_id": "20261105_120000",
        "filename": "epdk_raw_20261105_120000.json",
        "sha256_hash": h,
        "snapshot_timestamp": "2026-11-05T12:00:00+00:00",
        "record_count": 1,
        "status": "success"
    }
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    df, mappings = load_dataset(raw_file)
    meta = df.attrs.get("metadata", {})
    assert meta.get("snapshot_timestamp") == "2026-11-05T12:00:00+00:00"
    assert meta.get("sha256_hash") == h
    assert meta.get("record_count") == 1


def test_snapshot_provenance_avoids_assigning_newer_attempt_log_entry(tmp_path):
    # Older file from 20261028
    older_file = tmp_path / "epdk_raw_20261028_100000.json"
    older_file.write_text(json.dumps([{"sarjIstasyonuNo": "STN-OLD", "soketler": []}]), encoding="utf-8")

    # attempt_log has two entries: 2026-10-28 and 2026-11-05
    log_file = tmp_path / "attempt_log.jsonl"
    log_file.write_text(
        json.dumps({"status": 200, "ts": "2026-10-28T10:00:00+00:00", "records": 100}) + "\n" +
        json.dumps({"status": 200, "ts": "2026-11-05T10:00:00+00:00", "records": 500}) + "\n",
        encoding="utf-8"
    )

    df, mappings = load_dataset(older_file)
    meta = df.attrs.get("metadata", {})
    # MUST match 2026-10-28, NOT the newer 2026-11-05 entry!
    assert meta.get("snapshot_timestamp") == "2026-10-28T10:00:00+00:00"
    assert meta.get("record_count") == 100
