"""
Repository abstraction for review persistence.

Provides a high-level interface for storing and retrieving review records,
abstracting the underlying storage mechanism (S3, database, etc.).
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from app.storage.s3 import S3Client
from app.llm.schemas import CodeReview, ReviewRecommendation

logger = logging.getLogger(__name__)


class ReviewStatus(str, Enum):
    """Status of a review."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReviewRecord:
    """
    Record of a PR review.
    
    This is the persistent representation of a review,
    containing both metadata and results.
    """
    
    # Identifiers
    owner: str
    repo: str
    pr_number: int
    commit_sha: str
    
    # Metadata
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime
    
    # Review data (populated when completed)
    review_data: Optional[Dict[str, Any]] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None
    
    # Metrics
    iterations: int = 0
    processing_time_ms: Optional[int] = None
    comment_count: int = 0
    
    # Storage references
    s3_key: Optional[str] = None
    log_key: Optional[str] = None
    
    # Error tracking
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        # Convert enum to value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReviewRecord':
        """Create from dictionary."""
        # Convert ISO strings back to datetime
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        # Convert string to enum
        data['status'] = ReviewStatus(data['status'])
        return cls(**data)


class ReviewRepository:
    """
    Repository for managing review records.
    
    Provides CRUD operations and queries for review data,
    using S3 as the underlying storage.
    """
    
    def __init__(self, s3_client: S3Client):
        """
        Initialize repository.
        
        Args:
            s3_client: S3 client for storage
        """
        self.s3_client = s3_client
    
    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
    ) -> ReviewRecord:
        """
        Create a new review record.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            commit_sha: Commit SHA being reviewed
        
        Returns:
            Created ReviewRecord
        """
        now = datetime.utcnow()
        
        record = ReviewRecord(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=commit_sha,
            status=ReviewStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        
        logger.info(f"Created review record for {owner}/{repo}#{pr_number}")
        return record
    
    async def update_review_status(
        self,
        record: ReviewRecord,
        status: ReviewStatus,
        error_message: Optional[str] = None,
    ) -> ReviewRecord:
        """
        Update review status.
        
        Args:
            record: Review record to update
            status: New status
            error_message: Optional error message
        
        Returns:
            Updated record
        """
        record.status = status
        record.updated_at = datetime.utcnow()
        
        if error_message:
            record.error_message = error_message
        
        logger.info(f"Updated review status to {status.value}")
        return record
    
    async def save_review_result(
        self,
        record: ReviewRecord,
        review_result: Dict[str, Any],
        processing_time_ms: int,
    ) -> ReviewRecord:
        """
        Save completed review result.
        
        Args:
            record: Review record
            review_result: Complete review result from PRReviewer
            processing_time_ms: Processing time in milliseconds
        
        Returns:
            Updated record with saved data
        """
        # Update record with results
        record.status = ReviewStatus.COMPLETED
        record.updated_at = datetime.utcnow()
        record.review_data = review_result
        record.recommendation = review_result.get("recommendation", {}).get("value")
        record.confidence = review_result.get("confidence")
        record.iterations = review_result.get("iterations", 0)
        record.processing_time_ms = processing_time_ms
        
        # Extract review comments count
        review = review_result.get("review")
        if review:
            if isinstance(review, dict):
                record.comment_count = len(review.get("comments", []))
            else:
                # CodeReview object
                record.comment_count = len(review.comments)
        
        # Upload to S3
        s3_key = await self.s3_client.upload_review(
            owner=record.owner,
            repo=record.repo,
            pr_number=record.pr_number,
            review_data=review_result,
            timestamp=record.updated_at,
        )
        
        if s3_key:
            record.s3_key = s3_key
            logger.info(f"Review saved to S3: {s3_key}")
        else:
            logger.warning("Failed to save review to S3")
        
        return record
    
    async def save_logs(
        self,
        record: ReviewRecord,
        log_data: str,
    ) -> ReviewRecord:
        """
        Save log data for a review.
        
        Args:
            record: Review record
            log_data: Log content
        
        Returns:
            Updated record
        """
        log_key = await self.s3_client.upload_logs(
            owner=record.owner,
            repo=record.repo,
            pr_number=record.pr_number,
            log_data=log_data,
            timestamp=record.updated_at,
        )
        
        if log_key:
            record.log_key = log_key
            logger.info(f"Logs saved to S3: {log_key}")
        
        return record
    
    async def get_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        timestamp: datetime,
    ) -> Optional[ReviewRecord]:
        """
        Retrieve a specific review.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            timestamp: Review timestamp
        
        Returns:
            ReviewRecord if found, None otherwise
        """
        # Generate expected S3 key
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        key = f"reviews/{owner}/{repo}/{pr_number}/{ts_str}.json"
        
        # Download from S3
        data = await self.s3_client.download_review(key)
        
        if not data:
            return None
        
        # Reconstruct record
        # This is simplified - in production, you'd have a more robust schema
        return ReviewRecord(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            commit_sha=data.get("commit_sha", "unknown"),
            status=ReviewStatus.COMPLETED,
            created_at=timestamp,
            updated_at=timestamp,
            review_data=data,
            s3_key=key,
        )
    
    async def list_reviews(
        self,
        owner: str,
        repo: str,
        pr_number: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List reviews for a repository or PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Optional PR number to filter by
            limit: Maximum number of results
        
        Returns:
            List of review metadata
        """
        reviews = await self.s3_client.list_reviews(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            limit=limit,
        )
        
        return reviews
    
    async def get_latest_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent review for a PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
        
        Returns:
            Latest review data, or None if not found
        """
        reviews = await self.list_reviews(owner, repo, pr_number, limit=1)
        
        if not reviews:
            return None
        
        # Download the latest review
        latest_key = reviews[0]['key']
        return await self.s3_client.download_review(latest_key)
    
    async def delete_review(
        self,
        record: ReviewRecord,
    ) -> bool:
        """
        Delete a review record.
        
        Args:
            record: Review record to delete
        
        Returns:
            True if successful
        """
        if not record.s3_key:
            logger.warning("No S3 key found for review")
            return False
        
        success = await self.s3_client.delete_review(record.s3_key)
        
        # Also delete logs if present
        if record.log_key:
            await self.s3_client.delete_review(record.log_key)
        
        return success
    
    async def get_review_stats(
        self,
        owner: str,
        repo: str,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get statistics for reviews in a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            since: Optional start date for stats
        
        Returns:
            Statistics dictionary
        """
        reviews = await self.list_reviews(owner, repo, limit=1000)
        
        if not reviews:
            return {
                "total_reviews": 0,
                "avg_processing_time_ms": 0,
                "recommendation_breakdown": {},
            }
        
        # Filter by date if provided
        if since:
            reviews = [
                r for r in reviews
                if r['last_modified'] >= since
            ]
        
        # Calculate statistics
        # Note: This is simplified. In production, you'd download and analyze each review
        stats = {
            "total_reviews": len(reviews),
            "storage_size_bytes": sum(r['size'] for r in reviews),
            "date_range": {
                "earliest": min(r['last_modified'] for r in reviews).isoformat() if reviews else None,
                "latest": max(r['last_modified'] for r in reviews).isoformat() if reviews else None,
            }
        }
        
        return stats
    
    def get_presigned_url(
        self,
        record: ReviewRecord,
        expiration: int = 3600,
    ) -> Optional[str]:
        """
        Get presigned URL for accessing review data.
        
        Args:
            record: Review record
            expiration: URL expiration in seconds
        
        Returns:
            Presigned URL, or None if not available
        """
        if not record.s3_key:
            return None
        
        return self.s3_client.get_presigned_url(
            key=record.s3_key,
            expiration=expiration,
        )