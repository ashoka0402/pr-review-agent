"""
Metrics collection for monitoring and performance tracking.

Provides utilities for recording latency, counters, and custom metrics
for observability and alerting.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager

from app.config import Settings

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """Individual metric data point."""
    
    name: str
    metric_type: MetricType
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'type': self.metric_type.value,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'tags': self.tags,
        }


class MetricsCollector:
    """
    Collector for application metrics.
    
    Stores metrics in memory and provides methods for recording
    various metric types. In production, this would integrate with
    a metrics backend like Prometheus, CloudWatch, or Datadog.
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize metrics collector.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.enabled = settings.METRICS_ENABLED
        self.metrics: List[Metric] = []
        self._start_time = datetime.utcnow()
        
        logger.info(f"Metrics collector initialized (enabled: {self.enabled})")
    
    def record_counter(
        self,
        name: str,
        value: float = 1.0,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a counter metric.
        
        Counters are monotonically increasing values.
        
        Args:
            name: Metric name
            value: Increment value (default: 1.0)
            tags: Optional tags/labels
        """
        if not self.enabled:
            return
        
        metric = Metric(
            name=name,
            metric_type=MetricType.COUNTER,
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {},
        )
        
        self.metrics.append(metric)
        logger.debug(f"Counter recorded: {name}={value} {tags}")
    
    def record_gauge(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a gauge metric.
        
        Gauges are point-in-time values that can go up or down.
        
        Args:
            name: Metric name
            value: Current value
            tags: Optional tags/labels
        """
        if not self.enabled:
            return
        
        metric = Metric(
            name=name,
            metric_type=MetricType.GAUGE,
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {},
        )
        
        self.metrics.append(metric)
        logger.debug(f"Gauge recorded: {name}={value} {tags}")
    
    def record_histogram(
        self,
        name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a histogram metric.
        
        Histograms track distributions of values.
        
        Args:
            name: Metric name
            value: Observed value
            tags: Optional tags/labels
        """
        if not self.enabled:
            return
        
        metric = Metric(
            name=name,
            metric_type=MetricType.HISTOGRAM,
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {},
        )
        
        self.metrics.append(metric)
        logger.debug(f"Histogram recorded: {name}={value} {tags}")
    
    def record_timer(
        self,
        name: str,
        duration_ms: float,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Record a timer metric (specialized histogram for durations).
        
        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
            tags: Optional tags/labels
        """
        if not self.enabled:
            return
        
        metric = Metric(
            name=name,
            metric_type=MetricType.TIMER,
            value=duration_ms,
            timestamp=datetime.utcnow(),
            tags=tags or {},
        )
        
        self.metrics.append(metric)
        logger.debug(f"Timer recorded: {name}={duration_ms}ms {tags}")
    
    @contextmanager
    def timer_context(
        self,
        name: str,
        tags: Optional[Dict[str, str]] = None,
    ):
        """
        Context manager for timing code blocks.
        
        Usage:
            with metrics.timer_context("my_operation"):
                # Code to time
                pass
        
        Args:
            name: Metric name
            tags: Optional tags/labels
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.record_timer(name, duration_ms, tags)
    
    def get_metrics(
        self,
        since: Optional[datetime] = None,
        metric_type: Optional[MetricType] = None,
    ) -> List[Metric]:
        """
        Get collected metrics.
        
        Args:
            since: Optional start time filter
            metric_type: Optional metric type filter
        
        Returns:
            List of metrics matching filters
        """
        filtered = self.metrics
        
        if since:
            filtered = [m for m in filtered if m.timestamp >= since]
        
        if metric_type:
            filtered = [m for m in filtered if m.metric_type == metric_type]
        
        return filtered
    
    def get_metric_summary(self) -> Dict[str, Any]:
        """
        Get summary of collected metrics.
        
        Returns:
            Summary statistics
        """
        total_metrics = len(self.metrics)
        
        # Count by type
        type_counts = {}
        for metric in self.metrics:
            metric_type = metric.metric_type.value
            type_counts[metric_type] = type_counts.get(metric_type, 0) + 1
        
        # Calculate stats for timers
        timers = [m for m in self.metrics if m.metric_type == MetricType.TIMER]
        timer_stats = {}
        
        if timers:
            timer_values = [t.value for t in timers]
            timer_stats = {
                'count': len(timer_values),
                'total_ms': sum(timer_values),
                'avg_ms': sum(timer_values) / len(timer_values),
                'min_ms': min(timer_values),
                'max_ms': max(timer_values),
            }
        
        return {
            'total_metrics': total_metrics,
            'type_counts': type_counts,
            'timer_stats': timer_stats,
            'uptime_seconds': (datetime.utcnow() - self._start_time).total_seconds(),
        }
    
    def clear_metrics(self) -> None:
        """Clear all collected metrics."""
        self.metrics = []
        logger.info("Metrics cleared")
    
    def export_metrics(self) -> List[Dict[str, Any]]:
        """
        Export metrics in serializable format.
        
        Returns:
            List of metric dictionaries
        """
        return [m.to_dict() for m in self.metrics]


# Common metric names (constants for consistency)
class MetricNames:
    """Standard metric names used throughout the application."""
    
    # PR Review metrics
    REVIEW_STARTED = "review.started"
    REVIEW_COMPLETED = "review.completed"
    REVIEW_FAILED = "review.failed"
    REVIEW_DURATION_MS = "review.duration_ms"
    REVIEW_ITERATIONS = "review.iterations"
    
    # LLM metrics
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE_TIME_MS = "llm.response_time_ms"
    LLM_TOKENS_USED = "llm.tokens_used"
    LLM_ERROR = "llm.error"
    
    # Static analysis metrics
    STATIC_ANALYSIS_DURATION_MS = "static_analysis.duration_ms"
    STATIC_ANALYSIS_ISSUES = "static_analysis.issues"
    
    # GitHub API metrics
    GITHUB_API_REQUEST = "github.api.request"
    GITHUB_API_RESPONSE_TIME_MS = "github.api.response_time_ms"
    GITHUB_API_ERROR = "github.api.error"
    
    # Storage metrics
    S3_UPLOAD = "s3.upload"
    S3_DOWNLOAD = "s3.download"
    S3_ERROR = "s3.error"
    
    # Webhook metrics
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"
    WEBHOOK_IGNORED = "webhook.ignored"


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get the global metrics collector instance.
    
    Returns:
        MetricsCollector instance
    
    Raises:
        RuntimeError: If collector not initialized
    """
    if _metrics_collector is None:
        raise RuntimeError("Metrics collector not initialized. Call setup_metrics() first.")
    return _metrics_collector


def setup_metrics(settings: Settings) -> MetricsCollector:
    """
    Initialize the global metrics collector.
    
    Args:
        settings: Application settings
    
    Returns:
        Initialized MetricsCollector
    """
    global _metrics_collector
    _metrics_collector = MetricsCollector(settings)
    return _metrics_collector


def record_metric(
    name: str,
    value: float,
    metric_type: MetricType = MetricType.COUNTER,
    tags: Optional[Dict[str, str]] = None,
) -> None:
    """
    Convenience function to record a metric.
    
    Args:
        name: Metric name
        value: Metric value
        metric_type: Type of metric
        tags: Optional tags
    """
    try:
        collector = get_metrics_collector()
        
        if metric_type == MetricType.COUNTER:
            collector.record_counter(name, value, tags)
        elif metric_type == MetricType.GAUGE:
            collector.record_gauge(name, value, tags)
        elif metric_type == MetricType.HISTOGRAM:
            collector.record_histogram(name, value, tags)
        elif metric_type == MetricType.TIMER:
            collector.record_timer(name, value, tags)
            
    except RuntimeError:
        # Metrics not initialized - silently skip
        pass