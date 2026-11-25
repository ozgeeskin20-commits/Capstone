"""
Daily Archive Builder.

Derives a small, committable historical record from the raw snapshot that the
collector stores locally. Raw snapshots stay out of version control; only the
compact derived records below are written, so repository growth stays bounded.

Outputs (under data/archive/):
    daily/YYYY-MM-DD.csv.gz   Station-level facts for that day (small, gzipped).
    stations_dim.csv          One row per station ever observed, with first_seen
                              and last_seen. Sorted by station_id so day-to-day
                              diffs stay minimal.
    daily_totals.csv          One row per day, for fast time-series reads.

Reuses the existing loading, schema normalization and validation pipeline so the
archive and the dashboard always agree on how a record is interpreted.

Privacy: the raw payload may carry `sarjIstasyonuIsletmecisi`, which can hold a
natural person's name. That field is never written to the archive. Only the
licensed network operator's title and licence number are kept.

Usage:
    python -m src.archive.daily_archive
"""

import gzip
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from src.archive import repo_snapshot
from src.data_loader import load_dataset
from src.validator import validate_charging_dataset

TZ_ISTANBUL = timezone(timedelta(hours=3))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ARCHIVE_DIR = Path(os.getenv("ARCHIVE_DIR", REPO_ROOT / "data" / "archive"))
DAILY_DIR = ARCHIVE_DIR / "daily"
DIM_PATH = ARCHIVE_DIR / "stations_dim.csv"
TOTALS_PATH = ARCHIVE_DIR / "daily_totals.csv"

# Station attributes that change rarely; kept once in the dimension file.
DIM_COLUMNS = [
    "station_id",
    "station_name",
    "operator_license_no",
    "operator_name",
    "address",
    "latitude",
    "longitude",
    "first_seen",
    "last_seen",
]

# Measures that change day to day; written per day.
FACT_COLUMNS = [
    "station_id",
    "socket_count",
    "ac_socket_count",
    "dc_socket_count",
    "total_power_kw",
]

# Never written to the archive: may contain a natural person's name (KVKK).
EXCLUDED_FIELDS = ("sarjIstasyonuIsletmecisi",)


