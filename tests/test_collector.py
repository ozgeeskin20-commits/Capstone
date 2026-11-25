"""
Comprehensive Unit & Mock Integration Tests for EPDK Daily Collector.
Tests all required operational scenarios:
- Successful collection and compressed persistence.
- Timeout, rate limiting (429 Retry-After) and failed HTTP responses.
- Empty, partial, truncated, and malformed JSON responses.
- Storage failure handling.
- Retention of the previous successful snapshot upon failure.
- Verifiable snapshot and metadata association (SHA-256).
- Repeated / overlapping execution protection (concurrency lock).
- Dashboard retrieval from storage manifest.
- S3StorageAdapter operations using a mocked client.
"""

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest

from src.collector.api_client import EPDKApiClient, FetchResult
from src.collector.validator import CollectorValidator, ValidationResult
from src.collector.storage import LocalStorageAdapter, S3StorageAdapter
from src.collector.collector_service import CollectorService
from src.data_loader import load_dataset


@pytest.fixture
def valid_epdk_payload():
    """Generates a valid EPDK payload with 60 stations and sockets."""
    stations = []
    for i in range(60):
        stations.append({
            "sarjIstasyonuNo": f"STN-{i:04d}",
            "istasyonAdi": f"Station {i}",
            "sarjAgiIsletmecisiUnvan": "ZES" if i % 2 == 0 else "Trugo",
            "soketler": [
                {
                    "soketNo": f"SCK-{i:04d}-1",
                    "soketTipi": "AC",
                    "soketTuru": "AC_TYPE2",
                    "soketGucu": 22.0,
                },
                {
                    "soketNo": f"SCK-{i:04d}-2",
                    "soketTipi": "DC",
                    "soketTuru": "DC_CCS",
                    "soketGucu": 180.0,
                },
            ]
        })
    return json.dumps(stations).encode("utf-8")


# ------------------------------------------------------------------------------
# 1. Successful collection and persistence
# ------------------------------------------------------------------------------
def test_successful_collection_and_persistence(tmp_path, valid_epdk_payload):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    validator = CollectorValidator(min_stations_threshold=50)

    # Mock API client returning valid payload
    mock_client = MagicMock(spec=EPDKApiClient)
    mock_client.endpoint_url = "https://mock.epdk.test/api"
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={"Content-Type": "application/json"},
        duration_seconds=1.2,
    )

    lock_file = tmp_path / ".collector.lock"
    service = CollectorService(
        api_client=mock_client,
        validator=validator,
        storage=storage,
        lock_file_path=lock_file,
    )

    report = service.run_collection()
    assert report["status"] == "success"
    assert report["station_count"] == 60
    assert report["socket_count"] == 120

    # Verify latest manifest
    manifest = storage.get_latest_manifest()
    assert manifest is not None
    assert manifest["status"] == "success"
    assert manifest["station_count"] == 60
    assert manifest["sha256_hash"] == hashlib.sha256(valid_epdk_payload).hexdigest()

    # Verify compressed file exists and can be decompressed
    saved_file = Path(report["storage_path"])
    assert saved_file.exists()
    assert saved_file.name.endswith(".json.gz")
    with gzip.open(saved_file, "rb") as gz:
        decompressed = gz.read()
    assert decompressed == valid_epdk_payload


# ------------------------------------------------------------------------------
# 2. Timeout, rate limiting (429 Retry-After) and failed HTTP responses
# ------------------------------------------------------------------------------
def test_timeout_and_failed_responses(tmp_path):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    mock_client = MagicMock(spec=EPDKApiClient)
    mock_client.fetch.return_value = FetchResult(
        status_code=502,
        content=b"Bad Gateway",
        headers={},
        duration_seconds=2.0,
        error_message="HTTP 502: Bad Gateway",
    )

    service = CollectorService(api_client=mock_client, storage=storage, lock_file_path=tmp_path / ".lock")
    report = service.run_collection()

    assert report["status"] == "failed"
    assert report["stage"] == "http_fetch"
    assert storage.get_latest_manifest() is None

    # Check failure log
    assert storage.failure_log_path.exists()
    lines = storage.failure_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "HTTP 502" in lines[0]


