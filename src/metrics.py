"""
Analytical Metrics and Aggregations Module for EPDK EV Charging Station Data.

Computes KPI metrics, AC/DC distributions, power distributions, and operator rankings.
Enforces accurate entity semantics:
- Stations != Sockets.
- Separates identical duplicate rows from conflicting socket records.
- Eliminates row-order dependence: NEVER uses arbitrary keep="first" on conflicting records.
- Flags ambiguity and classifies conflicting sockets deterministically.
- Strict Category Reconciliation: Total Sockets = AC + DC + Çelişkili + Bilinmeyen.
- Fully vectorized for sub-second execution on large production datasets.
"""

from typing import Dict, Any, Optional, Tuple, Set, List
import pandas as pd
import numpy as np


def _drop_duplicates_safe(df: pd.DataFrame, subset: Optional[List[str]] = None) -> pd.DataFrame:
    """Drops duplicate rows safely even if DataFrame contains unhashable column types like lists."""
    if df.empty:
        return df
    if subset is not None:
        return df.drop_duplicates(subset=subset)
    hashable_cols = [
        c for c in df.columns 
        if c != "_validation_errors" and not (len(df) > 0 and isinstance(df[c].iloc[0], (list, dict, set)))
    ]
    return df.drop_duplicates(subset=hashable_cols)


def detect_socket_conflicts(df: pd.DataFrame) -> Dict[str, Set[str]]:
    """
    Detects sockets with conflicting attributes across records or within records.
    Returns sets of socket IDs with conflicts in:
    - operator: socket_id associated with > 1 distinct operator_name
    - power: socket_id associated with > 1 distinct power_kw_normalized
    - type: socket_id associated with > 1 distinct socket_type_normalized across rows,
            OR marked as 'Çelişkili' within a single row (e.g. soketTipi=DC vs soketTuru=AC_TYPE2).
    """
    if df.empty or "socket_id" not in df.columns:
        return {"operator": set(), "power": set(), "type": set()}

    df_valid = _drop_duplicates_safe(df.dropna(subset=["socket_id"]))

    conflicts = {"operator": set(), "power": set(), "type": set()}

    if "operator_name" in df_valid.columns:
        op_counts = df_valid.dropna(subset=["operator_name"]).groupby("socket_id")["operator_name"].nunique()
        conflicts["operator"] = set(op_counts[op_counts > 1].index)

    if "power_kw_normalized" in df_valid.columns:
        pwr_counts = df_valid.dropna(subset=["power_kw_normalized"]).groupby("socket_id")["power_kw_normalized"].nunique()
        conflicts["power"] = set(pwr_counts[pwr_counts > 1].index)

    if "socket_type_normalized" in df_valid.columns:
        # Cross-row conflicts (different type labels for the same socket_id)
        type_counts = df_valid.dropna(subset=["socket_type_normalized"]).groupby("socket_id")["socket_type_normalized"].nunique()
        cross_row_conflicts = set(type_counts[type_counts > 1].index)
        
        # Single-row conflicts (explicitly identified as 'Çelişkili')
        single_row_conflicts = set(
            df_valid.loc[df_valid["socket_type_normalized"] == "Çelişkili", "socket_id"].dropna()
        )
        conflicts["type"] = cross_row_conflicts.union(single_row_conflicts)

    return conflicts


