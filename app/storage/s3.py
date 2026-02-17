"""
S3 client for storing review data and logs.

Handles uploading review results, logs, and artifacts to S3 for
persistence, audit trails, and analytics.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional, Any, BinaryIO
from io import BytesIO

from app.config import Settings

logger = logging.getLogger(__name__)


class S3Error(Exception):
    """Exception raised for S3 operation errors."""
    pass


class S3Client:
    """
    Client for interacting with AWS S3.
    
    Provides methods for uploading and retrieving review data,
    logs, and other artifacts.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize S3 client.
        
        Args:
            settings: Application settings with S3 configuration
        """
        self.settings = settings
        self.bucket_name = settings.S3_BUCKET_NAME
        self.enabled = settings.S3_ENABLED
        
        if self.enabled:
            try:
                import boto3
                self.client = boto3.client(
                    's3',
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION,
                )
                logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
            except ImportError:
                logger.warning("boto3 not installed. S3 storage disabled.")
                self.enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                self.enabled = False
        else:
            logger.info("S3 storage is disabled")
            self.client = None
    
    async def upload_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Upload review data to S3.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            review_data: Complete review result
            timestamp: Review timestamp (uses current time if not provided)
        
        Returns:
            S3 key/path of uploaded file, or None if upload failed/disabled
        """
        if not self.enabled:
            logger.debug("S3 upload skipped (disabled)")
            return None
        
        try:
            # Generate S3 key
            timestamp = timestamp or datetime.utcnow()
            key = self._generate_review_key(owner, repo, pr_number, timestamp)
            
            # Convert to JSON
            json_data = json.dumps(review_data, indent=2, default=str)
            
            # Upload
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json_data.encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'owner': owner,
                    'repo': repo,
                    'pr_number': str(pr_number),
                    'timestamp': timestamp.isoformat(),
                }
            )
            
            logger.info(f"Review uploaded to S3: {key}")
            return key
            
        except Exception as e:
            logger.error(f"Failed to upload review to S3: {e}")
            return None
    
    async def upload_logs(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        log_data: str,
        timestamp: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Upload log data to S3.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            log_data: Log content
            timestamp: Log timestamp
        
        Returns:
            S3 key of uploaded file, or None if failed/disabled
        """
        if not self.enabled:
            return None
        
        try:
            timestamp = timestamp or datetime.utcnow()
            key = self._generate_log_key(owner, repo, pr_number, timestamp)
            
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=log_data.encode('utf-8'),
                ContentType='text/plain',
                Metadata={
                    'owner': owner,
                    'repo': repo,
                    'pr_number': str(pr_number),
                    'timestamp': timestamp.isoformat(),
                }
            )
            
            logger.info(f"Logs uploaded to S3: {key}")
            return key
            
        except Exception as e:
            logger.error(f"Failed to upload logs to S3: {e}")
            return None
    
    async def download_review(
        self,
        key: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Download and parse review data from S3.
        
        Args:
            key: S3 key of the review file
        
        Returns:
            Parsed review data, or None if failed
        """
        if not self.enabled:
            return None
        
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            
            content = response['Body'].read().decode('utf-8')
            data = json.loads(content)
            
            logger.info(f"Review downloaded from S3: {key}")
            return data
            
        except Exception as e:
            logger.error(f"Failed to download review from S3: {e}")
            return None
    
    async def list_reviews(
        self,
        owner: str,
        repo: str,
        pr_number: Optional[int] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
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
        if not self.enabled:
            return []
        
        try:
            # Build prefix
            if pr_number:
                prefix = f"reviews/{owner}/{repo}/{pr_number}/"
            else:
                prefix = f"reviews/{owner}/{repo}/"
            
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=limit,
            )
            
            reviews = []
            for obj in response.get('Contents', []):
                reviews.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                })
            
            logger.info(f"Found {len(reviews)} reviews for {owner}/{repo}")
            return reviews
            
        except Exception as e:
            logger.error(f"Failed to list reviews from S3: {e}")
            return []
    
    async def upload_artifact(
        self,
        key: str,
        data: bytes,
        content_type: str = 'application/octet-stream',
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Upload arbitrary artifact to S3.
        
        Args:
            key: S3 key/path
            data: Binary data to upload
            content_type: Content type
            metadata: Optional metadata
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            kwargs = {
                'Bucket': self.bucket_name,
                'Key': key,
                'Body': data,
                'ContentType': content_type,
            }
            
            if metadata:
                kwargs['Metadata'] = metadata
            
            self.client.put_object(**kwargs)
            logger.info(f"Artifact uploaded to S3: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload artifact to S3: {e}")
            return False
    
    async def delete_review(self, key: str) -> bool:
        """
        Delete a review from S3.
        
        Args:
            key: S3 key of the review to delete
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False
        
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            logger.info(f"Review deleted from S3: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete review from S3: {e}")
            return False
    
    def _generate_review_key(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        timestamp: datetime,
    ) -> str:
        """
        Generate S3 key for review data.
        
        Format: reviews/{owner}/{repo}/{pr_number}/{timestamp}.json
        """
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"reviews/{owner}/{repo}/{pr_number}/{ts_str}.json"
    
    def _generate_log_key(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        timestamp: datetime,
    ) -> str:
        """
        Generate S3 key for log data.
        
        Format: logs/{owner}/{repo}/{pr_number}/{timestamp}.log
        """
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        return f"logs/{owner}/{repo}/{pr_number}/{ts_str}.log"
    
    def get_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
    ) -> Optional[str]:
        """
        Generate presigned URL for accessing a file.
        
        Args:
            key: S3 key
            expiration: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            Presigned URL, or None if failed
        """
        if not self.enabled:
            return None
        
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': key,
                },
                ExpiresIn=expiration,
            )
            return url
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None


def get_s3_client():
    return None
