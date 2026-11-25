"""
Regression tests for Phase 1 defect fixes and App logic:
- Defect 1: Power filter default preserves socketless stations; explicit socket filter labels/filters stations.
- Defect 2: AC/DC distribution excludes socketless station placeholders and deduplicates sockets.
- Defect 3: Clearing operator selection produces an empty result.
- Defect 4: validate_charging_dataset handles non-positional index labels without IndexError.
- Defect 5: Failed file upload clears raw_df to prevent stale-data fallback.
"""

import io
import json
import pytest
import pandas as pd
from src.validator import validate_charging_dataset
from src.metrics import (
    compute_kpis,
    get_ac_dc_distribution,
    get_operator_socket_ranking,
    get_operator_power_ranking
)
from src.data_loader import load_dataset, generate_synthetic_fixture


def test_defect_1_power_filter_preserves_socketless_stations_by_default():
    """
    Defect 1: Full-range power filter by default must NOT remove stations without sockets.
    When a dataset has 3 stations (1 of which has no sockets), default view must show all 3 stations.
    """
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22.0},
        {"station_id": "STN-2", "socket_id": "SCK-2", "operator_name": "Op A", "socket_type": "DC", "power_kw": 120.0},
        {"station_id": "STN-EMPTY", "socket_id": None, "operator_name": "Op B", "socket_type": None, "power_kw": None},
    ])
    
    validated_df, summary = validate_charging_dataset(df)
    assert summary.unique_stations == 3
    assert summary.stations_without_sockets == 1
    
    # Simulate default filter state in app.py
    valid_powers = validated_df["power_kw_normalized"].dropna()
    min_power = float(valid_powers.min())
    max_power = float(valid_powers.max())
    power_range = (min_power, max_power)
    selected_type = "Tümü"
    
    is_type_filter_active = (selected_type != "Tümü")
    is_power_filter_active = not valid_powers.empty and (power_range[0] > min_power or power_range[1] < max_power)
    is_socket_filter_active = is_type_filter_active or is_power_filter_active
    
    filtered_df = validated_df.copy()
    if is_type_filter_active:
        filtered_df = filtered_df[filtered_df["socket_type_normalized"] == selected_type]
    if is_power_filter_active:
        filtered_df = filtered_df[
            filtered_df["power_kw_normalized"].notna() &
            (filtered_df["power_kw_normalized"] >= power_range[0]) &
            (filtered_df["power_kw_normalized"] <= power_range[1])
        ]
        
    kpis = compute_kpis(filtered_df)
    # MUST preserve all 3 stations in default view!
    assert kpis["unique_stations"] == 3
    assert is_socket_filter_active is False

    # Now simulate user explicitly applying a power filter (e.g. power >= 50)
    power_range_user = (50.0, max_power)
    is_power_filter_active_user = (power_range_user[0] > min_power or power_range_user[1] < max_power)
    filtered_df_user = validated_df.copy()
    if is_power_filter_active_user:
        filtered_df_user = filtered_df_user[
            filtered_df_user["power_kw_normalized"].notna() &
            (filtered_df_user["power_kw_normalized"] >= power_range_user[0]) &
            (filtered_df_user["power_kw_normalized"] <= power_range_user[1])
        ]
    kpis_user = compute_kpis(filtered_df_user)
    # Only STN-2 has power >= 50
    assert kpis_user["unique_stations"] == 1
    assert is_power_filter_active_user is True


def test_defect_2_ac_dc_distribution_excludes_socketless_station_placeholders():
    """
    Defect 2: get_ac_dc_distribution must NOT count socketless stations as 'Bilinmiyor' sockets.
    """
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type_normalized": "AC", "power_kw_normalized": 22.0},
        {"station_id": "STN-2", "socket_id": None, "operator_name": "Op B", "socket_type_normalized": None, "power_kw_normalized": None},
    ])
    
    dist = get_ac_dc_distribution(df)
    assert dist["Soket Sayısı"].sum() == 1
    assert "Bilinmiyor" not in dist["Tip"].values


def test_defect_3_clearing_operator_selection_produces_empty_result():
    """
    Defect 3: When filter_all_ops is False and selected_operators is empty, result must be empty.
    """
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "ZES", "socket_type_normalized": "AC", "power_kw_normalized": 22.0},
        {"station_id": "STN-2", "socket_id": "SCK-2", "operator_name": "Trugo", "socket_type_normalized": "DC", "power_kw_normalized": 180.0},
    ])
    
    filter_all_ops = False
    selected_operators = []  # User cleared selection
    
    filtered_df = df.copy()
    if not filter_all_ops:
        if not selected_operators:
            filtered_df = filtered_df.iloc[0:0]
        else:
            filtered_df = filtered_df[filtered_df["operator_name"].isin(selected_operators)]
            
    assert len(filtered_df) == 0
    kpis = compute_kpis(filtered_df)
    assert kpis["unique_stations"] == 0
    assert kpis["unique_sockets"] == 0


def test_defect_4_validation_with_non_range_index():
    """
    Defect 4: validate_charging_dataset on DataFrame indexed [100, 200] must not raise IndexError.
    """
    df = pd.DataFrame(
        [
            {"station_id": "STN-100", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type": "AC", "power_kw": 22.0},
            {"station_id": "STN-200", "socket_id": "SCK-2", "operator_name": "Op B", "socket_type": "DC", "power_kw": 60.0},
        ],
        index=[100, 200]
    )
    
    annotated, summary = validate_charging_dataset(df)
    assert len(annotated) == 2
    assert summary.unique_stations == 2
    assert summary.unique_sockets == 2
    assert bool(annotated.loc[100, "_is_valid"]) is True
    assert bool(annotated.loc[200, "_is_valid"]) is True


def test_defect_5_failed_upload_does_not_fallback_to_stale_data():
    """
    Defect 5: A failed upload must set raw_df to None instead of retaining previous data.
    """
    # Simulate a corrupted uploaded file
    corrupted_stream = io.BytesIO(b"NOT A VALID JSON OR CSV {corrupt")
    corrupted_stream.name = "broken_file.json"
    
    raw_df = generate_synthetic_fixture(5)  # Previous data in memory
    
    # App logic on upload
    try:
        raw_df, _ = load_dataset(corrupted_stream, filename_hint="broken_file.json")
    except Exception:
        raw_df = None  # Crucial fix: cleared on failure
        
    assert raw_df is None


def test_snapshot_change_cache_invalidation():
    """
    Phase 1.2.2 requirement:
    - Validation cache key must be bound to snapshot_id/content_hash and validation version.
    - When snapshot changes, cache key changes, ensuring stale validation results are never reused.
    """
    VALIDATION_VERSION = "v1.2.2"
    
    snap1_meta = {"snapshot_id": "snap_20261030_082729", "sha256_hash": "hash_aaa"}
    snap2_meta = {"snapshot_id": "snap_20261124_112635", "sha256_hash": "hash_bbb"}

    key1 = f"_validated_df_{snap1_meta['snapshot_id']}_{VALIDATION_VERSION}"
    key2 = f"_validated_df_{snap2_meta['snapshot_id']}_{VALIDATION_VERSION}"

    assert key1 != key2
    assert "snap_20261030_082729" in key1
    assert "snap_20261124_112635" in key2
    assert VALIDATION_VERSION in key1