def compute_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes top-level market KPIs on validated dataset.
    
    Category Reconciliation Rule:
        Total Sockets = AC + DC + Çelişkili + Bilinmeyen
    
    Power Policy:
        Sockets with conflicting type classifications but valid unambiguous numeric power
        ratings ARE included in the overall nameplate power sum, since electric capacity
        is physically present even if the socket connector/feed type label is contradictory.
        Sockets with conflicting power values are excluded from the power sum.
    """
    if df.empty:
        return {
            "unique_stations": 0,
            "unique_sockets": 0,
            "sockets_per_station": 0.0,
            "total_socket_power_kw": 0.0,
            "ac_socket_count": 0,
            "dc_socket_count": 0,
            "conflicting_type_sockets_count": 0,
            "unknown_type_sockets_count": 0,
            "operator_count": 0,
            "conflicting_power_sockets_excluded": 0,
        }

    unique_stations = int(df["station_id"].dropna().nunique()) if "station_id" in df.columns else 0

    # Check if socket data is present
    has_sockets = "socket_id" in df.columns and df["socket_id"].dropna().shape[0] > 0
    if not has_sockets:
        return {
            "unique_stations": unique_stations,
            "unique_sockets": None,
            "sockets_per_station": None,
            "total_socket_power_kw": None,
            "ac_socket_count": None,
            "dc_socket_count": None,
            "conflicting_type_sockets_count": None,
            "unknown_type_sockets_count": None,
            "operator_count": int(df["operator_name"].dropna().nunique()) if "operator_name" in df.columns else 0,
            "conflicting_power_sockets_excluded": 0,
        }

    conflicts = detect_socket_conflicts(df)
    conflicting_pwr = conflicts["power"]
    conflicting_types = conflicts["type"]

    # Unique physical sockets count
    df_clean = _drop_duplicates_safe(df.dropna(subset=["socket_id"]))
    unique_sockets = int(df_clean["socket_id"].nunique())
    avg_sps = round(unique_sockets / max(1, unique_stations), 2)

    # 1. Power aggregation: Exclude sockets with conflicting power values
    # Valid unambiguous powers are included (regardless of type conflict)
    if "power_kw_normalized" in df_clean.columns:
        unambiguous_power_df = df_clean[~df_clean["socket_id"].isin(conflicting_pwr)].dropna(subset=["power_kw_normalized"])
        unique_socket_power = unambiguous_power_df.groupby("socket_id")["power_kw_normalized"].first()
        total_power = float(unique_socket_power.sum())
    else:
        total_power = 0.0

    # 2. AC/DC/Çelişkili/Bilinmeyen counts on unique socket entities (Vectorized)
    if "socket_type_normalized" in df_clean.columns:
        # Create single row per unique socket
        unique_sockets_df = df_clean.drop_duplicates(subset=["socket_id"]).copy()
        
        # Determine classification for each socket
        sck_ids = unique_sockets_df["socket_id"]
        types = unique_sockets_df["socket_type_normalized"].copy()
        
        is_conflicting = sck_ids.isin(conflicting_types) | (types == "Çelişkili")
        
        ac_count = int(((types == "AC") & (~is_conflicting)).sum())
        dc_count = int(((types == "DC") & (~is_conflicting)).sum())
        conflicting_count = int(is_conflicting.sum())
        is_unknown = ((types.isna()) | (~types.isin(["AC", "DC", "Çelişkili"]))) & (~is_conflicting)
        unknown_count = int(is_unknown.sum())
    else:
        ac_count = 0
        dc_count = 0
        conflicting_count = 0
        unknown_count = unique_sockets

    op_count = int(df["operator_name"].dropna().nunique()) if "operator_name" in df.columns else 0

    return {
        "unique_stations": unique_stations,
        "unique_sockets": unique_sockets,
        "sockets_per_station": avg_sps,
        "total_socket_power_kw": round(total_power, 2),
        "ac_socket_count": ac_count,
        "dc_socket_count": dc_count,
        "conflicting_type_sockets_count": conflicting_count,
        "unknown_type_sockets_count": unknown_count,
        "operator_count": op_count,
        "conflicting_power_sockets_excluded": len(conflicting_pwr),
    }


def get_ac_dc_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns distribution of sockets by AC/DC/Çelişkili/Bilinmeyen type.
    Counts actual socket entities only (excludes socketless station placeholders).
    Fully vectorized without row-order dependence or groupby Python iteration.
    """
    if df.empty or "socket_type_normalized" not in df.columns or "socket_id" not in df.columns:
        return pd.DataFrame(columns=["Tip", "Soket Sayısı", "Oran (%)"])

    df_clean = _drop_duplicates_safe(df.dropna(subset=["socket_id"]))
    if df_clean.empty:
        return pd.DataFrame(columns=["Tip", "Soket Sayısı", "Oran (%)"])

    conflicts = detect_socket_conflicts(df_clean)
    conflicting_types = conflicts["type"]

    # Vectorized unique socket entity classification
    unique_sockets_df = df_clean.drop_duplicates(subset=["socket_id"]).copy()
    sck_ids = unique_sockets_df["socket_id"]
    types = unique_sockets_df["socket_type_normalized"].fillna("Bilinmiyor").copy()

    # Assign conflicting status
    is_conflicting = sck_ids.isin(conflicting_types) | (types == "Çelişkili")
    types.loc[is_conflicting] = "Çelişkili"

    # Normalize unknown categories
    types.loc[~types.isin(["AC", "DC", "Çelişkili"])] = "Bilinmiyor"

    counts_series = types.value_counts()
    
    # Order: AC, DC, Çelişkili, Bilinmiyor
    desired_order = ["AC", "DC", "Çelişkili", "Bilinmiyor"]
    ordered_labels = [c for c in desired_order if c in counts_series.index]
    
    counts = counts_series.loc[ordered_labels].reset_index()
    counts.columns = ["Tip", "Soket Sayısı"]

    total = max(1, counts["Soket Sayısı"].sum())
    counts["Oran (%)"] = (counts["Soket Sayısı"] / total * 100).round(2)
    return counts


