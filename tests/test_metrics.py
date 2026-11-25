"""
Unit tests for Analytical Metrics and Aggregations Module (src/metrics.py).
"""

import pytest
import pandas as pd
from src.metrics import (
    compute_kpis,
    get_ac_dc_distribution,
    get_operator_socket_ranking,
    get_operator_power_ranking,
    get_observed_power_distribution
)


@pytest.fixture
def sample_dataframe():
    return pd.DataFrame([
        {
            "station_id": "STN-1",
            "socket_id": "SCK-1",
            "operator_name": "ZES",
            "socket_type_normalized": "AC",
            "power_kw_normalized": 22.0
        },
        {
            "station_id": "STN-1",
            "socket_id": "SCK-2",
            "operator_name": "ZES",
            "socket_type_normalized": "DC",
            "power_kw_normalized": 120.0
        },
        {
            "station_id": "STN-2",
            "socket_id": "SCK-3",
            "operator_name": "E-Sarj",
            "socket_type_normalized": "DC",
            "power_kw_normalized": 180.5
        },
        {
            "station_id": "STN-3",
            "socket_id": None,  # Station without socket
            "operator_name": "Trugo",
            "socket_type_normalized": None,
            "power_kw_normalized": None
        }
    ])


def test_compute_kpis_normal(sample_dataframe):
    kpis = compute_kpis(sample_dataframe)

    assert kpis["unique_stations"] == 3
    assert kpis["unique_sockets"] == 3
    assert kpis["ac_socket_count"] == 1
    assert kpis["dc_socket_count"] == 2
    assert kpis["operator_count"] == 3
    # Total power: 22.0 + 120.0 + 180.5 = 322.5
    assert kpis["total_socket_power_kw"] == 322.5
    assert kpis["sockets_per_station"] == 1.0  # 3 sockets / 3 stations


def test_compute_kpis_empty():
    empty_df = pd.DataFrame()
    kpis = compute_kpis(empty_df)

    assert kpis["unique_stations"] == 0
    assert kpis["unique_sockets"] == 0
    assert kpis["total_socket_power_kw"] == 0.0


def test_compute_kpis_missing_sockets():
    # Stations only without socket_id column
    df = pd.DataFrame([
        {"station_id": "STN-1", "operator_name": "ZES"},
        {"station_id": "STN-2", "operator_name": "Trugo"}
    ])
    kpis = compute_kpis(df)

    assert kpis["unique_stations"] == 2
    assert kpis["unique_sockets"] is None
    assert kpis["total_socket_power_kw"] is None
    assert kpis["ac_socket_count"] is None
    assert kpis["dc_socket_count"] is None


def test_get_ac_dc_distribution(sample_dataframe):
    dist = get_ac_dc_distribution(sample_dataframe)

    assert not dist.empty
    # Must only count the 3 actual sockets, NOT the socketless station
    assert dist["Soket Sayısı"].sum() == 3
    assert "Bilinmiyor" not in set(dist["Tip"])
    ac_row = dist[dist["Tip"] == "AC"]
    dc_row = dist[dist["Tip"] == "DC"]
    assert ac_row["Soket Sayısı"].iloc[0] == 1
    assert dc_row["Soket Sayısı"].iloc[0] == 2


def test_duplicate_socket_records_deduplication():
    """Defect 2 regression test: duplicate socket records must not inflate counts or power."""
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type_normalized": "AC", "power_kw_normalized": 22.0},
        {"station_id": "STN-1", "socket_id": "SCK-1", "operator_name": "Op A", "socket_type_normalized": "AC", "power_kw_normalized": 22.0}, # duplicate
        {"station_id": "STN-1", "socket_id": "SCK-2", "operator_name": "Op A", "socket_type_normalized": "DC", "power_kw_normalized": 120.0},
    ])

    kpis = compute_kpis(df)
    assert kpis["unique_sockets"] == 2
    assert kpis["ac_socket_count"] == 1
    assert kpis["dc_socket_count"] == 1
    assert kpis["total_socket_power_kw"] == 142.0  # 22 + 120, not 22 + 22 + 120

    dist = get_ac_dc_distribution(df)
    assert dist["Soket Sayısı"].sum() == 2

    pwr_dist = get_observed_power_distribution(df)
    assert pwr_dist["Soket Sayısı"].sum() == 2

    op_pwr = get_operator_power_ranking(df)
    assert op_pwr["Toplam Soket Gücü (kW)"].iloc[0] == 142.0



