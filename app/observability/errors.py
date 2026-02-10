"""
Error tracking and reporting.

Provides utilities for capturing, logging, and reporting errors
for debugging and monitoring purposes.
"""

import logging
import sys
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field
from enum import Enum

from app.config import Settings

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorRecord:
    """Record of a captured error."""
    
    # Error identification
    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    
    # Error details
    exception_type: str
    exception_message: str
    traceback: str
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    
    # User/request info
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'error_id': self.error_id,
            'timestamp': self.timestamp.isoformat(),
            'severity': self.severity.value,
            'exception_type': self.exception_type,
            'exception_message': self.exception_message,
            'traceback': self.traceback,
            'context': self.context,
            'tags': self.tags,
            'user_id': self.user_id,
            'request_id': self.request_id,
        }


class ErrorTracker:
    """
    Error tracker for capturing and reporting errors.
    
    In production, this would integrate with error tracking services
    like Sentry, Rollbar, or CloudWatch Logs.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize error tracker.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.enabled = settings.ERROR_TRACKING_ENABLED
        self.errors: List[ErrorRecord] = []
        
        # Initialize Sentry if configured
        self.sentry_enabled = False
        if self.enabled and settings.SENTRY_DSN:
            try:
                import sentry_sdk
                sentry_sdk.init(
                    dsn=settings.SENTRY_DSN,
                    environment=settings.ENVIRONMENT,
                    traces_sample_rate=0.1,  # 10% of transactions
                )
                self.sentry_enabled = True
                logger.info("Sentry error tracking initialized")
            except ImportError:
                logger.warning("sentry-sdk not installed. Sentry disabled.")
            except Exception as e:
                logger.error(f"Failed to initialize Sentry: {e}")
        
        logger.info(f"Error tracker initialized (enabled: {self.enabled})")
    
    def capture_exception(
        self,
        exception: Exception,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        Capture an exception.
        
        Args:
            exception: The exception to capture
            severity: Error severity level
            context: Additional context data
            tags: Tags for filtering/grouping
            user_id: User identifier
            request_id: Request identifier
        
        Returns:
            Error ID
        """
        if not self.enabled:
            return ""
        
        # Generate error ID
        error_id = self._generate_error_id()
        
        # Extract exception details
        exc_type = type(exception).__name__
        exc_message = str(exception)
        exc_traceback = ''.join(traceback.format_exception(
            type(exception), exception, exception.__traceback__
        ))
        
        # Create error record
        error_record = ErrorRecord(
            error_id=error_id,
            timestamp=datetime.utcnow(),
            severity=severity,
            exception_type=exc_type,
            exception_message=exc_message,
            traceback=exc_traceback,
            context=context or {},
            tags=tags or {},
            user_id=user_id,
            request_id=request_id,
        )
        
        # Store locally
        self.errors.append(error_record)
        
        # Log the error
        log_level = self._severity_to_log_level(severity)
        logger.log(
            log_level,
            f"Error captured: {exc_type}: {exc_message}",
            extra={
                'error_id': error_id,
                'context': context,
                'tags': tags,
            },
            exc_info=exception,
        )
        
        # Send to Sentry if enabled
        if self.sentry_enabled:
            self._send_to_sentry(exception, error_record)
        
        return error_id
    
    def capture_message(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.INFO,
        context: Optional[Dict[str, Any]] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Capture a message without an exception.
        
        Args:
            message: Message to capture
            severity: Message severity
            context: Additional context
            tags: Tags for filtering
        
        Returns:
            Error ID
        """
        if not self.enabled:
            return ""
        
        # Create a synthetic exception for consistency
        error_id = self._generate_error_id()
        
        error_record = ErrorRecord(
            error_id=error_id,
            timestamp=datetime.utcnow(),
            severity=severity,
            exception_type="Message",
            exception_message=message,
            traceback="",
            context=context or {},
            tags=tags or {},
        )
        
        self.errors.append(error_record)
        
        # Log
        log_level = self._severity_to_log_level(severity)
        logger.log(
            log_level,
            f"Message captured: {message}",
            extra={'error_id': error_id, 'context': context, 'tags': tags},
        )
        
        # Send to Sentry if enabled
        if self.sentry_enabled:
            import sentry_sdk
            sentry_sdk.capture_message(message, level=severity.value)
        
        return error_id
    
    def get_errors(
        self,
        since: Optional[datetime] = None,
        severity: Optional[ErrorSeverity] = None,
        limit: int = 100,
    ) -> List[ErrorRecord]:
        """
        Get captured errors.
        
        Args:
            since: Optional start time filter
            severity: Optional severity filter
            limit: Maximum number of errors to return
        
        Returns:
            List of error records
        """
        filtered = self.errors
        
        if since:
            filtered = [e for e in filtered if e.timestamp >= since]
        
        if severity:
            filtered = [e for e in filtered if e.severity == severity]
        
        # Return most recent errors first
        filtered = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
        
        return filtered[:limit]
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get summary of captured errors.
        
        Returns:
            Summary statistics
        """
        total_errors = len(self.errors)
        
        # Count by severity
        severity_counts = {}
        for error in self.errors:
            severity = error.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # Count by exception type
        type_counts = {}
        for error in self.errors:
            exc_type = error.exception_type
            type_counts[exc_type] = type_counts.get(exc_type, 0) + 1
        
        # Get most common errors
        sorted_types = sorted(
            type_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return {
            'total_errors': total_errors,
            'severity_counts': severity_counts,
            'most_common_types': sorted_types[:10],
            'latest_error': self.errors[-1].timestamp.isoformat() if self.errors else None,
        }
    
    def clear_errors(self) -> None:
        """Clear all captured errors."""
        self.errors = []
        logger.info("Error records cleared")
    
    def _generate_error_id(self) -> str:
        """Generate a unique error ID."""
        import uuid
        return str(uuid.uuid4())
    
    def _severity_to_log_level(self, severity: ErrorSeverity) -> int:
        """Convert ErrorSeverity to logging level."""
        mapping = {
            ErrorSeverity.DEBUG: logging.DEBUG,
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }
        return mapping.get(severity, logging.ERROR)
    
    def _send_to_sentry(
        self,
        exception: Exception,
        error_record: ErrorRecord,
    ) -> None:
        """Send error to Sentry."""
        try:
            import sentry_sdk
            
            # Set context
            with sentry_sdk.push_scope() as scope:
                # Add context
                for key, value in error_record.context.items():
                    scope.set_context(key, value)
                
                # Add tags
                for key, value in error_record.tags.items():
                    scope.set_tag(key, value)
                
                # Add user info
                if error_record.user_id:
                    scope.set_user({'id': error_record.user_id})
                
                # Set level
                scope.level = error_record.severity.value
                
                # Capture
                sentry_sdk.capture_exception(exception)
                
        except Exception as e:
            logger.error(f"Failed to send error to Sentry: {e}")


# Global error tracker instance
_error_tracker: Optional[ErrorTracker] = None


def get_error_tracker() -> ErrorTracker:
    """
    Get the global error tracker instance.
    
    Returns:
        ErrorTracker instance
    
    Raises:
        RuntimeError: If tracker not initialized
    """
    if _error_tracker is None:
        raise RuntimeError("Error tracker not initialized. Call setup_error_tracking() first.")
    return _error_tracker


def setup_error_tracking(settings: Settings) -> ErrorTracker:
    """
    Initialize the global error tracker.
    
    Args:
        settings: Application settings
    
    Returns:
        Initialized ErrorTracker
    """
    global _error_tracker
    _error_tracker = ErrorTracker(settings)
    return _error_tracker


def capture_exception(
    exception: Exception,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    context: Optional[Dict[str, Any]] = None,
    tags: Optional[Dict[str, str]] = None,
) -> str:
    """
    Convenience function to capture an exception.
    
    Args:
        exception: Exception to capture
        severity: Error severity
        context: Additional context
        tags: Tags for filtering
    
    Returns:
        Error ID
    """
    try:
        tracker = get_error_tracker()
        return tracker.capture_exception(
            exception=exception,
            severity=severity,
            context=context,
            tags=tags,
        )
    except RuntimeError:
        # Tracker not initialized - just log
        logger.error(
            f"Error tracker not initialized. Exception: {exception}",
            exc_info=exception,
        )
        return ""


def capture_message(
    message: str,
    severity: ErrorSeverity = ErrorSeverity.INFO,
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Convenience function to capture a message.
    
    Args:
        message: Message to capture
        severity: Message severity
        context: Additional context
    
    Returns:
        Error ID
    """
    try:
        tracker = get_error_tracker()
        return tracker.capture_message(
            message=message,
            severity=severity,
            context=context,
        )
    except RuntimeError:
        # Tracker not initialized - just log
        log_level = {
            ErrorSeverity.DEBUG: logging.DEBUG,
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }.get(severity, logging.INFO)
        
        logger.log(log_level, message, extra={'context': context})
        return ""