"""
EPDK Charging Market Automated Data Collector Package.
Provides scheduled API collection, validation, compressed snapshot persistence,
manifest management, and storage adapters.
"""

from src.collector.api_client import EPDKApiClient, FetchResult
from src.collector.validator import CollectorValidator, ValidationResult
from src.collector.storage import StorageAdapter, LocalStorageAdapter, S3StorageAdapter
from src.collector.collector_service import CollectorService

__all__ = [
    "EPDKApiClient",
    "FetchResult",
    "CollectorValidator",
    "ValidationResult",
    "StorageAdapter",
    "LocalStorageAdapter",
    "S3StorageAdapter",
    "CollectorService",
]
