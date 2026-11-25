"""
Data Loading and Schema Normalization Module for EPDK EV Charging Station Data.

Supports:
- EPDK raw JSON dumps (containing nested 'data' and 'soketler' lists).
- Normalized CSV exports (istasyonlar_*.csv and soketler_*.csv).
- ZIP archives containing EPDK JSON/CSV snapshots and attempt_log.jsonl metadata.

Enforces string ID preservation, non-destructive schema normalization, and preserves
stations without sockets as distinct records.
"""

import json
import zipfile
import gzip
import hashlib
import io
import re
from pathlib import Path
from typing import Union, Tuple, Optional, Dict, Any, List
import pandas as pd


# Canonical column mappings (case-insensitive)
COLUMN_ALIASES: Dict[str, List[str]] = {
    "station_id": [
        "station_id", "istasyon_id", "id", "stationid", "istasyonid",
        "sarjistasyonuno", "sarj_istasyonu_no", "istasyonno", "istasyon_no",
        "station_identifier", "sarj_istasyonu_id", "station_code"
    ],
    "station_name": [
        "station_name", "istasyon_adi", "sarjistasyonuadi", "sarj_istasyonu_adi",
        "name", "adi"
    ],
    "socket_id": [
        "socket_id", "soket_id", "socketid", "soketid",
        "soketno", "soket_no", "connector_id", "soket_kodu", "socket_number"
    ],
    "operator_name": [
        "operator_name", "operator", "isletmeci", "isletmeci_adi",
        "sarjagiisletmecisiunvan", "sarj_agi_isletmecisi_unvan",
        "lisans_sahibi", "operator_title", "sai_adi", "sirket_adi", "company"
    ],
    "operator_license_no": [
        "sarjagiisletmecisilisansno", "sarj_agi_isletmecisi_lisans_no",
        "operator_license_no", "lisans_no"
    ],
    "socket_type": [
        "socket_type", "soket_tipi", "sokettipi", "current_type", "akim_tipi",
        "ac_dc", "type", "tip", "tur"
    ],
    "socket_sub_type": [
        "socket_sub_type", "soket_turu", "soketturu", "connector_type", "baglanti_turu"
    ],
    "power_kw": [
        "power_kw", "guc_kw", "guc", "power", "powerkw",
        "soketgucu", "soket_gucu", "installed_power", "kapasite_kw", "rating_kw"
    ],
    "address": [
        "address", "adres"
    ],
    "latitude": [
        "latitude", "enlem", "lat"
    ],
    "longitude": [
        "longitude", "boylam", "lon", "lng"
    ],
    "snapshot_date": [
        "snapshot_date", "tarih", "kayit_tarihi", "timestamp", "date",
        "snapshot_timestamp", "veri_tarihi"
    ]
}


