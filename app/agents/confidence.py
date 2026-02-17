"""
Confidence scoring and evaluation for PR reviews.

Evaluates the quality and reliability of generated reviews,
determining when human review is needed.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from app.llm.schemas import CodeReview, Severity, Category

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceFactors:
    """Factors that influence confidence in a review."""
    
    # PR characteristics
    pr_size: str = "medium"  # "small", "medium", "large", "very_large"
    files_changed: int = 0
    lines_changed: int = 0
    languages: List[str] = field(default_factory=list)
    has_tests: bool = False
    
    # Static analysis coverage
    linting_coverage: float = 0.0  # 0.0-1.0
    security_scan_coverage: float = 0.0  # 0.0-1.0
    complexity_analysis_coverage: float = 0.0  # 0.0-1.0
    
    # Review characteristics
    num_findings: int = 0
    num_inline_comments: int = 0
    avg_finding_confidence: float = 0.5  # 0.0-1.0
    has_critical_issues: bool = False
    has_security_issues: bool = False
    
    # Context availability
    has_description: bool = False
    has_related_files: bool = False
    known_patterns: bool = False


class ConfidenceEvaluation:
    """Result of confidence evaluation."""
    
    def __init__(
        self,
        overall_score: float,
        level: str,
        factors: ConfidenceFactors,
    ):
        self.overall_score = overall_score
        self.level = level  # "high", "medium", "low"
        self.factors = factors


class ConfidenceEvaluator:
    """Evaluator for assessing review confidence."""
    
    def __init__(self, confidence_threshold: float = 0.7):
        """
        Initialize confidence evaluator.
        
        Args:
            confidence_threshold: Minimum confidence for approval
        """
        self.threshold = confidence_threshold
    
    def evaluate(
        self,
        review: CodeReview,
        context: Dict[str, Any],
    ) -> ConfidenceEvaluation:
        """
        Evaluate confidence in a review.
        
        Args:
            review: The generated review
            context: Review context (PR info, static analysis results, etc.)
        
        Returns:
            Evaluation results with confidence score and recommendations
        """
        try:
            # Extract factors from context
            factors = self._extract_factors(review, context)
            
            # Calculate overall confidence score
            overall_score = self._calculate_confidence_score(review, factors)
            
            # Determine confidence level
            if overall_score >= 0.85:
                level = "high"
            elif overall_score >= 0.65:
                level = "medium"
            else:
                level = "low"
            
            logger.info(
                f"Confidence evaluation: {level} ({overall_score:.2f})",
                extra={
                    "pr_size": factors.pr_size,
                    "findings": factors.num_findings,
                    "has_critical": factors.has_critical_issues,
                }
            )
            
            return ConfidenceEvaluation(
                overall_score=overall_score,
                level=level,
                factors=factors,
            )
            
        except Exception as e:
            logger.error(f"Confidence evaluation failed: {e}", exc_info=True)
            # Return default medium confidence on error
            return ConfidenceEvaluation(
                overall_score=0.65,
                level="medium",
                factors=ConfidenceFactors(),
            )
    
    def _extract_factors(
        self,
        review: CodeReview,
        context: Dict[str, Any],
    ) -> ConfidenceFactors:
        """Extract confidence factors from review and context."""
        
        # PR characteristics from context
        pr_info = context.get("pr_info", {})
        diff_info = context.get("diff_info")
        static_analysis = context.get("static_analysis", {})
        
        # Safe defaults if diff_info missing
        if diff_info:
            lines_changed = getattr(diff_info, 'total_changes', 0)
            files_changed = getattr(diff_info, 'files_changed', 0)
            file_names = [getattr(f, 'filename', '') for f in getattr(diff_info, 'file_changes', [])]
        else:
            lines_changed = 0
            files_changed = 0
            file_names = []
        
        # Determine PR size
        if lines_changed < 100:
            pr_size = "small"
        elif lines_changed < 500:
            pr_size = "medium"
        elif lines_changed < 1000:
            pr_size = "large"
        else:
            pr_size = "very_large"
        
        # Static analysis coverage
        linting_files = len(static_analysis.get("linting", {}).get("files_analyzed", []))
        security_files = len(static_analysis.get("security", {}).get("files_analyzed", []))
        complexity_files = len(static_analysis.get("complexity", {}).get("files_analyzed", []))
        
        linting_coverage = linting_files / max(files_changed, 1)
        security_coverage = security_files / max(files_changed, 1)
        complexity_coverage = complexity_files / max(files_changed, 1)
        
        # Detect tests
        has_tests = any("test" in f.lower() for f in file_names)
        
        # Review characteristics from CodeReview object
        num_findings = len(review.findings) if review.findings else 0
        num_inline_comments = len(review.inline_comments) if review.inline_comments else 0
        
        # Calculate average finding severity as confidence indicator
        if review.findings:
            severity_scores = {
                "critical": 0.9,
                "high": 0.8,
                "medium": 0.7,
                "low": 0.6,
                "info": 0.5,
            }
            avg_confidence = sum(
                severity_scores.get(f.severity.lower(), 0.5) 
                for f in review.findings
            ) / len(review.findings)
        else:
            avg_confidence = 0.7
        
        # Check for critical/security issues
        has_critical = any(
            f.severity.lower() == "critical" 
            for f in (review.findings or [])
        )
        has_security = any(
            "security" in f.category.lower() 
            for f in (review.findings or [])
        )
        
        # Languages (derive from file extensions)
        languages = list({
            f.split(".")[-1]
            for f in file_names
            if "." in f
        })
        
        return ConfidenceFactors(
            pr_size=pr_size,
            files_changed=files_changed,
            lines_changed=lines_changed,
            languages=languages,
            has_tests=has_tests,
            linting_coverage=min(linting_coverage, 1.0),
            security_scan_coverage=min(security_coverage, 1.0),
            complexity_analysis_coverage=min(complexity_coverage, 1.0),
            num_findings=num_findings,
            num_inline_comments=num_inline_comments,
            avg_finding_confidence=avg_confidence,
            has_critical_issues=has_critical,
            has_security_issues=has_security,
            has_description=bool(pr_info.get("description")),
            has_related_files=bool(context.get("file_context")),
            known_patterns=True,
        )
    
    def _calculate_confidence_score(
        self,
        review: CodeReview,
        factors: ConfidenceFactors,
    ) -> float:
        """Calculate overall confidence score for a review."""
        
        scores = []
        
        # Factor 1: PR size (smaller = more confident)
        size_scores = {
            "small": 1.0,
            "medium": 0.85,
            "large": 0.65,
            "very_large": 0.45,
        }
        scores.append(size_scores.get(factors.pr_size, 0.5))
        
        # Factor 2: Static analysis coverage (higher = more confident)
        avg_coverage = (
            factors.linting_coverage +
            factors.security_scan_coverage +
            factors.complexity_analysis_coverage
        ) / 3.0
        scores.append(avg_coverage)
        
        # Factor 3: Finding confidence
        scores.append(factors.avg_finding_confidence)
        
        # Factor 4: Review completeness (findings + comments)
        completeness = (min(factors.num_findings / 5.0, 1.0) + 
                       min(factors.num_inline_comments / 10.0, 1.0)) / 2.0
        scores.append(completeness)
        
        # Factor 5: Context availability
        context_score = 0.0
        if factors.has_description:
            context_score += 0.25
        if factors.has_tests:
            context_score += 0.25
        if factors.has_related_files:
            context_score += 0.25
        if factors.known_patterns:
            context_score += 0.25
        scores.append(context_score)
        
        # Factor 6: Risk (critical issues lower confidence)
        if factors.has_critical_issues:
            scores.append(0.6)
        elif factors.has_security_issues:
            scores.append(0.7)
        else:
            scores.append(0.9)
        
        # Calculate weighted average
        overall_confidence = sum(scores) / len(scores)
        
        # Apply ceiling based on PR size
        if factors.pr_size == "very_large":
            overall_confidence = min(overall_confidence, 0.75)
        elif factors.pr_size == "large":
            overall_confidence = min(overall_confidence, 0.85)
        
        return overall_confidence


# Module-level function for backward compatibility
def calculate_confidence_score(
    review: CodeReview,
    context: Dict[str, Any],
) -> float:
    """
    Calculate confidence score for a review.
    
    This is a module-level function for backward compatibility.
    Consider using ConfidenceEvaluator.evaluate() for full evaluation.
    
    Args:
        review: The generated review
        context: Review context dictionary
    
    Returns:
        Confidence score (0.0-1.0)
    """
    evaluator = ConfidenceEvaluator()
    evaluation = evaluator.evaluate(review, context)
    return evaluation.overall_score