def test_rate_limiting_429_with_retry_after(tmp_path):
    client = EPDKApiClient(endpoint_url="https://mock.test/api", max_retries=2, max_retry_after=5)

    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429
    mock_resp_429.content = b"Too Many Requests"
    mock_resp_429.headers = {"Retry-After": "2"}
    mock_resp_429.reason = "Too Many Requests"

    mock_session = MagicMock()
    mock_session.request.return_value = mock_resp_429

    with patch("time.sleep") as mock_sleep:
        res = client.fetch(session=mock_session)
        assert res.status_code == 429
        assert res.retry_after == 2
        # Backoff or retry-after slept
        assert mock_sleep.called


# ------------------------------------------------------------------------------
# 3. Empty, partial, truncated, and malformed JSON responses
# ------------------------------------------------------------------------------
def test_empty_response_validation():
    validator = CollectorValidator()
    res = validator.validate_payload(b"")
    assert not res.is_structurally_valid
    assert "Empty payload" in res.fatal_error


def test_malformed_json_validation():
    validator = CollectorValidator()
    res = validator.validate_payload(b"{broken json: 'val'")
    assert not res.is_structurally_valid
    assert "Malformed JSON" in res.fatal_error


def test_partial_below_threshold_validation():
    validator = CollectorValidator(min_stations_threshold=50)
    # Only 5 stations
    payload = json.dumps([{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(5)]).encode("utf-8")
    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "below minimum safety threshold" in res.fatal_error


def test_api_error_dict_payload():
    validator = CollectorValidator()
    payload = json.dumps({"error": "Unauthorized access", "status": 401}).encode("utf-8")
    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "API returned error envelope" in res.fatal_error


# ------------------------------------------------------------------------------
# 4. Storage failure during write
# ------------------------------------------------------------------------------
def test_storage_failure_handling(tmp_path, valid_epdk_payload):
    storage = MagicMock(spec=LocalStorageAdapter)
    storage.save_snapshot.side_effect = IOError("Disk full or permission denied")
    storage.record_failure = MagicMock()
    storage.get_latest_manifest.return_value = None

    mock_client = MagicMock()
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={},
        duration_seconds=1.0,
    )

    service = CollectorService(
        api_client=mock_client,
        validator=CollectorValidator(min_stations_threshold=50),
        storage=storage,
        lock_file_path=tmp_path / ".lock",
    )

    report = service.run_collection()
    assert report["status"] == "failed"
    assert report["stage"] == "storage_save"
    assert not storage.update_latest_manifest.called
    assert storage.record_failure.called


# ------------------------------------------------------------------------------
# 5. Retention of the previous successful snapshot upon failure
# ------------------------------------------------------------------------------
def test_retention_of_previous_successful_snapshot(tmp_path, valid_epdk_payload):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    validator = CollectorValidator(min_stations_threshold=50)

    # 1. First collection succeeds
    mock_client = MagicMock()
    mock_client.endpoint_url = "https://mock.epdk.test"
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={},
        duration_seconds=1.0,
    )
    service = CollectorService(
        api_client=mock_client,
        validator=validator,
        storage=storage,
        lock_file_path=tmp_path / ".lock",
    )
    first_report = service.run_collection()
    assert first_report["status"] == "success"
    first_sha = first_report["sha256_hash"]

    # Manifest points to first run
    m1 = storage.get_latest_manifest()
    assert m1["sha256_hash"] == first_sha

    # 2. Second collection fails due to empty/corrupted response
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=b"[]",  # empty array
        headers={},
        duration_seconds=0.5,
    )
    second_report = service.run_collection()
    assert second_report["status"] == "failed"

    # Crucial: Manifest STILL points to the first successful snapshot!
    m2 = storage.get_latest_manifest()
    assert m2["sha256_hash"] == first_sha
    assert m2["snapshot_id"] == first_report["snapshot_id"]


# ------------------------------------------------------------------------------
# 6. Verifiable snapshot and metadata association (SHA-256)
# ------------------------------------------------------------------------------
def test_snapshot_metadata_sha256_association(tmp_path, valid_epdk_payload):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    mock_client = MagicMock()
    mock_client.endpoint_url = "https://mock.test"
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={},
        duration_seconds=1.0,
    )

    service = CollectorService(
        api_client=mock_client,
        validator=CollectorValidator(min_stations_threshold=50),
        storage=storage,
        lock_file_path=tmp_path / ".lock",
    )
    report = service.run_collection()
    manifest = storage.get_latest_manifest()

    # Read back snapshot file
    stored_path = Path(report["storage_path"])
    raw_uncompressed = storage.get_snapshot_bytes(str(stored_path))

    computed_sha = hashlib.sha256(raw_uncompressed).hexdigest()
    assert computed_sha == manifest["sha256_hash"]
    assert computed_sha == report["sha256_hash"]