def test_get_operator_socket_ranking(sample_dataframe):
    ranking = get_operator_socket_ranking(sample_dataframe, top_n=5)

    assert "Soket Sayısı Payı (%)" in ranking.columns
    assert "Pazar Payı (%)" not in ranking.columns  # Ensure old label is not present

    zes_row = ranking[ranking["Operatör"] == "ZES"]
    assert zes_row["Soket Sayısı"].iloc[0] == 2
    # 2 out of 3 total sockets = 66.67%
    assert zes_row["Soket Sayısı Payı (%)"].iloc[0] == 66.67


def test_get_operator_power_ranking(sample_dataframe):
    pwr_ranking = get_operator_power_ranking(sample_dataframe, top_n=5)

    assert not pwr_ranking.empty
    assert "Toplam Soket Gücü (kW)" in pwr_ranking.columns

    # E-Sarj has 180.5 kW, ZES has 142.0 kW
    top_op = pwr_ranking.iloc[0]
    assert top_op["Operatör"] == "E-Sarj"
    assert top_op["Toplam Soket Gücü (kW)"] == 180.5


def test_get_observed_power_distribution(sample_dataframe):
    dist = get_observed_power_distribution(sample_dataframe)

    assert not dist.empty
    assert set(dist["Güç (kW)"]) == {22.0, 120.0, 180.5}


def test_conflicting_duplicates_order_invariance():
    """
    Section 5 regression test:
    The same socket ID assigned to two operators, or with conflicting power/type:
    - Must NOT produce duplicate 100% share for both operators.
    - Power total must be invariant to row order.
    - Conflicting socket records must be excluded from affected aggregates with clear exclusion counts.
    """
    df_order_a = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-X", "operator_name": "ZES", "socket_type_normalized": "AC", "power_kw_normalized": 22.0},
        {"station_id": "STN-1", "socket_id": "SCK-X", "operator_name": "Trugo", "socket_type_normalized": "DC", "power_kw_normalized": 180.0},
        {"station_id": "STN-2", "socket_id": "SCK-UNAMBIGUOUS", "operator_name": "Astor", "socket_type_normalized": "DC", "power_kw_normalized": 100.0},
    ])

    df_order_b = df_order_a.iloc[::-1].reset_index(drop=True)

    kpis_a = compute_kpis(df_order_a)
    kpis_b = compute_kpis(df_order_b)

    assert kpis_a["unique_sockets"] == 2
    assert kpis_b["unique_sockets"] == 2
    assert kpis_a["conflicting_power_sockets_excluded"] == 1
    assert kpis_b["conflicting_power_sockets_excluded"] == 1
    assert kpis_a["total_socket_power_kw"] == 100.0
    assert kpis_b["total_socket_power_kw"] == 100.0

    rank_a = get_operator_socket_ranking(df_order_a)
    rank_b = get_operator_socket_ranking(df_order_b)
    pd.testing.assert_frame_equal(rank_a, rank_b)
    assert "Astor" in rank_a["Operatör"].values
    assert "ZES" not in rank_a["Operatör"].values
    assert "Trugo" not in rank_a["Operatör"].values

    dist_a = get_ac_dc_distribution(df_order_a)
    dist_b = get_ac_dc_distribution(df_order_b)
    pd.testing.assert_frame_equal(dist_a, dist_b)
    assert "Çelişkili" in dist_a["Tip"].values


