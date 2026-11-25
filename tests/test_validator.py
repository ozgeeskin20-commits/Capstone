"""
Unit tests for EPDK Charging Market Data Validation Module.
Tests unique station/socket counting, relationship validation, duplicate handling,
stations without sockets, and conflicting AC/DC classifications.
"""

import pytest
import pandas as pd
from src.validator import (
    normalize_ac_dc,
    normalize_power,
    validate_charging_dataset,
    ValidationSummary
)


def test_normalize_ac_dc():
    # Valid AC variants
    val, ok = normalize_ac_dc("AC")
    assert ok and val == "AC"
    val, ok = normalize_ac_dc("Alternatif Akım")
    assert ok and val == "AC"

    # Valid DC variants
    val, ok = normalize_ac_dc("dc")
    assert ok and val == "DC"
    val, ok = normalize_ac_dc("Doğru Akım")
    assert ok and val == "DC"

    # Invalid / Unknown
    val, ok = normalize_ac_dc("HYBRID")
    assert not ok and val == "HYBRID"
    val, ok = normalize_ac_dc(None)
    assert not ok and val is None


def test_normalize_power():
    # Standard numbers
    val, ok = normalize_power(22)
    assert ok and val == 22.0
    val, ok = normalize_power(150.5)
    assert ok and val == 150.5

    # String variants
    val, ok = normalize_power("22 kW")
    assert ok and val == 22.0
    val, ok = normalize_power("22,5")
    assert ok and val == 22.5

    # Invalid: zero, negative, non-numeric, None
    val, ok = normalize_power(0)
    assert not ok and val is None
    val, ok = normalize_power(-50)
    assert not ok and val is None
    val, ok = normalize_power("bilinmiyor")
    assert not ok and val is None
    val, ok = normalize_power(None)
    assert not ok and val is None


def test_unique_station_and_socket_counting():
    """Tests station-socket cardinality: 1 station with 3 sockets."""
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22},
        {"station_id": "STN-1", "socket_id": "SCK-2", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22},
        {"station_id": "STN-1", "socket_id": "SCK-3", "operator_name": "Op A", "socket_type": "DC", "power_kw": 120},
    ])

    annotated, summary = validate_charging_dataset(df)

    assert summary.total_records == 3
    assert summary.unique_stations == 1
    assert summary.stations_with_sockets == 1
    assert summary.stations_without_sockets == 0
    assert summary.unique_sockets == 3
    assert summary.duplicate_socket_ids == 0
    assert summary.valid_socket_records == 3
    assert summary.invalid_socket_records == 0


def test_stations_without_sockets_preservation():
    """Tests preservation of licensed stations that have no sockets."""
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22},
        {"station_id": "STN-EMPTY", "socket_id": None, "operator_name": "Op B", "socket_type": None, "power_kw": None},
    ])

    annotated, summary = validate_charging_dataset(df)

    assert summary.total_records == 2
    assert summary.unique_stations == 2
    assert summary.stations_with_sockets == 1
    assert summary.stations_without_sockets == 1
    assert summary.unique_sockets == 1
    assert summary.valid_socket_records == 1
    assert summary.invalid_socket_records == 1


def test_conflicting_ac_dc_classification():
    """Tests detection of conflicting AC/DC labels (e.g. soketTipi=DC, soketTuru=AC_TYPE2)."""
    df = pd.DataFrame([
        {
            "station_id": "STN-1",
            "socket_id": "SKT-CONFLICT",
            "operator_name": "Op A",
            "socket_type": "DC",
            "socket_sub_type": "AC_TYPE2",
            "power_kw": 22.0
        }
    ])

    annotated, summary = validate_charging_dataset(df)

    assert summary.conflicting_ac_dc_count == 1
    assert summary.valid_socket_records == 0
    assert any("Çelişkili Sınıflandırma" in err for err in annotated["_validation_errors"].iloc[0])
    assert annotated["socket_type_normalized"].iloc[0] == "Çelişkili"


def test_duplicate_socket_detection():
    """Tests flagging of duplicate socket IDs."""
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-DUP", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22},
        {"station_id": "STN-2", "socket_id": "SCK-DUP", "operator_name": "Op B", "socket_type": "DC", "power_kw": 60},
    ])

    annotated, summary = validate_charging_dataset(df)

    assert summary.duplicate_socket_ids == 2
    assert summary.unique_sockets == 1
    assert summary.invalid_socket_records == 2
    for errors in annotated["_validation_errors"]:
        assert any("Yinelenen Soket ID" in err for err in errors)


def test_missing_station_relationship():
    """Tests orphan sockets with missing or empty station_id."""
    df = pd.DataFrame([
        {"station_id": None, "socket_id": "SCK-1", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22},
        {"station_id": "  ", "socket_id": "SCK-2", "operator_name": "Op A", "socket_type": "DC", "power_kw": 60},
    ])

    annotated, summary = validate_charging_dataset(df)

    assert summary.missing_station_ids == 2
    assert summary.invalid_socket_records == 2
    for errors in annotated["_validation_errors"]:
        assert any("Eksik veya geçersiz İstasyon ID" in err for err in errors)


def test_validation_independent_of_dataframe_index_labels():
    """Defect 4 regression test: DataFrame indexed [10, 20] must not raise IndexError."""
    df = pd.DataFrame(
        [
            {"station_id": "STN-10", "socket_id": "SCK-10", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22},
            {"station_id": "STN-20", "socket_id": "SCK-20", "operator_name": "Op B", "socket_type": "DC", "power_kw": 120},
        ],
        index=[10, 20]
    )

    annotated, summary = validate_charging_dataset(df)
    assert len(annotated) == 2
    assert summary.unique_stations == 2
    assert summary.unique_sockets == 2
    assert bool(annotated.loc[10, "_is_valid"]) is True
    assert bool(annotated.loc[20, "_is_valid"]) is True