# ------------------------------------------------------------------------------
# 7. Repeated / overlapping execution protection (concurrency lock)
# ------------------------------------------------------------------------------
def test_overlapping_execution_protection(tmp_path, valid_epdk_payload):
    lock_file = tmp_path / ".active.lock"
    # Pre-create lock file simulating an ongoing run
    lock_file.write_text("pid=99999\nts=2026-11-05T10:00:00+00:00", encoding="utf-8")

    mock_client = MagicMock()
    service = CollectorService(
        api_client=mock_client,
        storage=LocalStorageAdapter(base_dir=tmp_path),
        lock_file_path=lock_file,
    )

    report = service.run_collection()
    assert report["status"] == "skipped"
    assert "lock held" in report["reason"]
    assert not mock_client.fetch.called


# ------------------------------------------------------------------------------
# 8. Dashboard retrieval from storage manifest
# ------------------------------------------------------------------------------
def test_dashboard_retrieval_from_manifest(tmp_path, valid_epdk_payload):
    storage = LocalStorageAdapter(base_dir=tmp_path)
    metadata = {
        "snapshot_id": "20261105_090000",
        "timestamp_utc": "2026-11-05T09:00:00+00:00",
        "station_count": 60,
    }
    path_str = storage.save_snapshot("20261105_090000", valid_epdk_payload, metadata)

    manifest = {
        "snapshot_id": "20261105_090000",
        "filename": "epdk_raw_20261105_090000.json.gz",
        "sha256_hash": metadata["sha256_hash"],
        "storage_path": path_str,
        "snapshot_timestamp": "2026-11-05T09:00:00+00:00",
    }
    storage.update_latest_manifest(manifest)

    # Dashboard retrieval simulation
    retrieved_manifest = storage.get_latest_manifest()
    assert retrieved_manifest is not None

    snapshot_bytes = storage.get_snapshot_bytes(retrieved_manifest["storage_path"])
    import io
    df, mappings = load_dataset(io.BytesIO(snapshot_bytes), filename_hint=retrieved_manifest["filename"])

    assert len(df) == 120  # 60 stations * 2 sockets
    assert df["station_id"].nunique() == 60
    assert df["socket_id"].nunique() == 120


# ------------------------------------------------------------------------------
# 9. Stateful Fake S3 Client and S3StorageAdapter Operations
# ------------------------------------------------------------------------------
class FakeClientError(Exception):
    """Simulates botocore.exceptions.ClientError with structured response dictionary."""
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(f"An error occurred ({code}) when calling the operation: {message}")
        self.response = {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": status_code}
        }


class StatefulFakeS3Client:
    """
    In-memory stateful S3 client simulating conditional writes (IfNoneMatch, IfMatch),
    ETags, exclusive creation, optimistic concurrency, and genuine S3 errors.
    """
    def __init__(self):
        self.objects = {}  # key -> {"Body": bytes, "ETag": str, "ContentType": str, "Metadata": dict}
        self.call_history = []

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: Any,
        ContentType: Optional[str] = None,
        Metadata: Optional[Dict[str, str]] = None,
        IfNoneMatch: Optional[str] = None,
        IfMatch: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.call_history.append({
            "action": "put_object",
            "Bucket": Bucket,
            "Key": Key,
            "IfNoneMatch": IfNoneMatch,
            "IfMatch": IfMatch,
        })

        if isinstance(Body, str):
            body_bytes = Body.encode("utf-8")
        elif hasattr(Body, "read"):
            body_bytes = Body.read()
        else:
            body_bytes = bytes(Body)

        # 1. Enforce IfNoneMatch="*" (object must NOT exist)
        if IfNoneMatch == "*":
            if Key in self.objects:
                raise FakeClientError(
                    "PreconditionFailed",
                    "At least one of the pre-conditions you specified did not hold",
                    412
                )

        # 2. Enforce IfMatch=<etag> (object must exist and ETag must match)
        if IfMatch is not None:
            if Key not in self.objects:
                raise FakeClientError("PreconditionFailed", "Target object not found for IfMatch", 412)
            existing_etag = self.objects[Key]["ETag"].strip('"')
            target_etag = IfMatch.strip('"')
            if existing_etag != target_etag:
                raise FakeClientError(
                    "PreconditionFailed",
                    f"ETag mismatch: current {existing_etag} != expected {target_etag}",
                    412
                )

        etag = hashlib.md5(body_bytes).hexdigest()
        self.objects[Key] = {
            "Body": body_bytes,
            "ETag": f'"{etag}"',
            "ContentType": ContentType or "application/octet-stream",
            "Metadata": Metadata or {},
        }
        return {"ETag": f'"{etag}"'}

    def get_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        self.call_history.append({"action": "get_object", "Bucket": Bucket, "Key": Key})
        if Key not in self.objects:
            raise FakeClientError("NoSuchKey", "The specified key does not exist.", 404)

        import io
        item = self.objects[Key]
        return {
            "Body": io.BytesIO(item["Body"]),
            "ETag": item["ETag"],
            "ContentType": item["ContentType"],
            "Metadata": item["Metadata"],
        }

    def head_object(self, Bucket: str, Key: str) -> Dict[str, Any]:
        self.call_history.append({"action": "head_object", "Bucket": Bucket, "Key": Key})
        if Key not in self.objects:
            raise FakeClientError("404", "Not Found", 404)
        return {
            "ETag": self.objects[Key]["ETag"],
            "ContentType": self.objects[Key]["ContentType"],
            "Metadata": self.objects[Key]["Metadata"],
        }


