"""
CLI Entrypoint for Daily EPDK Collection Task.
Usage:
    python -m src.collector.run_collector

Authoritative gating:
    Execution is strictly gated by the environment variable EPDK_COLLECTION_ENABLED.
    If unset, empty, or not equal to 'true', the process immediately exits with code 0
    without making any HTTP requests or touching storage.
"""

import os
import sys
from pathlib import Path

from src.collector.api_client import EPDKApiClient
from src.collector.validator import CollectorValidator
from src.collector.storage import LocalStorageAdapter, S3StorageAdapter
from src.collector.collector_service import CollectorService


def is_collection_enabled() -> bool:
    """Returns True ONLY if EPDK_COLLECTION_ENABLED is explicitly set to 'true', '1', or 'yes'."""
    val = os.getenv("EPDK_COLLECTION_ENABLED", "").strip().lower()
    return val in ("true", "1", "yes")


def main():
    # Authoritative gating: no bypass, no --force flag
    if not is_collection_enabled():
        print(
            "[EPDK Collector] Collection is disabled (EPDK_COLLECTION_ENABLED is unset or not 'true'). "
            "Exiting without making any HTTP or storage calls."
        )
        sys.exit(0)

    print("[EPDK Collector] Starting authorized daily collection cycle...")

    # Select storage backend
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "s3":
        print("[EPDK Collector] Using S3StorageAdapter backend.")
        storage = S3StorageAdapter()
    else:
        print("[EPDK Collector] Using LocalStorageAdapter backend.")
        storage = LocalStorageAdapter()

    api_client = EPDKApiClient()
    validator = CollectorValidator(min_stations_threshold=int(os.getenv("MIN_STATIONS_THRESHOLD", "50")))
    service = CollectorService(api_client=api_client, validator=validator, storage=storage)

    result = service.run_collection()
    status = result.get("status")
    print(f"[EPDK Collector] Result: {status}")

    if status == "success":
        print(f"  Snapshot ID : {result.get('snapshot_id')}")
        print(f"  Stations    : {result.get('station_count')}")
        print(f"  Sockets     : {result.get('socket_count')}")
        print(f"  SHA-256     : {result.get('sha256_hash')[:16]}...")
        print(f"  Stored at   : {result.get('storage_path')}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  Warning     : {w}")
        sys.exit(0)
    elif status == "skipped":
        print(f"  Reason      : {result.get('reason')}")
        sys.exit(0)
    else:
        print(f"  Error Stage : {result.get('stage')}")
        print(f"  Details     : {result.get('details')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
