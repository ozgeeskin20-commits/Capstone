"""
Data Validation and Quality Module for EPDK EV Charging Station Data.

Enforces structural, relational, and domain rules on station and socket records.
Preserves raw input data and provides comprehensive validation reporting in aggregate.
Fully vectorized for sub-second execution on large production datasets.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


@dataclass
class ValidationSummary:
    """Summary of data quality and validation results across a dataset."""
    total_records: int = 0
    valid_socket_records: int = 0
    invalid_socket_records: int = 0
    unique_stations: int = 0
    stations_with_sockets: int = 0
    stations_without_sockets: int = 0
    unique_sockets: int = 0
    duplicate_socket_ids: int = 0
    duplicate_station_ids: int = 0
    missing_required_fields: int = 0
    missing_station_ids: int = 0
    missing_socket_ids: int = 0
    unknown_ac_dc_count: int = 0
    conflicting_ac_dc_count: int = 0
    invalid_power_count: int = 0
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Toplam Kayıt Satırı": self.total_records,
            "Geçerli Soket Kayıtları": self.valid_socket_records,
            "Uyarılı/Soketsiz Kayıtlar": self.invalid_socket_records,
            "Kayıtlı İstasyon Sayısı (Toplam)": self.unique_stations,
            "Soketi bulunan istasyon": self.stations_with_sockets,
            "Soketsiz İstasyon Sayısı": self.stations_without_sockets,
            "Benzersiz Soket Sayısı": self.unique_sockets,
            "Yinelenen Soket ID": self.duplicate_socket_ids,
            "Eksik İstasyon İlişkisi": self.missing_station_ids,
            "Çelişkili AC/DC Sınıflandırması": self.conflicting_ac_dc_count,
            "Bilinmeyen AC/DC Sayısı": self.unknown_ac_dc_count,
            "Geçersiz Güç Değeri Sayısı": self.invalid_power_count,
        }


def normalize_ac_dc(val: Any) -> Tuple[Optional[str], bool]:
    """
    Normalizes AC/DC values to 'AC', 'DC' or None.
    Returns (normalized_value, is_valid).
    """
    if pd.isna(val) or val is None:
        return None, False
    
    s = str(val).strip().upper()
    s_clean = s.replace("İ", "I").replace("Ğ", "G").replace("Ü", "U").replace("Ş", "S").replace("Ö", "O").replace("Ç", "C")
    if s_clean in ("AC", "ALTERNATING_CURRENT", "ALTERNATIF AKIM", "ALTERNATIF") or s in ("AC", "ALTERNATING_CURRENT", "ALTERNATİF AKIM", "ALTERNATIF"):
        return "AC", True
    elif s_clean in ("DC", "DIRECT_CURRENT", "DOGRU AKIM") or s in ("DC", "DIRECT_CURRENT", "DOĞRU AKIM"):
        return "DC", True
    else:
        return s, False


def normalize_power(val: Any) -> Tuple[Optional[float], bool]:
    """
    Validates and converts power value to numeric kW.
    Must be a strictly positive float.
    Returns (power_kw, is_valid).
    """
    if pd.isna(val) or val is None:
        return None, False
    
    try:
        # Handle string formats e.g. "22 kW", "22,5"
        if isinstance(val, str):
            clean_str = val.lower().replace("kw", "").replace("kwh", "").strip()
            clean_str = clean_str.replace(",", ".")
            num = float(clean_str)
        else:
            num = float(val)
        
        if np.isnan(num) or np.isinf(num) or num <= 0:
            return None, False
        return num, True
    except (ValueError, TypeError):
        return None, False


def validate_charging_dataset(df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationSummary]:
    """
    Validates and annotates the normalized dataset using high-performance vectorization.
    
    Expects standardized column names:
      - station_id: Identifier of the physical charging station/location
      - socket_id: Identifier of the individual charging socket/connector
      - operator_name: Name of the licensed charging network operator
      - socket_type: AC or DC
      - power_kw: Installed socket power rating in kW
    
    Returns:
      - annotated_df: DataFrame with additional columns:
          _is_valid (bool): whether the record passed critical validation
          _validation_errors (list of str): specific issues per record
      - summary: ValidationSummary with aggregated audit counts.
    """
    n_rows = len(df)
    summary = ValidationSummary(total_records=n_rows)
    
    if df.empty:
        summary.issues.append("Veri kümesi boş (0 satır).")
        return df.copy(), summary

    df_validated = df.copy()

    # 1. Required columns presence
    required_cols = ["station_id", "socket_id", "operator_name", "socket_type", "power_kw"]
    for col in required_cols:
        if col not in df_validated.columns:
            df_validated[col] = None
            summary.issues.append(f"Zorunlu sütun eksik: '{col}' (varsayılan None eklendi)")

    # 2. Station ID validation (vectorized)
    station_col = df_validated["station_id"]
    station_s = station_col.fillna("").astype(str).str.strip()
    station_missing = (
        station_col.isna()
        | (station_s == "")
        | (station_s.str.lower() == "none")
        | (station_s.str.lower() == "nan")
    )
    summary.missing_station_ids = int(station_missing.sum())

    # 3. Socket ID validation (vectorized)
    socket_col = df_validated["socket_id"]
    socket_s = socket_col.fillna("").astype(str).str.strip()
    socket_missing = (
        socket_col.isna()
        | (socket_s == "")
        | (socket_s.str.lower() == "none")
        | (socket_s.str.lower() == "nan")
    )
    summary.missing_socket_ids = int(socket_missing.sum())

    # 4. Duplicate checks (vectorized)
    valid_sockets_mask = ~socket_missing
    duplicate_socket_mask = valid_sockets_mask & df_validated.duplicated(subset=["socket_id"], keep=False)
    summary.duplicate_socket_ids = int(duplicate_socket_mask.sum())

    valid_stations = station_s[~station_missing].unique()
    summary.unique_stations = len(valid_stations)
    summary.unique_sockets = int(socket_s[valid_sockets_mask].nunique())

    stations_with_scks = station_s[valid_sockets_mask].unique()
    summary.stations_with_sockets = len(stations_with_scks)
    summary.stations_without_sockets = max(0, summary.unique_stations - summary.stations_with_sockets)

    # 5. Operator check (vectorized)
    op_s = df_validated["operator_name"].fillna("").astype(str).str.strip()
    operator_missing = (op_s == "") | (op_s.str.lower().isin(["none", "nan"]))

    # 6. AC/DC normalization (fast list comprehension)
    types_raw = df_validated["socket_type"].tolist()
    norm_types: List[Optional[str]] = []
    type_valid_flags: List[bool] = []
    for val in types_raw:
        ntype, ok = normalize_ac_dc(val)
        norm_types.append(ntype)
        type_valid_flags.append(ok)

    type_ok_series = pd.Series(type_valid_flags, index=df_validated.index)
    norm_types_series = pd.Series(norm_types, index=df_validated.index)

    # Unknown AC/DC count
    unknown_type_mask = valid_sockets_mask & (~type_ok_series)
    summary.unknown_ac_dc_count = int(unknown_type_mask.sum())

    # 7. Same-row conflicting classification check
    has_sub_type = "socket_sub_type" in df_validated.columns or "soketTuru" in df_validated.columns
    sub_col = "socket_sub_type" if "socket_sub_type" in df_validated.columns else "soketTuru" if "soketTuru" in df_validated.columns else None

    conflict_mask = pd.Series(False, index=df_validated.index)
    if has_sub_type and sub_col:
        raw_sub = df_validated[sub_col].fillna("").astype(str).str.strip().str.upper()
        is_sub_ac = raw_sub.str.startswith("AC")
        is_sub_dc = raw_sub.str.startswith("DC")
        is_norm_dc = norm_types_series == "DC"
        is_norm_ac = norm_types_series == "AC"
        conflict_mask = valid_sockets_mask & norm_types_series.notna() & (
            (is_norm_dc & is_sub_ac) | (is_norm_ac & is_sub_dc)
        )
        summary.conflicting_ac_dc_count = int(conflict_mask.sum())
        
        # Crucial: Centrally assign conflicting sockets to 'Çelişkili' instead of arbitrarily forcing DC or AC
        norm_types_series[conflict_mask] = "Çelişkili"

    # 8. Power normalization (fast list comprehension)
    powers_raw = df_validated["power_kw"].tolist()
    norm_powers: List[Optional[float]] = []
    power_valid_flags: List[bool] = []
    for val in powers_raw:
        npwr, ok = normalize_power(val)
        norm_powers.append(npwr)
        power_valid_flags.append(ok)

    power_ok_series = pd.Series(power_valid_flags, index=df_validated.index)
    invalid_power_mask = valid_sockets_mask & (~power_ok_series)
    summary.invalid_power_count = int(invalid_power_mask.sum())

    # 9. Build error messages efficiently via flatnonzero on boolean masks
    errors_list: List[List[str]] = [[] for _ in range(n_rows)]
    
    # Pre-extract column arrays to avoid .iloc overhead in error formatting
    socket_id_arr = df_validated["socket_id"].to_numpy()
    socket_type_arr = df_validated["socket_type"].to_numpy()
    sub_type_arr = df_validated[sub_col].to_numpy() if (has_sub_type and sub_col) else None
    power_kw_arr = df_validated["power_kw"].to_numpy()

    for pos in np.flatnonzero(station_missing):
        errors_list[pos].append("Eksik veya geçersiz İstasyon ID")
        summary.missing_required_fields += 1

    for pos in np.flatnonzero(socket_missing):
        errors_list[pos].append("İstasyona bağlı soket bulunamadı (Soketsiz İstasyon)")

    for pos in np.flatnonzero(duplicate_socket_mask):
        errors_list[pos].append(f"Yinelenen Soket ID: {socket_id_arr[pos]}")

    for pos in np.flatnonzero(operator_missing):
        errors_list[pos].append("Eksik Operatör Adı")

    for pos in np.flatnonzero(unknown_type_mask):
        errors_list[pos].append(f"Tanınmayan Akım Tipi: '{socket_type_arr[pos]}'")

    if has_sub_type and sub_col:
        for pos in np.flatnonzero(conflict_mask):
            errors_list[pos].append(
                f"Çelişkili Sınıflandırma: soketTipi='{socket_type_arr[pos]}', soketTuru='{sub_type_arr[pos]}'"
            )

    for pos in np.flatnonzero(invalid_power_mask):
        errors_list[pos].append(f"Geçersiz Güç Değeri: '{power_kw_arr[pos]}'")

    is_valid_list = [len(errs) == 0 for errs in errors_list]

    df_validated["socket_type_normalized"] = norm_types_series.tolist()
    df_validated["power_kw_normalized"] = norm_powers
    df_validated["_validation_errors"] = errors_list
    df_validated["_is_valid"] = is_valid_list

    summary.valid_socket_records = sum(is_valid_list)
    summary.invalid_socket_records = n_rows - summary.valid_socket_records

    return df_validated, summary
