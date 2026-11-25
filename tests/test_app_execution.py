"""
Application Execution and Dashboard Controller Tests.
Exercises the actual production dashboard behavior:
- Server process startup check (labeled as server startup check).
- Metric rendering and default vs socket-level population filtering.
- Empty operator selection producing an empty result.
- Failed upload handling clearing DataFrame state (no stale-data fallback).
- Cloud snapshot integrity verification (detecting checksum mismatches and corrupted bytes).
"""

import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import pytest
import pandas as pd

from src.dashboard_controller import (
    filter_dataset,
    verify_snapshot_integrity,
    handle_file_upload,
)
from src.validator import validate_charging_dataset
from src.metrics import compute_kpis
from src.data_loader import load_dataset


@pytest.fixture
def small_synthetic_app_fixture():
    """Provides a small 3-station fixture with 1 socketless station."""
    return pd.DataFrame([
        {
            "station_id": "STN-001",
            "station_name": "Station A",
            "socket_id": "SCK-001-1",
            "operator_name": "ZES",
            "socket_type": "AC",
            "power_kw": 22.0,
        },
        {
            "station_id": "STN-001",
            "station_name": "Station A",
            "socket_id": "SCK-001-2",
            "operator_name": "ZES",
            "socket_type": "DC",
            "power_kw": 180.0,
        },
        {
            "station_id": "STN-002",
            "station_name": "Station B",
            "socket_id": "SCK-002-1",
            "operator_name": "Trugo",
            "socket_type": "DC",
            "power_kw": 120.0,
        },
        {
            "station_id": "STN-EMPTY",
            "station_name": "Station Without Sockets",
            "socket_id": None,
            "operator_name": "Astor",
            "socket_type": None,
            "power_kw": None,
        }
    ])