def test_s3_storage_adapter_mocked():
    """Verifies standard save and retrieve using StatefulFakeS3Client."""
    fake_client = StatefulFakeS3Client()
    adapter = S3StorageAdapter(
        bucket_name="my-charging-bucket",
        access_key_id="dummy-key",
        secret_access_key="dummy-secret",
        prefix="epdk/",
        client=fake_client,
    )

    raw_data = b'{"stations": []}'
    metadata = {}
    s3_key = adapter.save_snapshot("20261105_090000", raw_data, metadata)

    assert "epdk/snapshots/epdk_raw_20261105_090000.json.gz" in s3_key
    assert len(fake_client.objects) == 2  # data + metadata

    # Test initial manifest update
    manifest = {
        "snapshot_id": "20261105_090000",
        "timestamp_utc": "2026-11-05T09:00:00+00:00",
    }
    assert adapter.update_latest_manifest(manifest) is True
    assert "epdk/latest_manifest.json" in fake_client.objects
    assert adapter.get_latest_manifest() == manifest


# ------------------------------------------------------------------------------
# 10. Dedicated Section 7 Regression Tests
# ------------------------------------------------------------------------------
def test_declared_num_rows_mismatch_rejected():
    """Validates that declared numRows != actual stations length is rejected."""
    validator = CollectorValidator(min_stations_threshold=10)
    # Envelope claims 17087, but data only has 10 stations
    payload = json.dumps({
        "statusCode": 200,
        "numRows": 17087,
        "data": [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(10)]
    }).encode("utf-8")
    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "Declared record count mismatch" in res.fatal_error


def test_epdk_error_envelope_statusCode_500_rejected():
    """Validates that an error envelope with statusCode=500 is rejected even with large data array."""
    validator = CollectorValidator(min_stations_threshold=10)
    payload = json.dumps({
        "statusCode": 500,
        "error": "Internal Gateway Failure",
        "data": [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(60)]
    }).encode("utf-8")
    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "API returned error envelope" in res.fatal_error


def test_station_list_with_integers_rejected():
    """Validates that a list containing non-dict elements is rejected instead of counting them."""
    validator = CollectorValidator(min_stations_threshold=5)
    # 1 valid station dict + 9 integers
    items = [{"sarjIstasyonuNo": "STN-1", "soketler": []}] + [12345] * 9
    payload = json.dumps(items).encode("utf-8")
    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "is not a dictionary" in res.fatal_error


def test_socket_list_with_invalid_types_rejected():
    """Validates that non-dict items inside soketler are rejected."""
    validator = CollectorValidator(min_stations_threshold=1)
    payload = json.dumps([
        {
            "sarjIstasyonuNo": "STN-1",
            "istasyonAdi": "Alpha",
            "soketler": ["invalid_socket_string"]
        }
    ]).encode("utf-8")
    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "contains non-dict socket" in res.fatal_error


