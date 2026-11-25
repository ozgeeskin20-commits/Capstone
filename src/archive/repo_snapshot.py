"""
Repository Snapshot.

Keeps the most recent socket-level observation inside the repository so that the
dashboard has current data to read without calling the EPDK endpoint itself.

The scheduled workflow writes these two files once a day, overwriting them:

    data/current/sockets_latest.csv   Socket-level rows, in the project's
                                      canonical column names. Written
                                      uncompressed and sorted so that
                                      day-to-day revisions delta-compress.
    data/current/manifest.json        Provenance for that file: when it was
                                      collected, from which snapshot, and the
                                      row counts a reader should expect.

This is the current observation only; it is overwritten daily and carries no
history. The dated series lives in `data/archive/` and is never overwritten.

The manifest deliberately stores no absolute path, because each contributor
clones the repository to a different location. `read_manifest` resolves the
snapshot's location at read time and fills `storage_path` in, which is what
`src.auto_collector.load_snapshot_from_manifest` expects.

Privacy: the written columns carry no field that can hold a natural person's
name. Only the licensed network operator's title and licence number are kept.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CURRENT_DIR = Path(os.getenv("CURRENT_DATA_DIR", REPO_ROOT / "data" / "current"))
SNAPSHOT_PATH = CURRENT_DIR / "sockets_latest.csv"
MANIFEST_PATH = CURRENT_DIR / "manifest.json"

# Canonical column names, so that reloading through `load_dataset` requires no
# renaming and the dashboard sees exactly the frame it would see from the raw
# payload. Address and coordinates are not carried; no current view uses them,
# and `data/archive/stations_dim.csv` holds them per station.
SNAPSHOT_COLUMNS = [
    "station_id",
    "station_name",
    "operator_name",
    "operator_license_no",
    "socket_id",
    "socket_type",
    "socket_sub_type",
    "power_kw",
]


def write_snapshot(
    validated_df: pd.DataFrame,
    source_manifest: Dict[str, Any],
    snapshot_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Writes the current socket-level snapshot and its manifest.

    `validated_df` is the frame the archive builder already holds: loaded,
    schema-normalized and validated. Only the columns above are written, so
    validation artefacts and unused fields stay out of the repository.
    """
    snapshot_path = Path(snapshot_path) if snapshot_path is not None else SNAPSHOT_PATH
    manifest_path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    frame = validated_df.copy()
    for column in SNAPSHOT_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[SNAPSHOT_COLUMNS]

    # A stable order keeps the daily revision a small diff rather than a rewrite.
    frame = frame.sort_values(["station_id", "socket_id"], na_position="last").reset_index(drop=True)

    temp_snapshot = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
    frame.to_csv(temp_snapshot, index=False, encoding="utf-8", lineterminator="\n")
    os.replace(temp_snapshot, snapshot_path)

    timestamp = source_manifest.get("timestamp_utc") or datetime.now(timezone.utc).isoformat()
    manifest = {
        "status": "success",
        "snapshot_id": source_manifest.get("snapshot_id", ""),
        "timestamp_utc": timestamp,
        "snapshot_timestamp": timestamp,
        "station_count": int(frame["station_id"].dropna().nunique()),
        "socket_count": int(frame["socket_id"].dropna().nunique()),
        "row_count": int(len(frame)),
        "filename": snapshot_path.name,
        "source_sha256": source_manifest.get("sha256_hash", ""),
        "columns": SNAPSHOT_COLUMNS,
        "note": (
            "Current observation only; overwritten daily. The dated series is in data/archive/."
        ),
    }

    temp_manifest = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    with open(temp_manifest, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp_manifest, manifest_path)

    return manifest


def read_manifest(
    snapshot_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """
    Reads the committed manifest and resolves the snapshot's location.

    Returns None when either file is missing or unreadable, or when the two
    disagree, so that a caller falls through to its next source rather than
    failing. `storage_path` is filled in here, not stored in the file, because
    the repository sits at a different absolute path on every machine.
    """
    snapshot_path = Path(snapshot_path) if snapshot_path is not None else SNAPSHOT_PATH
    manifest_path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH

    if not manifest_path.exists() or not snapshot_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(manifest, dict) or manifest.get("status") != "success":
        return None

    resolved = dict(manifest)
    resolved["storage_path"] = str(snapshot_path.resolve())
    resolved["filename"] = snapshot_path.name
    return resolved


def describe(manifest: Dict[str, Any]) -> Tuple[int, int]:
    """Returns the station and socket counts a reader should expect."""
    return int(manifest.get("station_count", 0)), int(manifest.get("socket_count", 0))
