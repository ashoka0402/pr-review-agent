"""
Storage module for persisting review data and logs.

This module provides:
- S3 client for storing review history and logs
- Repository abstraction for review persistence
"""

from app.storage.s3 import S3Client, get_s3_client
from app.storage.repository import ReviewRepository, ReviewRecord

__all__ = [
    "S3Client",
    "get_s3_client",
    "ReviewRepository",
    "ReviewRecord",
]