def test_corrupted_stored_bytes_aborts_promotion(tmp_path, valid_epdk_payload):
    """
    Verifies that if stored bytes on disk are corrupted, read-back verification fails,
    aborts manifest promotion, and records failure.
    """
    storage = LocalStorageAdapter(base_dir=tmp_path)
    mock_client = MagicMock()
    mock_client.endpoint_url = "https://mock.test"
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={},
        duration_seconds=1.0,
    )

    # Patch storage.get_snapshot_bytes to simulate byte corruption during read-back
    with patch.object(storage, "get_snapshot_bytes", return_value=b"CORRUPTED_TAMPERED_DATA"):
        service = CollectorService(
            api_client=mock_client,
            validator=CollectorValidator(min_stations_threshold=50),
            storage=storage,
            lock_file_path=tmp_path / ".lock",
        )
        report = service.run_collection()
        assert report["status"] == "failed"
        assert report["stage"] == "read_back_verification"
        assert storage.get_latest_manifest() is None


def test_failed_manifest_update_aborts(tmp_path, valid_epdk_payload):
    """
    Verifies that if manifest update returns False (e.g. attempting to overwrite newer with older),
    collection reports failure and failure is recorded.
    """
    storage = LocalStorageAdapter(base_dir=tmp_path)
    # Set an existing newer manifest
    storage.update_latest_manifest({
        "snapshot_id": "99991231_235959",
        "timestamp_utc": "2099-12-31T23:59:59+00:00",
    })

    mock_client = MagicMock()
    mock_client.endpoint_url = "https://mock.test"
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={},
        duration_seconds=1.0,
    )

    service = CollectorService(
        api_client=mock_client,
        validator=CollectorValidator(min_stations_threshold=50),
        storage=storage,
        lock_file_path=tmp_path / ".lock",
    )
    report = service.run_collection()
    assert report["status"] == "failed"
    assert report["stage"] == "manifest_promotion"


def test_snapshot_collision_create_only_raises(tmp_path, valid_epdk_payload):
    """
    Verifies that calling save_snapshot with an existing snapshot ID raises FileExistsError
    and does NOT overwrite the original file.
    """
    storage = LocalStorageAdapter(base_dir=tmp_path)
    metadata = {"ts": "first"}
    storage.save_snapshot("COLLISION_TEST", valid_epdk_payload, metadata)

    # Second call with same ID must raise FileExistsError
    metadata2 = {"ts": "second"}
    with pytest.raises(FileExistsError):
        storage.save_snapshot("COLLISION_TEST", b"DIFFERENT_PAYLOAD", metadata2)

    # Verify original bytes remain untouched
    stored_bytes = storage.get_snapshot_bytes("epdk_raw_COLLISION_TEST.json.gz")
    assert stored_bytes == valid_epdk_payload


def test_concurrent_exclusive_lock_acquisition(tmp_path):
    """
    Verifies that exclusive atomic lock acquisition prevents a second execution from proceeding.
    """
    lock_file = tmp_path / ".atomic.lock"
    service1 = CollectorService(lock_file_path=lock_file)
    service2 = CollectorService(lock_file_path=lock_file)

    assert service1._acquire_lock() is True
    # Second acquisition fails
    assert service2._acquire_lock() is False

    # service2 cannot release service1's lock
    service2._release_lock()
    assert lock_file.exists()

    # service1 releases cleanly
    service1._release_lock()
    assert not lock_file.exists()


def test_disabled_collector_makes_no_calls(monkeypatch):
    """
    Proves that when EPDK_COLLECTION_ENABLED is unset or false,
    run_collector.main() makes 0 calls to HTTP and 0 calls to storage.
    """
    import os
    from src.collector import run_collector

    monkeypatch.setenv("EPDK_COLLECTION_ENABLED", "false")
    mock_http = MagicMock()
    mock_storage = MagicMock()

    with patch("requests.request", mock_http), patch("src.collector.storage.LocalStorageAdapter", mock_storage):
        with pytest.raises(SystemExit) as exc_info:
            run_collector.main()
        assert exc_info.value.code == 0

    assert not mock_http.called
    assert not mock_storage.called


