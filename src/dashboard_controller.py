"""
Dashboard Controller Module for EPDK EV Charging Station Analytics.
Provides production state management, filtering, integrity verification,
and metric computation helpers used directly by app.py and verified by tests.
"""

import gzip
import hashlib
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd

from src.metrics import compute_kpis


def filter_dataset(
    validated_df: pd.DataFrame,
    filter_all_ops: bool,
    selected_operators: List[str],
    selected_type: str,
    power_range: Tuple[float, float],
    min_power: float,
    max_power: float,
) -> Tuple[pd.DataFrame, bool, str]:
    """
    Applies dashboard sidebar filters to validated charging dataset.
    Returns:
      (filtered_df, is_socket_filter_active, station_subtext)
    
    Rules:
    - Empty operator selection (filter_all_ops=False and selected_operators=[]) yields empty DataFrame (0 rows).
    - Default power slider (power_range == (min_power, max_power)) preserves all registered stations,
      including socketless stations and rows with unknown power.
    - Explicit socket-level filter (selected_type != 'Tümü' or custom power range) filters sockets
      and explicitly labels the station population as 'Soket Kriterine Uyan İstasyonlar'.
    """
    if validated_df.empty:
        return validated_df.copy(), False, "Kayıtlı Tüm İstasyonlar"

    filtered_df = validated_df.copy()

    # 1. Operator filter
    if not filter_all_ops:
        if not selected_operators:
            # Explicit empty selection yields empty result
            filtered_df = filtered_df.iloc[0:0]
        else:
            filtered_df = filtered_df[filtered_df["operator_name"].isin(selected_operators)]

    # 2. Socket-level filters
    is_type_filter_active = (selected_type != "Tümü")
    is_power_filter_active = (
        "power_kw_normalized" in validated_df.columns
        and not validated_df["power_kw_normalized"].dropna().empty
        and (power_range[0] > min_power or power_range[1] < max_power)
    )
    is_socket_filter_active = is_type_filter_active or is_power_filter_active

    if is_type_filter_active:
        filtered_df = filtered_df[filtered_df["socket_type_normalized"] == selected_type]

    if is_power_filter_active:
        filtered_df = filtered_df[
            filtered_df["power_kw_normalized"].notna()
            & (filtered_df["power_kw_normalized"] >= power_range[0])
            & (filtered_df["power_kw_normalized"] <= power_range[1])
        ]

    station_subtext = "Soket Kriterine Uyan İstasyonlar" if is_socket_filter_active else "Kayıtlı Tüm İstasyonlar"
    return filtered_df, is_socket_filter_active, station_subtext


def verify_snapshot_integrity(raw_bytes: bytes, expected_sha256: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Verifies downloaded/stored snapshot bytes against the expected uncompressed SHA-256 hash.
    Decompresses gzip streams before hashing to standardize content semantics.
    """
    if not raw_bytes:
        return False, "Snapshot bytes are empty."

    try:
        if raw_bytes.startswith(b"\x1f\x8b"):
            uncompressed = gzip.decompress(raw_bytes)
        else:
            uncompressed = raw_bytes
    except Exception as e:
        return False, f"Decompression error: {e}"

    computed_sha = hashlib.sha256(uncompressed).hexdigest()

    if expected_sha256:
        if computed_sha != expected_sha256:
            return False, (
                f"Checksum mismatch: computed SHA-256 ({computed_sha[:12]}...) "
                f"does not match manifest ({expected_sha256[:12]}...)."
            )

    return True, None


def handle_file_upload(file_obj, loader_fn) -> Tuple[Optional[pd.DataFrame], Dict[str, Any], Optional[str]]:
    """
    Safely processes an uploaded file.
    If parsing fails, returns (None, {}, error_message) ensuring no fallback to stale data.
    """
    if file_obj is None:
        return None, {}, None

    try:
        df, mappings = loader_fn(file_obj, filename_hint=getattr(file_obj, "name", "upload"))
        return df, mappings, None
    except Exception as e:
        # Crucial: Clears DataFrame completely on upload failure
        return None, {}, str(e)