def get_operator_socket_ranking(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """
    Returns top operators ranked by unique socket count.
    Excludes ambiguous sockets claimed by multiple distinct operators to prevent
    duplicate share attribution (>100% total sum) and row-order bias.
    """
    if df.empty or "operator_name" not in df.columns or "socket_id" not in df.columns or df["socket_id"].dropna().empty:
        return pd.DataFrame(columns=["Operatör", "Soket Sayısı", "İstasyon Sayısı", "Soket Sayısı Payı (%)"])

    df_clean = _drop_duplicates_safe(df.dropna(subset=["socket_id", "operator_name"]))
    conflicts = detect_socket_conflicts(df_clean)
    conflicting_ops = conflicts["operator"]

    # Exclude ambiguous sockets with conflicting operator assignments
    unambiguous_df = df_clean[~df_clean["socket_id"].isin(conflicting_ops)]

    if unambiguous_df.empty:
        return pd.DataFrame(columns=["Operatör", "Soket Sayısı", "İstasyon Sayısı", "Soket Sayısı Payı (%)"])

    grouped = unambiguous_df.groupby("operator_name").agg(
        soket_sayisi=("socket_id", "nunique"),
        istasyon_sayisi=("station_id", "nunique") if "station_id" in unambiguous_df.columns else ("socket_id", "count")
    ).reset_index()

    total_valid_sockets = max(1, unambiguous_df["socket_id"].nunique())
    grouped["Soket Sayısı Payı (%)"] = (grouped["soket_sayisi"] / total_valid_sockets * 100).round(2)
    grouped = grouped.sort_values(by=["soket_sayisi", "operator_name"], ascending=[False, True]).head(top_n)
    grouped.columns = ["Operatör", "Soket Sayısı", "İstasyon Sayısı", "Soket Sayısı Payı (%)"]
    return grouped


def get_operator_power_ranking(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """
    Returns top operators ranked by total installed socket power (kW).
    Excludes ambiguous sockets with conflicting operator or power records.
    Independent of row order.
    """
    if df.empty or "operator_name" not in df.columns or "power_kw_normalized" not in df.columns:
        return pd.DataFrame(columns=["Operatör", "Toplam Soket Gücü (kW)", "Ortalama Soket Gücü (kW)"])

    df_clean = _drop_duplicates_safe(df.dropna(subset=["socket_id", "operator_name", "power_kw_normalized"]))
    conflicts = detect_socket_conflicts(df_clean)
    excluded_scks = conflicts["operator"].union(conflicts["power"])

    unambiguous_df = df_clean[~df_clean["socket_id"].isin(excluded_scks)]

    if unambiguous_df.empty:
        return pd.DataFrame(columns=["Operatör", "Toplam Soket Gücü (kW)", "Ortalama Soket Gücü (kW)"])

    unique_sockets = unambiguous_df.groupby("socket_id").first().reset_index()

    grouped = unique_sockets.groupby("operator_name").agg(
        toplam_guc=("power_kw_normalized", "sum"),
        ortalama_guc=("power_kw_normalized", "mean")
    ).reset_index()

    grouped["toplam_guc"] = grouped["toplam_guc"].round(1)
    grouped["ortalama_guc"] = grouped["ortalama_guc"].round(1)
    grouped = grouped.sort_values(by=["toplam_guc", "operator_name"], ascending=[False, True]).head(top_n)
    grouped.columns = ["Operatör", "Toplam Soket Gücü (kW)", "Ortalama Soket Gücü (kW)"]
    return grouped


def get_observed_power_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """
    Returns observed discrete power rating frequency distribution.
    Uses observed numerical values without inventing arbitrary synthetic bins.
    Counts unique actual sockets, excluding power conflicts.
    Sockets with contradictory type classifications are displayed under 'Çelişkili' group.
    """
    if df.empty or "power_kw_normalized" not in df.columns or "socket_id" not in df.columns:
        return pd.DataFrame(columns=["Güç (kW)", "Akım Tipi", "Soket Sayısı"])

    df_clean = _drop_duplicates_safe(df.dropna(subset=["socket_id", "power_kw_normalized"]))
    conflicts = detect_socket_conflicts(df_clean)
    excluded_power_scks = conflicts["power"]

    # Only exclude sockets with conflicting power readings
    unambiguous_df = df_clean[~df_clean["socket_id"].isin(excluded_power_scks)]
    if unambiguous_df.empty:
        return pd.DataFrame(columns=["Güç (kW)", "Akım Tipi", "Soket Sayısı"])

    # Unique socket record per socket_id
    unique_sockets = unambiguous_df.groupby("socket_id").first().reset_index()

    type_col = "socket_type_normalized" if "socket_type_normalized" in unique_sockets.columns else None
    if type_col:
        # Determine classification
        classified_types = unique_sockets[type_col].fillna("Bilinmiyor").copy()
        conflicting_types = conflicts["type"]
        is_conflicting = unique_sockets["socket_id"].isin(conflicting_types) | (classified_types == "Çelişkili")
        classified_types.loc[is_conflicting] = "Çelişkili"
        classified_types.loc[~classified_types.isin(["AC", "DC", "Çelişkili"])] = "Bilinmiyor"
        unique_sockets["_display_type"] = classified_types

        grouped = unique_sockets.groupby(["power_kw_normalized", "_display_type"]).size().reset_index(name="Soket Sayısı")
        grouped.columns = ["Güç (kW)", "Akım Tipi", "Soket Sayısı"]
    else:
        grouped = unique_sockets.groupby("power_kw_normalized").size().reset_index(name="Soket Sayısı")
        grouped["Akım Tipi"] = "Bilinmiyor"
        grouped = grouped[["power_kw_normalized", "Akım Tipi", "Soket Sayısı"]]
        grouped.columns = ["Güç (kW)", "Akım Tipi", "Soket Sayısı"]

    grouped = grouped.sort_values(by="Güç (kW)")
    return grouped