def test_single_row_ac_dc_conflict_reconciliation():
    """
    Phase 1.2.2 requirement:
    - Single-row conflict (soketTipi=DC vs soketTuru=AC_TYPE2) must be detected as 'Çelişkili'.
    - Category reconciliation equation: Total = AC + DC + Çelişkili + Bilinmeyen must strictly hold.
    - Sockets with contradictory type but unambiguous power must be included in power sum.
    - Observed power distribution must show type-conflicting sockets under 'Çelişkili' category.
    """
    df = pd.DataFrame([
        {"station_id": "STN-1", "socket_id": "SCK-AC", "operator_name": "Op1", "socket_type_normalized": "AC", "power_kw_normalized": 22.0},
        {"station_id": "STN-2", "socket_id": "SCK-DC", "operator_name": "Op2", "socket_type_normalized": "DC", "power_kw_normalized": 120.0},
        {"station_id": "STN-3", "socket_id": "SCK-CONFLICT", "operator_name": "Op3", "socket_type_normalized": "Çelişkili", "power_kw_normalized": 50.0},
        {"station_id": "STN-4", "socket_id": "SCK-UNKNOWN", "operator_name": "Op4", "socket_type_normalized": None, "power_kw_normalized": 11.0},
    ])

    kpis = compute_kpis(df)
    assert kpis["unique_sockets"] == 4
    assert kpis["ac_socket_count"] == 1
    assert kpis["dc_socket_count"] == 1
    assert kpis["conflicting_type_sockets_count"] == 1
    assert kpis["unknown_type_sockets_count"] == 1

    # Strict reconciliation equation holds
    assert kpis["unique_sockets"] == (
        kpis["ac_socket_count"] +
        kpis["dc_socket_count"] +
        kpis["conflicting_type_sockets_count"] +
        kpis["unknown_type_sockets_count"]
    )

    # Valid power of type-conflicting socket (50.0) is included: 22 + 120 + 50 + 11 = 203.0
    assert kpis["total_socket_power_kw"] == 203.0

    dist = get_ac_dc_distribution(df)
    assert set(dist["Tip"].values) == {"AC", "DC", "Çelişkili", "Bilinmiyor"}
    assert dist.loc[dist["Tip"] == "AC", "Soket Sayısı"].iloc[0] == 1
    assert dist.loc[dist["Tip"] == "DC", "Soket Sayısı"].iloc[0] == 1
    assert dist.loc[dist["Tip"] == "Çelişkili", "Soket Sayısı"].iloc[0] == 1
    assert dist.loc[dist["Tip"] == "Bilinmiyor", "Soket Sayısı"].iloc[0] == 1
    assert dist["Soket Sayısı"].sum() == 4

    # Power distribution shows Çelişkili
    p_dist = get_observed_power_distribution(df)
    conflict_rows = p_dist[p_dist["Akım Tipi"] == "Çelişkili"]
    assert len(conflict_rows) == 1
    assert conflict_rows["Güç (kW)"].iloc[0] == 50.0


def test_real_snapshot_exact_reconciliation():
    """
    Phase 1.2.2 requirement on real dataset:
    Total: 50,587
    AC: 28,474
    DC: 22,112
    Çelişkili: 1
    Bilinmeyen: 0
    """
    from pathlib import Path
    from src.data_loader import load_dataset
    from src.validator import validate_charging_dataset

    snap_file = Path("_local_data/epdk_raw_20261124_112635_9d0f9e.json.gz")
    if not snap_file.exists():
        pytest.skip("Real local snapshot not found")

    df, _ = load_dataset(snap_file)
    vdf, summary = validate_charging_dataset(df)
    kpis = compute_kpis(vdf)

    assert kpis["unique_sockets"] == 50587
    assert kpis["ac_socket_count"] == 28474
    assert kpis["dc_socket_count"] == 22112
    assert kpis["conflicting_type_sockets_count"] == 1
    assert kpis["unknown_type_sockets_count"] == 0
    assert kpis["unique_sockets"] == (
        kpis["ac_socket_count"] +
        kpis["dc_socket_count"] +
        kpis["conflicting_type_sockets_count"] +
        kpis["unknown_type_sockets_count"]
    )