def archive_date(now: Optional[datetime] = None) -> str:
    """Returns the archive day label in Europe/Istanbul time."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(TZ_ISTANBUL).strftime("%Y-%m-%d")


def read_latest_manifest(data_dir: Path) -> Dict[str, Any]:
    """Reads the collector's latest_manifest.json. Raises if missing or unusable."""
    manifest_path = Path(data_dir) / "latest_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No collector manifest at {manifest_path}. Run the collector before building the archive."
        )
    with open(manifest_path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("status") != "success":
        raise ValueError(f"Latest manifest is not a successful snapshot: status={manifest.get('status')}")
    return manifest


def resolve_snapshot_path(manifest: Dict[str, Any], data_dir: Path) -> Path:
    """Resolves the snapshot file the manifest points at."""
    storage_path = manifest.get("storage_path")
    if storage_path:
        candidate = Path(storage_path)
        if candidate.exists():
            return candidate
    filename = manifest.get("filename")
    if filename:
        candidate = Path(data_dir) / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Snapshot file referenced by manifest not found (filename={filename}).")


def load_validated_frame(snapshot_path: Path) -> pd.DataFrame:
    """Loads a raw snapshot through the project's normal loading and validation pipeline."""
    raw_df, _ = load_dataset(snapshot_path, filename_hint=snapshot_path.name)
    raw_df = raw_df.drop(columns=[c for c in EXCLUDED_FIELDS if c in raw_df.columns], errors="ignore")
    validated_df, _ = validate_charging_dataset(raw_df)
    return validated_df


def build_station_facts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates the socket-level frame to one row per station.

    A station with no sockets is preserved with zero counts, matching the
    loader's behaviour of keeping socketless stations.
    """
    if df.empty or "station_id" not in df.columns:
        return pd.DataFrame(columns=FACT_COLUMNS)

    frame = df.dropna(subset=["station_id"]).copy()
    frame["station_id"] = frame["station_id"].astype(str)

    if "socket_id" in frame.columns:
        with_socket = frame.dropna(subset=["socket_id"]).drop_duplicates(subset=["station_id", "socket_id"])
    else:
        with_socket = frame.iloc[0:0]

    types = (
        with_socket["socket_type_normalized"]
        if "socket_type_normalized" in with_socket.columns
        else pd.Series(dtype=object)
    )
    powers = (
        pd.to_numeric(with_socket["power_kw_normalized"], errors="coerce")
        if "power_kw_normalized" in with_socket.columns
        else pd.Series(dtype=float)
    )

    measures = pd.DataFrame(
        {
            "station_id": with_socket["station_id"],
            "_is_ac": (types == "AC").astype(int) if len(types) else 0,
            "_is_dc": (types == "DC").astype(int) if len(types) else 0,
            "_power": powers if len(powers) else 0.0,
        }
    )

    grouped = measures.groupby("station_id", dropna=False).agg(
        socket_count=("station_id", "size"),
        ac_socket_count=("_is_ac", "sum"),
        dc_socket_count=("_is_dc", "sum"),
        total_power_kw=("_power", "sum"),
    )

    all_stations = pd.DataFrame({"station_id": frame["station_id"].drop_duplicates()})
    facts = all_stations.merge(grouped, on="station_id", how="left")
    for column in ("socket_count", "ac_socket_count", "dc_socket_count"):
        facts[column] = facts[column].fillna(0).astype(int)
    facts["total_power_kw"] = facts["total_power_kw"].fillna(0.0).round(2)

    return facts[FACT_COLUMNS].sort_values("station_id").reset_index(drop=True)


def build_station_attributes(df: pd.DataFrame) -> pd.DataFrame:
    """Extracts one row of slowly changing attributes per station."""
    attribute_columns = [c for c in DIM_COLUMNS if c not in ("first_seen", "last_seen")]
    if df.empty or "station_id" not in df.columns:
        return pd.DataFrame(columns=attribute_columns)

    frame = df.dropna(subset=["station_id"]).copy()
    frame["station_id"] = frame["station_id"].astype(str)
    for column in attribute_columns:
        if column not in frame.columns:
            frame[column] = pd.NA

    attributes = frame[attribute_columns].drop_duplicates(subset=["station_id"], keep="first")
    return attributes.sort_values("station_id").reset_index(drop=True)


def update_dimension(attributes: pd.DataFrame, day: str, dim_path: Optional[Path] = None) -> pd.DataFrame:
    """
    Merges today's station attributes into the dimension file.

    A station seen for the first time gets first_seen = today. Every station seen
    today gets last_seen = today. Stations absent today keep their previous
    last_seen, which is how a delisted station is recognised later.
    """
    dim_path = Path(dim_path) if dim_path is not None else DIM_PATH
    attribute_columns = [c for c in DIM_COLUMNS if c not in ("first_seen", "last_seen")]
    today = attributes.copy()
    today["station_id"] = today["station_id"].astype(str)

    if dim_path.exists():
        existing = pd.read_csv(dim_path, dtype={"station_id": str})
    else:
        existing = pd.DataFrame(columns=DIM_COLUMNS)

    merged = existing.set_index("station_id") if not existing.empty else pd.DataFrame(columns=DIM_COLUMNS[1:])
    if not merged.empty:
        merged.index = merged.index.astype(str)

    today_indexed = today.set_index("station_id")

    rows = []
    for station_id, attrs in today_indexed.iterrows():
        previous = merged.loc[station_id] if station_id in merged.index else None
        first_seen = previous["first_seen"] if previous is not None and pd.notna(previous.get("first_seen")) else day
        row = {"station_id": station_id, "first_seen": first_seen, "last_seen": day}
        for column in attribute_columns:
            if column == "station_id":
                continue
            row[column] = attrs.get(column)
        rows.append(row)

    seen_today = set(today_indexed.index)
    for station_id, previous in merged.iterrows():
        if station_id in seen_today:
            continue
        row = {"station_id": station_id}
        for column in DIM_COLUMNS[1:]:
            row[column] = previous.get(column)
        rows.append(row)

    dimension = pd.DataFrame(rows)
    dimension = dimension.reindex(columns=DIM_COLUMNS)
    return dimension.sort_values("station_id").reset_index(drop=True)


def build_totals_row(facts: pd.DataFrame, day: str, attributes: pd.DataFrame, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the one-row daily summary used for time-series reads."""
    operator_count = 0
    if "operator_license_no" in attributes.columns:
        operator_count = int(attributes["operator_license_no"].dropna().nunique())
    if operator_count == 0 and "operator_name" in attributes.columns:
        operator_count = int(attributes["operator_name"].dropna().nunique())

    return {
        "date": day,
        "station_count": int(len(facts)),
        "socket_count": int(facts["socket_count"].sum()),
        "ac_socket_count": int(facts["ac_socket_count"].sum()),
        "dc_socket_count": int(facts["dc_socket_count"].sum()),
        "total_power_kw": round(float(facts["total_power_kw"].sum()), 2),
        "operator_count": operator_count,
        "snapshot_id": manifest.get("snapshot_id", ""),
        "snapshot_sha256": manifest.get("sha256_hash", ""),
    }


def update_totals(row: Dict[str, Any], totals_path: Optional[Path] = None) -> pd.DataFrame:
    """Writes or replaces the row for this day, keeping one row per date."""
    totals_path = Path(totals_path) if totals_path is not None else TOTALS_PATH
    if totals_path.exists():
        totals = pd.read_csv(totals_path)
        totals = totals[totals["date"].astype(str) != row["date"]]
        totals = pd.concat([totals, pd.DataFrame([row])], ignore_index=True)
    else:
        totals = pd.DataFrame([row])
    return totals.sort_values("date").reset_index(drop=True)


def write_outputs(facts: pd.DataFrame, dimension: pd.DataFrame, totals: pd.DataFrame, day: str) -> Dict[str, str]:
    """Writes the three archive artefacts atomically."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    daily_path = DAILY_DIR / f"{day}.csv.gz"
    temp_daily = daily_path.with_suffix(daily_path.suffix + ".tmp")
    with gzip.open(temp_daily, "wt", encoding="utf-8", newline="") as handle:
        facts.to_csv(handle, index=False)
    os.replace(temp_daily, daily_path)

    for frame, path in ((dimension, DIM_PATH), (totals, TOTALS_PATH)):
        temp_path = path.with_suffix(path.suffix + ".tmp")
        frame.to_csv(temp_path, index=False, encoding="utf-8", lineterminator="\n")
        os.replace(temp_path, path)

    return {
        "daily": str(daily_path),
        "dimension": str(DIM_PATH),
        "totals": str(TOTALS_PATH),
    }


def build_archive(data_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Runs one archive build from the collector's latest verified snapshot."""
    if data_dir is None:
        data_dir = Path(os.getenv("LOCAL_DATA_DIR", REPO_ROOT / "_local_data"))

    day = archive_date(now)
    manifest = read_latest_manifest(data_dir)
    snapshot_path = resolve_snapshot_path(manifest, data_dir)

    validated = load_validated_frame(snapshot_path)
    facts = build_station_facts(validated)
    attributes = build_station_attributes(validated)

    if facts.empty:
        raise ValueError("Snapshot produced no station rows; archive not written.")

    dimension = update_dimension(attributes, day)
    totals_row = build_totals_row(facts, day, attributes, manifest)
    totals = update_totals(totals_row)
    paths = write_outputs(facts, dimension, totals, day)

    # The dated series above never changes; this is the single current
    # observation the dashboard reads instead of calling the endpoint.
    current = repo_snapshot.write_snapshot(validated, manifest)
    paths["current"] = str(repo_snapshot.SNAPSHOT_PATH)

    new_stations = int((dimension["first_seen"] == day).sum())
    return {
        "status": "success",
        "date": day,
        "snapshot_id": manifest.get("snapshot_id"),
        "stations_in_archive": int(len(dimension)),
        "new_station_ids_today": new_stations,
        "totals": totals_row,
        "current_snapshot": current,
        "paths": paths,
    }


def main() -> int:
    try:
        result = build_archive()
    except Exception as error:  # noqa: BLE001 - CLI boundary reports and exits
        print(f"[Archive] Failed: {type(error).__name__}: {error}")
        return 1

    totals = result["totals"]
    print(f"[Archive] Date            : {result['date']}")
    print(f"[Archive] Stations        : {totals['station_count']}")
    print(f"[Archive] Sockets         : {totals['socket_count']}")
    print(f"[Archive] Installed power : {totals['total_power_kw']} kW")
    print(f"[Archive] First seen today: {result['new_station_ids_today']}")
    print(f"[Archive] Daily file      : {result['paths']['daily']}")
    print(f"[Archive] Current snapshot: {result['paths']['current']} "
          f"({result['current_snapshot']['row_count']} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
