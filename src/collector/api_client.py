"""
EPDK Gateway API Client Module.
Reuses verified endpoint and request structure from the tested Colab implementation:
- Endpoint: https://apigateway.epdk.gov.tr/sarjIstasyonlari
- Method: GET with data="{}" and JSON headers
- Explicit timeouts, bounded retries, and Retry-After handling.
"""

import os
import time
import email.utils
from dataclasses import dataclass
from typing import Dict, Any, Optional
import requests


@dataclass
class FetchResult:
    status_code: int
    content: bytes
    headers: Dict[str, str]
    duration_seconds: float
    retry_after: Optional[int] = None
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status_code == 200 and len(self.content) > 0


class EPDKApiClient:
    """HTTP Client for EPDK Charging Stations Gateway API."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        max_retry_after: int = 60,
        api_key: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or os.getenv(
            "EPDK_API_URL", "https://apigateway.epdk.gov.tr/sarjIstasyonlari"
        )
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("EPDK_REQUEST_TIMEOUT", "180")
        )
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_retry_after = max_retry_after
        self.api_key = api_key or os.getenv("EPDK_API_KEY")

    def _parse_retry_after(self, retry_after_header: Optional[str]) -> Optional[int]:
        """Parses Retry-After header as integer seconds or HTTP date."""
        if not retry_after_header:
            return None
        try:
            return int(retry_after_header)
        except ValueError:
            try:
                date_tuple = email.utils.parsedate_tz(retry_after_header)
                if date_tuple:
                    target_ts = email.utils.mktime_tz(date_tuple)
                    diff = int(target_ts - time.time())
                    return max(0, diff)
            except Exception:
                pass
        return None

    def fetch(self, session: Optional[requests.Session] = None) -> FetchResult:
        """
        Executes HTTP request to EPDK API with bounded retries and exponential backoff.
        Respects Retry-After header on 429 responses up to max_retry_after limit.
        """
        http = session or requests.Session()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Codex-EPDK-Collector/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        last_error = None
        attempt = 0

        while attempt < self.max_retries:
            attempt += 1
            t0 = time.time()
            try:
                # Verified EPDK API signature from Colab notebook
                resp = http.request(
                    "GET",
                    self.endpoint_url,
                    data="{}",
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                duration = time.time() - t0
                retry_after_sec = self._parse_retry_after(resp.headers.get("Retry-After"))

                # Success
                if resp.status_code == 200:
                    return FetchResult(
                        status_code=200,
                        content=resp.content,
                        headers=dict(resp.headers),
                        duration_seconds=duration,
                        retry_after=retry_after_sec,
                    )

                # Transient rate-limit (429) or server errors (500, 502, 503, 504)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    wait_time = self.backoff_factor ** (attempt - 1)
                    if resp.status_code == 429 and retry_after_sec is not None:
                        if retry_after_sec > self.max_retry_after:
                            # Exceeds bounded wait time, abort
                            return FetchResult(
                                status_code=resp.status_code,
                                content=resp.content,
                                headers=dict(resp.headers),
                                duration_seconds=duration,
                                retry_after=retry_after_sec,
                                error_message=f"HTTP 429: Retry-After ({retry_after_sec}s) exceeds max allowed limit ({self.max_retry_after}s).",
                            )
                        wait_time = retry_after_sec

                    time.sleep(wait_time)
                    continue

                # Non-retriable HTTP error or exhausted retries
                return FetchResult(
                    status_code=resp.status_code,
                    content=resp.content,
                    headers=dict(resp.headers),
                    duration_seconds=duration,
                    retry_after=retry_after_sec,
                    error_message=f"HTTP {resp.status_code}: {resp.reason}",
                )

            except requests.exceptions.RequestException as ex:
                duration = time.time() - t0
                last_error = f"{type(ex).__name__}: {ex}"
                if attempt < self.max_retries:
                    time.sleep(self.backoff_factor ** (attempt - 1))
                    continue

        return FetchResult(
            status_code=0,
            content=b"",
            headers={},
            duration_seconds=time.time() - t0 if "t0" in locals() else 0.0,
            error_message=f"Request failed after {self.max_retries} attempts: {last_error}",
        )