# ------------------------------------------------------------------------------
# 11. Stateful S3 Race and Atomic Concurrency Tests
# ------------------------------------------------------------------------------
def test_s3_two_writers_creating_same_snapshot_key():
    """
    Verifies that when two writers attempt to create the exact same snapshot key,
    the second writer encounters a 412 PreconditionFailed via IfNoneMatch="*"
    and raises FileExistsError without overwriting the first snapshot.
    """
    fake_s3 = StatefulFakeS3Client()
    adapter1 = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)
    adapter2 = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)

    raw_bytes1 = b'{"stations": [{"id": 1}]}'
    raw_bytes2 = b'{"stations": [{"id": 2}]}'

    # Writer 1 succeeds
    key1 = adapter1.save_snapshot("COLLISION_KEY", raw_bytes1, {})
    assert key1 in fake_s3.objects

    # Writer 2 attempts identical snapshot ID
    with pytest.raises(FileExistsError) as exc_info:
        adapter2.save_snapshot("COLLISION_KEY", raw_bytes2, {})
    assert "S3 snapshot collision (atomic IfNoneMatch failed)" in str(exc_info.value)

    # Verify original bytes remain intact (uncompressed in snapshot)
    read_back = adapter1.get_snapshot_bytes(key1)
    assert read_back == raw_bytes1


def test_s3_two_writers_creating_first_manifest():
    """
    Verifies that when two writers race to create the first manifest:
    - Writer 1 succeeds using IfNoneMatch="*".
    - Writer 2 receives 412 PreconditionFailed, rereads the manifest,
      observes that candidate timestamp is older than Writer 1's, and safely aborts.
    - Writer 1's manifest is preserved.
    """
    fake_s3 = StatefulFakeS3Client()
    adapter1 = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)
    adapter2 = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)

    manifest_writer1 = {
        "snapshot_id": "SNAP_W1",
        "timestamp_utc": "2026-11-05T09:00:00+00:00",
        "station_count": 100,
    }
    manifest_writer2 = {
        "snapshot_id": "SNAP_W2",
        "timestamp_utc": "2026-11-05T08:50:00+00:00",  # older candidate
        "station_count": 80,
    }

    # Both see no manifest initially
    assert adapter1.get_latest_manifest() is None
    assert adapter2.get_latest_manifest() is None

    # Writer 1 writes first
    assert adapter1.update_latest_manifest(manifest_writer1) is True

    # Writer 2 attempts write: encounters 412 on IfNoneMatch="*", rereads, sees W1 is newer, returns False
    assert adapter2.update_latest_manifest(manifest_writer2) is False

    # Writer 1's manifest remains in place
    current = adapter1.get_latest_manifest()
    assert current["snapshot_id"] == "SNAP_W1"
    assert current["timestamp_utc"] == "2026-11-05T09:00:00+00:00"


def test_s3_newer_manifest_appearing_between_older_writer_read_and_write():
    """
    Verifies that when a newer manifest is written between an older writer's read and write,
    the older writer's conditional PutObject (IfMatch=<old_etag>) fails with 412,
    and upon reread the older writer preserves the newer manifest.
    """
    fake_s3 = StatefulFakeS3Client()
    adapter_older = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)
    adapter_newer = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)

    initial_manifest = {
        "snapshot_id": "INITIAL",
        "timestamp_utc": "2026-11-05T08:00:00+00:00",
    }
    adapter_older.update_latest_manifest(initial_manifest)

    # Older writer reads current manifest (at 08:00)
    current_manifest, old_etag = adapter_older.get_manifest_with_etag()
    assert old_etag is not None

    # Concurrently, a newer writer writes a newer manifest (at 09:00)
    newer_manifest = {
        "snapshot_id": "NEWER_WINNER",
        "timestamp_utc": "2026-11-05T09:00:00+00:00",
    }
    assert adapter_newer.update_latest_manifest(newer_manifest) is True

    # Older writer now attempts to commit candidate (at 08:30 < 09:00)
    candidate_older = {
        "snapshot_id": "OLDER_CANDIDATE",
        "timestamp_utc": "2026-11-05T08:30:00+00:00",
    }
    # update_latest_manifest will fail conditional write on old_etag, reread, see 09:00 > 08:30, and return False
    assert adapter_older.update_latest_manifest(candidate_older) is False

    # Verify winning newer manifest is preserved
    final_manifest = adapter_older.get_latest_manifest()
    assert final_manifest["snapshot_id"] == "NEWER_WINNER"
    assert final_manifest["timestamp_utc"] == "2026-11-05T09:00:00+00:00"