def normalize_schema(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Normalizes input DataFrame columns to canonical column names.
    Preserves all original columns while adding canonical aliases if renamed.
    """
    normalized_df = df.copy()
    col_mapping: Dict[str, str] = {}
    
    # Lowercase string lookup
    lower_to_orig = {str(c).strip().lower(): c for c in df.columns}
    
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in normalized_df.columns:
            continue
        for alias in aliases:
            cleaned_alias = alias.lower().replace("_", "")
            for col_lower, orig_col in lower_to_orig.items():
                if col_lower == alias.lower() or col_lower.replace("_", "") == cleaned_alias:
                    col_mapping[orig_col] = canonical
                    break
            if canonical in col_mapping.values():
                break

    if col_mapping:
        normalized_df = normalized_df.rename(columns=col_mapping)
    
    # Ensure IDs are string representations if present
    if "station_id" in normalized_df.columns:
        normalized_df["station_id"] = normalized_df["station_id"].astype(str)
    if "socket_id" in normalized_df.columns:
        # Keep None/NaN for stations without sockets, string for others
        normalized_df["socket_id"] = normalized_df["socket_id"].apply(
            lambda x: None if pd.isna(x) or str(x).lower() in ("none", "nan") else str(x)
        )
    
    return normalized_df, col_mapping


def load_from_csv(file_or_path: Union[str, Path, io.BytesIO], **kwargs) -> pd.DataFrame:
    """Loads dataset from CSV with automatic delimiter and encoding fallbacks."""
    delimiters = [",", ";", "\t"]
    encodings = ["utf-8", "utf-8-sig", "iso-8859-9", "cp1254", "latin1"]
    
    last_err: Optional[Exception] = None
    
    for enc in encodings:
        for sep in delimiters:
            try:
                if isinstance(file_or_path, (str, Path)):
                    df = pd.read_csv(file_or_path, sep=sep, encoding=enc, dtype=str, **kwargs)
                else:
                    file_or_path.seek(0)
                    df = pd.read_csv(file_or_path, sep=sep, encoding=enc, dtype=str, **kwargs)
                
                if df.shape[1] > 1:
                    return df
            except Exception as e:
                last_err = e
                continue
                
    if last_err:
        raise ValueError(f"CSV okuma başarısız oldu: {last_err}")
    return pd.DataFrame()


def load_from_json(file_or_path: Union[str, Path, io.BytesIO]) -> pd.DataFrame:
    """
    Loads dataset from JSON or gzip-compressed JSON (.json.gz).
    Handles EPDK raw gateway responses:
    - Root dict with 'data' key containing station records.
    - Each station record contains nested 'soketler' list.
    - Crucial: Stations with empty sockets list (soketler: []) are preserved with socket_id=None.
    """
    if isinstance(file_or_path, (str, Path)):
        p = Path(file_or_path)
        if p.name.endswith(".gz"):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
    else:
        file_or_path.seek(0)
        content = file_or_path.read()
        if isinstance(content, bytes):
            # Check gzip magic number 0x1f 0x8b
            if content.startswith(b"\x1f\x8b"):
                content = gzip.decompress(content).decode("utf-8", errors="replace")
            else:
                content = content.decode("utf-8", errors="replace")
        data = json.loads(content)

    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ["data", "items", "stations", "result", "results", "records"]:
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        if not items:
            items = [data]

    # Flatten nested sockets while PRESERVING stations without sockets
    flattened = []
    for item in items:
        if not isinstance(item, dict):
            continue
        
        sock_key = next((k for k in ["soketler", "sockets", "connectors"] if k in item), None)
        if sock_key:
            station_base = {k: v for k, v in item.items() if k != sock_key}
            sockets_list = item.get(sock_key, [])
            if isinstance(sockets_list, list) and len(sockets_list) > 0:
                for sock in sockets_list:
                    if isinstance(sock, dict):
                        # Merge station metadata with socket metadata
                        combined = {**station_base, **sock}
                        flattened.append(combined)
            else:
                # Station has 0 sockets: preserve station row with None for socket fields
                station_base["soketNo"] = None
                station_base["soketTipi"] = None
                station_base["soketTuru"] = None
                station_base["soketGucu"] = None
                flattened.append(station_base)
        else:
            flattened.append(item)

    return pd.DataFrame(flattened)


def load_from_zip(file_or_path: Union[str, Path, io.BytesIO]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Inspects and loads from an EPDK ZIP archive.
    Priority:
    1. Look for epdk_raw_*.json (contains authoritative station and socket records).
    2. Look for paired istasyonlar_*.csv and soketler_*.csv and join them on _row_id.
    3. Look for attempt_log.jsonl to extract snapshot timestamp metadata.
    """
    metadata: Dict[str, Any] = {}
    
    with zipfile.ZipFile(file_or_path, "r") as z:
        names = z.namelist()
        
        # Check attempt_log.jsonl for snapshot metadata
        log_name = next((n for n in names if n.endswith("attempt_log.jsonl")), None)
        if log_name:
            try:
                with z.open(log_name) as lf:
                    lines = lf.read().decode("utf-8").strip().splitlines()
                    for line in reversed(lines):
                        entry = json.loads(line)
                        if entry.get("status") == 200:
                            metadata["snapshot_timestamp"] = entry.get("ts")
                            metadata["record_count"] = entry.get("records")
                            metadata["bytes"] = entry.get("bytes")
                            metadata["headers"] = entry.get("headers", {})
                            break
            except Exception:
                pass

        # 1. Prefer raw JSON if available
        raw_json_name = next((n for n in names if "epdk_raw_" in n and n.endswith(".json")), None)
        if raw_json_name:
            with z.open(raw_json_name) as jf:
                df = load_from_json(io.BytesIO(jf.read()))
                metadata["source_file"] = raw_json_name
                return df, metadata
        
        # 2. Check for istasyonlar and soketler CSV pair
        st_name = next((n for n in names if "istasyonlar_" in n and n.endswith(".csv") and "konumlu" not in n), None)
        so_name = next((n for n in names if "soketler_" in n and n.endswith(".csv")), None)
        
        if st_name and so_name:
            with z.open(st_name) as sf, z.open(so_name) as of:
                st_df = load_from_csv(io.BytesIO(sf.read()))
                so_df = load_from_csv(io.BytesIO(of.read()))
                
                # Join on _row_id
                if "_row_id" in st_df.columns and "_row_id" in so_df.columns:
                    # outer join preserves stations without sockets
                    joined = so_df.merge(st_df, on="_row_id", how="outer")
                    metadata["source_file"] = f"{st_name} + {so_name}"
                    return joined, metadata

        # 3. Fallback to any CSV or JSON found
        for n in names:
            if n.endswith("/") or "conflict" in n.lower():
                continue
            if n.endswith(".csv"):
                with z.open(n) as cf:
                    metadata["source_file"] = n
                    return load_from_csv(io.BytesIO(cf.read())), metadata
            elif n.endswith(".json"):
                with z.open(n) as jf:
                    metadata["source_file"] = n
                    return load_from_json(io.BytesIO(jf.read())), metadata
                    
    raise ValueError("ZIP arşivi içinde geçerli bir EPDK veri seti bulunamadı.")


def load_dataset(file_or_path: Union[str, Path, io.BytesIO], filename_hint: Optional[str] = None) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Main loader entrypoint.
    Returns (normalized_df, applied_mappings).
    Snapshot metadata is attached to df.attrs.
    """
    name = str(filename_hint or file_or_path).lower()
    metadata: Dict[str, Any] = {}
    
    if name.endswith(".zip"):
        raw_df, metadata = load_from_zip(file_or_path)
    elif name.endswith(".json") or name.endswith(".json.gz") or name.endswith(".gz"):
        raw_df = load_from_json(file_or_path)
        p = Path(str(file_or_path)) if isinstance(file_or_path, (str, Path)) else None
        if p and p.exists() and p.is_file():
            # 1. Standardize hash semantics: Compute SHA-256 on UNCOMPRESSED canonical JSON bytes
            try:
                hasher = hashlib.sha256()
                if p.name.endswith(".gz"):
                    with gzip.open(p, "rb") as gz_f:
                        for chunk in iter(lambda: gz_f.read(65536), b""):
                            hasher.update(chunk)
                else:
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(65536), b""):
                            hasher.update(chunk)
                content_hash = hasher.hexdigest()
                metadata["sha256_hash"] = content_hash
                metadata["content_hash"] = content_hash
                metadata["source_file"] = p.name
            except Exception:
                content_hash = None

            # 2. Check for individual snapshot metadata file epdk_meta_<id>.json
            stem = p.name.replace(".json.gz", "").replace(".json", "").replace(".gz", "").replace("epdk_raw_", "")
            meta_candidate = p.parent / f"epdk_meta_{stem}.json"
            candidate_meta = None
            if meta_candidate.exists():
                try:
                    with open(meta_candidate, "r", encoding="utf-8") as mf:
                        candidate_meta = json.load(mf)
                except Exception:
                    pass

            # 3. Check for latest_manifest.json or manifest.json in the parent directory
            if not candidate_meta:
                for manifest_name in ["latest_manifest.json", "manifest.json"]:
                    manifest_path = p.parent / manifest_name
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as mf:
                                m_data = json.load(mf)
                                if (
                                    m_data.get("filename") == p.name
                                    or (content_hash and m_data.get("sha256_hash") == content_hash)
                                    or m_data.get("snapshot_id") == stem
                                ):
                                    candidate_meta = m_data
                                    break
                        except Exception:
                            pass

            # Check checksum match: a matching filename must NEVER override a checksum mismatch
            if candidate_meta:
                declared_hash = candidate_meta.get("sha256_hash")
                if declared_hash and content_hash and declared_hash != content_hash:
                    metadata["integrity_error"] = (
                        f"Checksum mismatch: computed SHA-256 ({content_hash[:12]}...) "
                        f"does not match manifest ({declared_hash[:12]}...)."
                    )
                    metadata["is_verified"] = False
                else:
                    metadata.update(candidate_meta)
                    metadata["is_verified"] = True

            # 4. Fallback: match strictly by timestamp pattern in filename from attempt_log.jsonl
            # Do NOT attach unrelated metadata merely because it is the latest log entry; unknown remains unknown.
            if "snapshot_timestamp" not in metadata and p.parent.exists():
                log_path = p.parent / "attempt_log.jsonl"
                if log_path.exists():
                    try:
                        m_time = re.search(r"(\d{8})_(\d{6})", p.name)
                        if m_time:
                            d, t = m_time.groups()
                            target_dt_pattern = f"{d[:4]}-{d[4:6]}-{d[6:8]}T{t[:2]}:{t[2:4]}:{t[4:6]}"
                            with open(log_path, "r", encoding="utf-8") as lf:
                                for line in reversed(lf.read().splitlines()):
                                    if not line.strip():
                                        continue
                                    entry = json.loads(line)
                                    if entry.get("status") == 200:
                                        ts = str(entry.get("ts", ""))
                                        pts = str(entry.get("pending_ts", ""))
                                        if target_dt_pattern in ts or target_dt_pattern in pts:
                                            metadata["snapshot_timestamp"] = ts
                                            metadata["record_count"] = entry.get("records")
                                            metadata["bytes"] = entry.get("bytes")
                                            break
                    except Exception:
                        pass
    else:
        # CSV handling with automatic pairing of istasyonlar and soketler exports
        p = Path(str(file_or_path)) if isinstance(file_or_path, (str, Path)) else None
        if p and p.exists() and p.is_file():
            fname = p.name.lower()
            if "istasyonlar_" in fname and "konumlu" not in fname:
                # Look for matching soketler CSV in the same folder
                so_candidate = p.parent / p.name.replace("istasyonlar_", "soketler_")
                if so_candidate.exists():
                    st_df = load_from_csv(p)
                    so_df = load_from_csv(so_candidate)
                    if "_row_id" in st_df.columns and "_row_id" in so_df.columns:
                        raw_df = so_df.merge(st_df, on="_row_id", how="outer")
                        metadata["source_file"] = f"{p.name} + {so_candidate.name}"
                        metadata["has_socket_data"] = True
                    else:
                        raw_df = st_df
                        metadata["source_file"] = p.name
                        metadata["has_socket_data"] = False
                else:
                    raw_df = load_from_csv(p)
                    metadata["source_file"] = p.name
                    metadata["has_socket_data"] = False
                    metadata["warning"] = "Eşleşen soket tablosu bulunamadı. Soket verileri mevcut değildir."
            elif "soketler_" in fname:
                st_candidate = p.parent / p.name.replace("soketler_", "istasyonlar_")
                if st_candidate.exists():
                    so_df = load_from_csv(p)
                    st_df = load_from_csv(st_candidate)
                    if "_row_id" in st_df.columns and "_row_id" in so_df.columns:
                        raw_df = so_df.merge(st_df, on="_row_id", how="outer")
                        metadata["source_file"] = f"{st_candidate.name} + {p.name}"
                        metadata["has_socket_data"] = True
                    else:
                        raw_df = so_df
                        metadata["source_file"] = p.name
                        metadata["has_socket_data"] = True
                else:
                    raw_df = load_from_csv(p)
                    metadata["source_file"] = p.name
                    metadata["has_socket_data"] = True
            else:
                raw_df = load_from_csv(file_or_path)
                metadata["source_file"] = p.name
        else:
            raw_df = load_from_csv(file_or_path)
        
    normalized_df, applied_mappings = normalize_schema(raw_df)
    normalized_df.attrs["metadata"] = metadata
    return normalized_df, applied_mappings


def generate_synthetic_fixture(num_records: int = 100, seed: int = 42) -> pd.DataFrame:
    """
    Generates a deterministic synthetic dataset for prototyping and unit tests.
    Explicitly labeled as synthetic; NOT representative of real EPDK statistics.
    """
    import random
    random.seed(seed)
    
    operators = ["E-Şarj A.Ş.", "ZES Dijital", "Voltrun", "Trugo Akıllı Şarj", "SharzNet", "Astor Şarj"]
    types = ["AC", "DC"]
    powers_ac = [11.0, 22.0]
    powers_dc = [60.0, 120.0, 150.0, 180.0, 300.0]
    
    records = []
    station_count = max(1, num_records // 3)
    stations = [f"STN-{1000 + i}" for i in range(station_count)]
    
    for i in range(num_records):
        stn = random.choice(stations)
        op = random.choice(operators)
        stype = random.choice(types)
        power = random.choice(powers_ac) if stype == "AC" else random.choice(powers_dc)
        
        records.append({
            "station_id": stn,
            "socket_id": f"SCK-{20000 + i}",
            "operator_name": op,
            "socket_type": stype,
            "power_kw": power,
            "snapshot_date": "2026-11-05"
        })
        
    df = pd.DataFrame(records)
    df.attrs["metadata"] = {"is_synthetic": True}
    return df
