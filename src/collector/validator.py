"""
Collector Payload Validation Module.
Validates downloaded EPDK responses before persistence:
- Structural integrity (valid JSON, dict/list root, required station attributes).
- Validates EPDK envelope (statusCode, error fields, numRows declared vs actual record count).
- Structurally validates EVERY station and socket record (rejects non-dict/malformed items).
- Completeness check (protects against replacing good data with empty, truncated, or error payloads).
- Distinguishes fatal structural errors from acceptable source-quality warnings.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Any, Dict


@dataclass
class ValidationResult:
    is_structurally_valid: bool
    station_count: int = 0
    socket_count: int = 0
    warnings: List[str] = field(default_factory=list)
    fatal_error: Optional[str] = None


class CollectorValidator:
    """Validates raw EPDK API payloads prior to persistence."""

    def __init__(self, min_stations_threshold: int = 50):
        self.min_stations_threshold = min_stations_threshold

    def validate_payload(self, raw_bytes: bytes) -> ValidationResult:
        """
        Validates raw payload bytes.
        Returns ValidationResult with counts and warnings.
        Fatal errors set is_structurally_valid=False.
        """
        if not raw_bytes or len(raw_bytes.strip()) == 0:
            return ValidationResult(
                is_structurally_valid=False,
                fatal_error="Empty payload (0 bytes received)."
            )

        # 1. JSON parsing check
        try:
            parsed = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except Exception as e:
            return ValidationResult(
                is_structurally_valid=False,
                fatal_error=f"Malformed JSON: {e}"
            )

        # 2. Envelope check (statusCode, errors, numRows declared vs actual)
        items = []
        declared_num_rows: Optional[int] = None

        if isinstance(parsed, dict):
            # 2a. Check explicit success/failure indicator flags
            for fail_key in ["isSuccess", "success"]:
                if fail_key in parsed:
                    val = parsed[fail_key]
                    if val is False or (isinstance(val, str) and val.strip().lower() in ("false", "0")) or (isinstance(val, (int, float)) and not isinstance(val, bool) and val == 0):
                        return ValidationResult(
                            is_structurally_valid=False,
                            fatal_error=f"API envelope indicates failure ({fail_key}={val})"
                        )
            for err_flag in ["hasError", "hasErrors"]:
                if err_flag in parsed:
                    val = parsed[err_flag]
                    if val is True or (isinstance(val, str) and val.strip().lower() in ("true", "1")) or (isinstance(val, (int, float)) and not isinstance(val, bool) and val == 1):
                        return ValidationResult(
                            is_structurally_valid=False,
                            fatal_error=f"API envelope indicates error ({err_flag}={val})"
                        )

            # 2b. Check envelope status code by field PRESENCE (not truthiness)
            status_code = None
            status_field_found = False
            for k in ["statusCode", "status", "code", "responseCode"]:
                if k in parsed:
                    status_code = parsed[k]
                    status_field_found = True
                    break

            if status_field_found and status_code is not None:
                if isinstance(status_code, bool):
                    if not status_code:
                        return ValidationResult(
                            is_structurally_valid=False,
                            fatal_error=f"API envelope status indicates failure: {status_code}"
                        )
                else:
                    try:
                        sc_int = int(status_code)
                        if sc_int != 200:
                            err_msg = parsed.get("error") or parsed.get("errorMessage") or parsed.get("message") or f"HTTP status {sc_int}"
                            return ValidationResult(
                                is_structurally_valid=False,
                                fatal_error=f"API returned error envelope (statusCode={sc_int}): {err_msg}"
                            )
                    except (ValueError, TypeError):
                        if str(status_code).strip().lower() not in ("success", "ok", "200"):
                            return ValidationResult(
                                is_structurally_valid=False,
                                fatal_error=f"API returned non-success status: {status_code}"
                            )

            # 2c. Check nonempty error fields
            for err_key in ["error", "errors", "errorMessage", "errorMessages", "exception", "fault"]:
                if err_key in parsed:
                    err_val = parsed[err_key]
                    is_nonempty = False
                    if err_val is None or err_val == "" or err_val == [] or err_val == {} or err_val is False:
                        is_nonempty = False
                    elif isinstance(err_val, (str, list, dict, set, tuple)):
                        is_nonempty = len(err_val) > 0
                    elif isinstance(err_val, bool):
                        is_nonempty = err_val
                    else:
                        is_nonempty = True

                    if is_nonempty:
                        return ValidationResult(
                            is_structurally_valid=False,
                            fatal_error=f"API envelope contains nonempty error field '{err_key}': {err_val}"
                        )

            # 2d. Strictly validate declared row counts (support exact integer strings; reject malformed)
            for row_key in ["numRows", "totalRows", "recordCount", "totalCount", "total"]:
                if row_key in parsed:
                    raw_val = parsed[row_key]
                    if raw_val is None:
                        continue
                    if isinstance(raw_val, bool):
                        return ValidationResult(
                            is_structurally_valid=False,
                            fatal_error=f"Malformed declared row count in '{row_key}': boolean value {raw_val} is invalid."
                        )
                    elif isinstance(raw_val, (int, float)):
                        if raw_val < 0 or int(raw_val) != raw_val:
                            return ValidationResult(
                                is_structurally_valid=False,
                                fatal_error=f"Malformed declared row count in '{row_key}': {raw_val} is not a valid non-negative integer."
                            )
                        declared_num_rows = int(raw_val)
                        break
                    elif isinstance(raw_val, str):
                        s_val = raw_val.strip()
                        if s_val.isdigit():
                            declared_num_rows = int(s_val)
                            break
                        else:
                            return ValidationResult(
                                is_structurally_valid=False,
                                fatal_error=f"Malformed declared row count in '{row_key}': '{raw_val}' is not a valid integer string."
                            )
                    else:
                        return ValidationResult(
                            is_structurally_valid=False,
                            fatal_error=f"Malformed declared row count in '{row_key}': unexpected type {type(raw_val).__name__}."
                        )

            # Find data container
            for k in ["data", "items", "stations", "result", "results", "records"]:
                if k in parsed and isinstance(parsed[k], list):
                    items = parsed[k]
                    break
            if not items and parsed:
                # If dict itself does not contain a list container, reject if not recognized
                return ValidationResult(
                    is_structurally_valid=False,
                    fatal_error="Response dict does not contain a list of station records."
                )

        elif isinstance(parsed, list):
            items = parsed
        else:
            return ValidationResult(
                is_structurally_valid=False,
                fatal_error=f"Unexpected root type: {type(parsed).__name__} (expected dict or list)."
            )

        # 3. Check for empty station list
        if len(items) == 0:
            return ValidationResult(
                is_structurally_valid=False,
                fatal_error="Response contains no station records (empty array)."
            )

        # 4. Check declared numRows against actual record count
        if declared_num_rows is not None and declared_num_rows != len(items):
            return ValidationResult(
                is_structurally_valid=False,
                station_count=len(items),
                fatal_error=(
                    f"Declared record count mismatch: envelope declared numRows={declared_num_rows}, "
                    f"but actual records received={len(items)}. Payload is partial or corrupted."
                )
            )

        # 5. Completeness sanity threshold
        station_count = len(items)
        if station_count < self.min_stations_threshold:
            return ValidationResult(
                is_structurally_valid=False,
                station_count=station_count,
                fatal_error=(
                    f"Station count ({station_count}) is below minimum safety threshold "
                    f"({self.min_stations_threshold}). Possible truncated response."
                )
            )

        # 6. STRUCTURAL INSPECTION OF EVERY STATION AND SOCKET
        # Reject malformed or non-record entries instead of skipping or counting them
        warnings = []
        socket_count = 0
        stations_without_sockets = 0
        conflicting_ac_dc = 0

        recognized_station_id_keys = ["sarjIstasyonuNo", "station_id", "id", "stationId", "istasyonId", "istasyonNo"]
        recognized_station_name_keys = ["istasyonAdi", "station_name", "name", "stationName"]

        for idx, item in enumerate(items):
            # Every item MUST be a dictionary
            if not isinstance(item, dict):
                return ValidationResult(
                    is_structurally_valid=False,
                    station_count=station_count,
                    fatal_error=f"Station record at index {idx} is not a dictionary (found {type(item).__name__})."
                )

            # Check for recognized station identity keys
            has_id = any(k in item and item[k] is not None for k in recognized_station_id_keys)
            has_name = any(k in item and item[k] is not None for k in recognized_station_name_keys)
            if not (has_id or has_name):
                return ValidationResult(
                    is_structurally_valid=False,
                    station_count=station_count,
                    fatal_error=f"Station record at index {idx} lacks recognized station identifier or name keys: {list(item.keys())[:5]}"
                )

            # Inspect socket container
            sock_container = None
            for sk in ["soketler", "sockets", "connectors"]:
                if sk in item:
                    sock_container = item[sk]
                    break

            if sock_container is not None:
                if not isinstance(sock_container, list):
                    return ValidationResult(
                        is_structurally_valid=False,
                        station_count=station_count,
                        fatal_error=f"Station at index {idx} has invalid socket container (type {type(sock_container).__name__}, expected list)."
                    )

                if len(sock_container) == 0:
                    stations_without_sockets += 1
                else:
                    for s_idx, sock in enumerate(sock_container):
                        if not isinstance(sock, dict):
                            return ValidationResult(
                                is_structurally_valid=False,
                                station_count=station_count,
                                fatal_error=f"Station at index {idx} contains non-dict socket at socket index {s_idx} ({type(sock).__name__})."
                            )
                        socket_count += 1
                        stype = str(sock.get("soketTipi", "")).upper()
                        ssub = str(sock.get("soketTuru", "")).upper()
                        if (stype == "DC" and ssub.startswith("AC")) or (stype == "AC" and ssub.startswith("DC")):
                            conflicting_ac_dc += 1
            else:
                stations_without_sockets += 1

        if stations_without_sockets > 0:
            warnings.append(f"{stations_without_sockets} istasyonda soket kaydı bulunmamaktadır (soketsiz lisanslı istasyon).")
        if conflicting_ac_dc > 0:
            warnings.append(f"{conflicting_ac_dc} sokette çelişkili AC/DC sınıflandırması tespit edildi.")

        return ValidationResult(
            is_structurally_valid=True,
            station_count=station_count,
            socket_count=socket_count,
            warnings=warnings
        )