def test_s3_permission_and_server_errors_during_reads():
    """
    Verifies that permission errors (AccessDenied / 403), server errors (500 / timeouts),
    and malformed manifests are NOT converted into an empty repository state (None).
    """
    fake_s3 = StatefulFakeS3Client()
    adapter = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)

    # 1. AccessDenied error during read
    def raise_access_denied(*args, **kwargs):
        raise FakeClientError("AccessDenied", "User does not have s3:GetObject permission", 403)

    with patch.object(fake_s3, "get_object", side_effect=raise_access_denied):
        with pytest.raises(PermissionError) as exc_info:
            adapter.get_latest_manifest()
        assert "Access denied" in str(exc_info.value)

    # 2. Server internal error (500)
    def raise_server_error(*args, **kwargs):
        raise FakeClientError("InternalError", "We encountered an internal error. Please try again.", 500)

    with patch.object(fake_s3, "get_object", side_effect=raise_server_error):
        with pytest.raises(Exception) as exc_info:
            adapter.get_latest_manifest()
        assert "InternalError" in str(exc_info.value)

    # 3. Malformed JSON manifest in S3
    fake_s3.objects["epdk/latest_manifest.json"] = {
        "Body": b"NOT_VALID_JSON{abc",
        "ETag": '"etag_corrupt"',
        "ContentType": "application/json",
        "Metadata": {},
    }
    with pytest.raises(ValueError) as exc_info:
        adapter.get_latest_manifest()
    assert "Malformed manifest JSON in S3" in str(exc_info.value)


def test_s3_precondition_failures_without_unconditional_fallback():
    """
    Verifies that when precondition failures occur, S3StorageAdapter NEVER falls back
    to an unconditional put_object (without IfMatch or IfNoneMatch).
    """
    fake_s3 = StatefulFakeS3Client()
    adapter = S3StorageAdapter(bucket_name="test-bkt", prefix="epdk/", client=fake_s3)

    # Set existing manifest with timestamp 09:00
    adapter.update_latest_manifest({
        "snapshot_id": "BASE",
        "timestamp_utc": "2026-11-05T09:00:00+00:00",
    })

    # Clear history and attempt update with older timestamp (08:00)
    fake_s3.call_history.clear()
    res = adapter.update_latest_manifest({
        "snapshot_id": "OLDER",
        "timestamp_utc": "2026-11-05T08:00:00+00:00",
    })
    assert res is False

    # Check all put_object calls in history
    for call in fake_s3.call_history:
        if call["action"] == "put_object" and "latest_manifest" in call["Key"]:
            has_conditional = call["IfNoneMatch"] is not None or call["IfMatch"] is not None
            assert has_conditional, f"Found unconditional put_object call: {call}"


# ------------------------------------------------------------------------------
# 12. API Envelope Validation Defect Regression Tests
# ------------------------------------------------------------------------------
def test_envelope_successful_response_with_nonempty_errors_rejected():
    """
    Verifies that a response with statusCode=200 but nonempty error/errors list is rejected.
    """
    validator = CollectorValidator(min_stations_threshold=5)
    payload = json.dumps({
        "statusCode": 200,
        "errors": ["Internal database timeout while querying sockets"],
        "data": [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(10)]
    }).encode("utf-8")

    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "nonempty error field" in res.fatal_error


def test_envelope_isSuccess_false_rejected():
    """
    Verifies that isSuccess=False is rejected even if statusCode=200 or records exist.
    """
    validator = CollectorValidator(min_stations_threshold=5)
    payload = json.dumps({
        "statusCode": 200,
        "isSuccess": False,
        "data": [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(10)]
    }).encode("utf-8")

    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "isSuccess=False" in res.fatal_error or "indicates failure" in res.fatal_error


def test_envelope_statusCode_zero_rejected():
    """
    Verifies that statusCode=0 is rejected and does not disappear through truthiness checks.
    """
    validator = CollectorValidator(min_stations_threshold=5)
    payload = json.dumps({
        "statusCode": 0,
        "message": "Gateway error code 0",
        "data": [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(10)]
    }).encode("utf-8")

    res = validator.validate_payload(payload)
    assert not res.is_structurally_valid
    assert "statusCode=0" in res.fatal_error


