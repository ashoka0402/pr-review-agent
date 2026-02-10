"""
Structured logging configuration.

Provides JSON-formatted logging with context management for
better observability in production environments.
"""

import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
from functools import wraps

from app.config import Settings


# Context variable for storing request/operation context
log_context: ContextVar[Dict[str, Any]] = ContextVar('log_context', default={})


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    
    Formats log records as JSON with additional context fields.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base log data
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add context from ContextVar
        context = log_context.get()
        if context:
            log_data['context'] = context
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info),
            }
        
        # Add extra fields from record
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Add source location for errors and above
        if record.levelno >= logging.ERROR:
            log_data['source'] = {
                'file': record.pathname,
                'line': record.lineno,
                'function': record.funcName,
            }
        
        return json.dumps(log_data)


class ContextFormatter(logging.Formatter):
    """
    Human-readable formatter with context.
    
    Used for development/debugging with better readability.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with context."""
        # Get base formatted message
        base_msg = super().format(record)
        
        # Add context if present
        context = log_context.get()
        if context:
            context_str = ' '.join(f'{k}={v}' for k, v in context.items())
            base_msg = f"{base_msg} [{context_str}]"
        
        return base_msg


def setup_logging(settings: Settings) -> None:
    """
    Configure application logging.
    
    Sets up structured JSON logging for production or human-readable
    logging for development.
    
    Args:
        settings: Application settings
    """
    # Determine log level
    log_level = getattr(logging, settings.LOG_LEVEL.upper())
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Set formatter based on environment
    if settings.ENVIRONMENT == "production":
        formatter = JSONFormatter()
    else:
        formatter = ContextFormatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Set levels for noisy libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    
    root_logger.info(
        f"Logging configured: level={settings.LOG_LEVEL}, "
        f"environment={settings.ENVIRONMENT}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger
    """
    return logging.getLogger(name)


class LogContext:
    """
    Context manager for adding structured context to logs.
    
    Usage:
        with LogContext(pr_number=123, owner="org", repo="repo"):
            logger.info("Processing PR")  # Includes context in log
    """
    
    def __init__(self, **kwargs):
        """
        Initialize log context.
        
        Args:
            **kwargs: Key-value pairs to add to log context
        """
        self.context = kwargs
        self.token = None
    
    def __enter__(self):
        """Enter context - set context variables."""
        # Get current context and merge with new values
        current = log_context.get().copy()
        current.update(self.context)
        self.token = log_context.set(current)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - restore previous context."""
        if self.token:
            log_context.reset(self.token)


def log_function_call(logger: Optional[logging.Logger] = None):
    """
    Decorator to log function calls with arguments and timing.
    
    Args:
        logger: Optional logger to use (defaults to function's module logger)
    
    Usage:
        @log_function_call()
        def my_function(arg1, arg2):
            pass
    """
    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = logging.getLogger(func.__module__)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            func_name = func.__name__
            start_time = datetime.utcnow()
            
            logger.debug(
                f"Calling {func_name}",
                extra={'args': str(args)[:100], 'kwargs': str(kwargs)[:100]}
            )
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.debug(
                    f"Completed {func_name}",
                    extra={'duration_ms': duration_ms}
                )
                return result
            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.error(
                    f"Failed {func_name}",
                    extra={'duration_ms': duration_ms, 'error': str(e)},
                    exc_info=True
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            func_name = func.__name__
            start_time = datetime.utcnow()
            
            logger.debug(
                f"Calling {func_name}",
                extra={'args': str(args)[:100], 'kwargs': str(kwargs)[:100]}
            )
            
            try:
                result = func(*args, **kwargs)
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.debug(
                    f"Completed {func_name}",
                    extra={'duration_ms': duration_ms}
                )
                return result
            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.error(
                    f"Failed {func_name}",
                    extra={'duration_ms': duration_ms, 'error': str(e)},
                    exc_info=True
                )
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def add_log_context(**kwargs):
    """
    Add fields to the current log context.
    
    Args:
        **kwargs: Key-value pairs to add
    """
    current = log_context.get().copy()
    current.update(kwargs)
    log_context.set(current)


def clear_log_context():
    """Clear the log context."""
    log_context.set({})


def get_log_context() -> Dict[str, Any]:
    """
    Get the current log context.
    
    Returns:
        Current context dictionary
    """
    return log_context.get().copy()