# ------------------------------------------------------------------------------
# 1. Server Process Startup Check
# ------------------------------------------------------------------------------
def test_app_server_startup(tmp_path):
    """
    Server startup check:
    Executes Streamlit in headless mode on a temporary port with isolated user profile.
    Confirms the server process initializes, compiles app.py, and runs without crashing.
    """
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)

    st_dir = tmp_path / ".streamlit"
    st_dir.mkdir(parents=True, exist_ok=True)
    (st_dir / "credentials.toml").write_text('[general]\nemail = ""\n', encoding="utf-8")
    (st_dir / "config.toml").write_text('[browser]\ngatherUsageStats = false\n[server]\nheadless = true\n', encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--server.port",
        "8504",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
    try:
        time.sleep(3.5)
        poll = proc.poll()
        if poll is not None:
            stdout, stderr = proc.communicate()
            pytest.fail(f"Streamlit server crashed on startup (code {poll}):\n{stderr}\n{stdout}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


# ------------------------------------------------------------------------------
# 2. Production App Filter Execution & Metric Verification
# ------------------------------------------------------------------------------
def test_dashboard_production_execution_and_metrics(small_synthetic_app_fixture):
    """
    Tests production filtering and metric computation directly:
    - Default view: All 3 stations preserved (including socketless), label is 'Kayıtlı Tüm İstasyonlar'.
    - Socket filter active: Only stations meeting power criteria preserved, label is 'Soket Kriterine Uyan İstasyonlar'.
    """
    validated_df, summary = validate_charging_dataset(small_synthetic_app_fixture)
    assert summary.unique_stations == 3
    assert summary.stations_without_sockets == 1
    assert summary.unique_sockets == 3

    # Case A: Default view (all operators, all types, full power range)
    min_power = 22.0
    max_power = 180.0
    filtered_default, is_socket_active_default, label_default = filter_dataset(
        validated_df=validated_df,
        filter_all_ops=True,
        selected_operators=["ZES", "Trugo", "Astor"],
        selected_type="Tümü",
        power_range=(min_power, max_power),
        min_power=min_power,
        max_power=max_power,
    )
    assert is_socket_active_default is False
    assert label_default == "Kayıtlı Tüm İstasyonlar"

    kpis_default = compute_kpis(filtered_default)
    # MUST show all 3 stations
    assert kpis_default["unique_stations"] == 3
    assert kpis_default["unique_sockets"] == 3
    assert kpis_default["total_socket_power_kw"] == 322.0  # 22 + 180 + 120

    # Case B: User moves power slider (e.g. min power = 100 kW)
    filtered_custom, is_socket_active_custom, label_custom = filter_dataset(
        validated_df=validated_df,
        filter_all_ops=True,
        selected_operators=["ZES", "Trugo", "Astor"],
        selected_type="Tümü",
        power_range=(100.0, max_power),
        min_power=min_power,
        max_power=max_power,
    )
    assert is_socket_active_custom is True
    assert label_custom == "Soket Kriterine Uyan İstasyonlar"

    kpis_custom = compute_kpis(filtered_custom)
    # STN-001 (180 kW) and STN-002 (120 kW) match; STN-EMPTY is excluded
    assert kpis_custom["unique_stations"] == 2
    assert kpis_custom["unique_sockets"] == 2
    assert kpis_custom["total_socket_power_kw"] == 300.0  # 180 + 120


# ------------------------------------------------------------------------------
# 3. Empty Operator Selection Execution
# ------------------------------------------------------------------------------
def test_dashboard_empty_operator_selection_execution(small_synthetic_app_fixture):
    """
    Tests that clearing operator selection produces an empty DataFrame (0 rows).
    """
    validated_df, _ = validate_charging_dataset(small_synthetic_app_fixture)

    filtered_df, _, _ = filter_dataset(
        validated_df=validated_df,
        filter_all_ops=False,
        selected_operators=[],  # User cleared all operator selections
        selected_type="Tümü",
        power_range=(22.0, 180.0),
        min_power=22.0,
        max_power=180.0,
    )
    assert len(filtered_df) == 0
    kpis = compute_kpis(filtered_df)
    assert kpis["unique_stations"] == 0
    assert kpis["unique_sockets"] == 0


# ------------------------------------------------------------------------------
# 4. Failed Upload Clears State (No Stale-Data Fallback)
# ------------------------------------------------------------------------------
def test_dashboard_failed_upload_resets_state():
    """
    Verifies that a failed file upload clears raw_df to None so that stale data is not displayed.
    """
    corrupt_stream = io.BytesIO(b"MALFORMED_NON_JSON_DATA")
    corrupt_stream.name = "corrupt.json"

    df, mappings, err_msg = handle_file_upload(corrupt_stream, load_dataset)
    assert df is None
    assert mappings == {}
    assert err_msg is not None


# ------------------------------------------------------------------------------
# 5. Cloud Snapshot Integrity Verification
# ------------------------------------------------------------------------------
def test_dashboard_cloud_integrity_error_handling():
    """
    Tests verify_snapshot_integrity:
    - Matching hash passes.
    - Altered byte fails with checksum mismatch error.
    - Corrupted gzip header fails with decompression error.
    """
    raw_payload = b'{"data": [{"sarjIstasyonuNo": "STN-1", "soketler": []}]}'
    compressed = gzip.compress(raw_payload)
    correct_sha = hashlib.sha256(raw_payload).hexdigest()

    # Success case
    ok, err = verify_snapshot_integrity(compressed, correct_sha)
    assert ok is True
    assert err is None

    # Checksum mismatch case (tampered data)
    wrong_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    ok, err = verify_snapshot_integrity(compressed, wrong_sha)
    assert ok is False
    assert "Checksum mismatch" in err

    # Corrupted decompression
    broken_bytes = b"\x1f\x8b\x08BROKEN_GZIP_STREAM"
    ok, err = verify_snapshot_integrity(broken_bytes, correct_sha)
    assert ok is False
    assert "Decompression error" in err


# ------------------------------------------------------------------------------
# 6. app.py Compilation and Syntax Regression Test
# ------------------------------------------------------------------------------
def test_app_compilation_syntax():
    """
    Regression test:
    Strictly verifies that app.py compiles cleanly without any SyntaxError or IndentationError.
    Catches template editing defects before deployment.
    """
    import py_compile
    from pathlib import Path
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    assert app_path.exists(), f"app.py not found at {app_path}"
    # Compiles app.py and raises py_compile.PyCompileError on syntax/indentation failure
    compiled_path = py_compile.compile(str(app_path), doraise=True)
    assert compiled_path is not None