def test_envelope_string_num_rows_strict_validation():
    """
    Verifies strict validation of declared numRows:
    - numRows="17087" with 60 records is rejected.
    - numRows="invalid" is rejected.
    - numRows=-1 is rejected.
    - numRows=True (boolean) is rejected.
    - numRows="60" with 60 records is accepted.
    """
    validator = CollectorValidator(min_stations_threshold=5)
    items = [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(60)]

    # 1. numRows="17087" with only 60 records
    p1 = json.dumps({"statusCode": 200, "numRows": "17087", "data": items}).encode("utf-8")
    r1 = validator.validate_payload(p1)
    assert not r1.is_structurally_valid
    assert "Declared record count mismatch" in r1.fatal_error

    # 2. numRows="invalid"
    p2 = json.dumps({"statusCode": 200, "numRows": "invalid", "data": items}).encode("utf-8")
    r2 = validator.validate_payload(p2)
    assert not r2.is_structurally_valid
    assert "Malformed declared row count" in r2.fatal_error

    # 3. numRows=-1
    p3 = json.dumps({"statusCode": 200, "numRows": -1, "data": items}).encode("utf-8")
    r3 = validator.validate_payload(p3)
    assert not r3.is_structurally_valid
    assert "Malformed declared row count" in r3.fatal_error

    # 4. numRows=True (boolean)
    p4 = json.dumps({"statusCode": 200, "numRows": True, "data": items}).encode("utf-8")
    r4 = validator.validate_payload(p4)
    assert not r4.is_structurally_valid
    assert "Malformed declared row count" in r4.fatal_error

    # 5. numRows="60" with exact 60 records
    p5 = json.dumps({"statusCode": 200, "numRows": "60", "data": items}).encode("utf-8")
    r5 = validator.validate_payload(p5)
    assert r5.is_structurally_valid
    assert r5.station_count == 60


def test_envelope_empty_socket_list_and_ac_dc_conflict_preserved_as_warnings():
    """
    Verifies that stations with empty socket lists and sockets with conflicting AC/DC
    remain valid and generate warnings (not fatal rejections).
    """
    validator = CollectorValidator(min_stations_threshold=2)
    payload = json.dumps({
        "statusCode": 200,
        "data": [
            {
                "sarjIstasyonuNo": "STN-EMPTY",
                "istasyonAdi": "Empty Station",
                "soketler": []  # Valid registered station with no sockets
            },
            {
                "sarjIstasyonuNo": "STN-CONFLICT",
                "istasyonAdi": "Conflict Station",
                "soketler": [
                    {
                        "soketNo": "SCK-CONFLICT",
                        "soketTipi": "DC",
                        "soketTuru": "AC_TYPE2",
                        "soketGucu": 22.0
                    }
                ]
            }
        ]
    }).encode("utf-8")

    res = validator.validate_payload(payload)
    assert res.is_structurally_valid is True
    assert res.station_count == 2
    assert res.socket_count == 1
    assert any("soketsiz lisanslı istasyon" in w for w in res.warnings)
    assert any("çelişkili AC/DC" in w for w in res.warnings)


def test_envelope_rejection_leaves_previous_successful_manifest_unchanged(tmp_path, valid_epdk_payload):
    """
    Verifies that when an invalid envelope is rejected, CollectorService records failure
    and the previous successful manifest in storage is 100% untouched and unchanged.
    """
    storage = LocalStorageAdapter(base_dir=tmp_path)
    mock_client = MagicMock()
    mock_client.endpoint_url = "https://mock.test/api"

    # Step 1: Successful collection
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=valid_epdk_payload,
        headers={},
        duration_seconds=1.0,
    )
    service = CollectorService(
        api_client=mock_client,
        validator=CollectorValidator(min_stations_threshold=50),
        storage=storage,
        lock_file_path=tmp_path / ".lock",
    )
    res1 = service.run_collection()
    assert res1["status"] == "success"

    manifest_before = storage.get_latest_manifest()
    assert manifest_before is not None
    assert manifest_before["status"] == "success"
    assert manifest_before["station_count"] == 60

    # Step 2: Second run returns invalid envelope (isSuccess=False and nonempty errors)
    bad_payload = json.dumps({
        "statusCode": 200,
        "isSuccess": False,
        "errors": ["Upstream database timeout"],
        "data": [{"sarjIstasyonuNo": f"STN-{i}", "soketler": []} for i in range(60)]
    }).encode("utf-8")
    mock_client.fetch.return_value = FetchResult(
        status_code=200,
        content=bad_payload,
        headers={},
        duration_seconds=0.5,
    )

    res2 = service.run_collection()
    assert res2["status"] == "failed"
    assert res2["stage"] == "validation"

    # Step 3: Verify previous manifest is completely unchanged
    manifest_after = storage.get_latest_manifest()
    assert manifest_after == manifest_before
    assert manifest_after["snapshot_id"] == manifest_before["snapshot_id"]
    assert manifest_after["sha256_hash"] == manifest_before["sha256_hash"]
