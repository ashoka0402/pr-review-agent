"""
Confidence scoring and evaluation for PR reviews.

Evaluates the quality and reliability of generated reviews,
determining when human review is needed.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from app.llm.schemas import CodeReview, Severity, Category

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceFactors:
    """Factors that influence confidence in a review."""
    
    # PR characteristics
    pr_size: str  # "small", "medium", "large", "very_large"
    files_changed: int
    lines_changed: int
    languages: List[str]
    has_tests: bool
    
    # Static analysis coverage
    linting_coverage: float  # 0.0-1.0
    security_scan_coverage: float  # 0.0-1.0
    complexity_analysis_coverage: float  # 0.0-1.0
    
    # Review characteristics
    num_comments: int
    avg_comment_confidence: float  # 0.0-1.0
    has_critical_issues: bool
    has_security_issues: bool
    
    # Context availability
    has_description: bool
    has_related_files: bool
    known_patterns: bool  # Whether code uses familiar patterns


def calculate_confidence_score(
    review: CodeReview,
    factors: ConfidenceFactors,
) -> float:
    """
    Calculate overall confidence score for a review.
    
    Confidence is based on:
    - PR size and complexity
    - Static analysis coverage
    - Review comment quality
    - Context availability
    
    Args:
        review: The generated review
        factors: Contextual factors
    
    Returns:
        Confidence score between 0.0 and 1.0
    """
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
    
    # Factor 3: Review comment confidence
    scores.append(factors.avg_comment_confidence)
    
    # Factor 4: Context availability
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
    
    # Factor 5: Language familiarity (Python = high confidence)
    if "python" in [lang.lower() for lang in factors.languages]:
        scores.append(0.9)
    else:
        scores.append(0.6)  # Lower confidence for other languages
    
    # Factor 6: Penalty for critical issues without high confidence
    if factors.has_critical_issues:
        critical_comments = review.get_comments_by_severity(Severity.CRITICAL)
        if critical_comments:
            avg_critical_confidence = sum(c.confidence for c in critical_comments) / len(critical_comments)
            if avg_critical_confidence < 0.8:
                scores.append(0.5)  # Penalize low-confidence critical issues
    
    # Calculate weighted average
    overall_confidence = sum(scores) / len(scores)
    
    # Apply ceiling based on PR size
    if factors.pr_size == "very_large":
        overall_confidence = min(overall_confidence, 0.75)
    
    logger.info(f"Calculated confidence: {overall_confidence:.2f} (factors: {len(scores)})")
    return overall_confidence


def needs_human_review(
    review: CodeReview,
    confidence_score: float,
    threshold: float = 0.7,
) -> bool:
    """
    Determine if human review is needed.
    
    Args:
        review: The generated review
        confidence_score: Overall confidence score
        threshold: Confidence threshold (default: 0.7)
    
    Returns:
        True if human review is recommended
    """
    # Always need human review if confidence is below threshold
    if confidence_score < threshold:
        return True
    
    # Need human review for critical issues
    if review.has_blocking_issues():
        critical_comments = review.get_comments_by_severity(Severity.CRITICAL)
        # If any critical comment has low confidence, need human review
        if any(c.confidence < 0.8 for c in critical_comments):
            return True
    
    # Need human review for security issues with low confidence
    security_comments = review.get_comments_by_category(Category.SECURITY)
    if security_comments:
        if any(c.confidence < 0.75 for c in security_comments):
            return True
    
    return False


def identify_uncertain_areas(
    review: CodeReview,
    factors: ConfidenceFactors,
) -> List[str]:
    """
    Identify specific areas where the review is uncertain.
    
    Args:
        review: The generated review
        factors: Contextual factors
    
    Returns:
        List of uncertain areas
    """
    uncertain = []
    
    # Large PRs are inherently uncertain
    if factors.pr_size in ["large", "very_large"]:
        uncertain.append(f"Large PR ({factors.lines_changed} lines changed)")
    
    # Low comment confidence
    low_confidence_comments = [c for c in review.comments if c.confidence < 0.7]
    if low_confidence_comments:
        files = set(c.file_path for c in low_confidence_comments)
        uncertain.append(f"Low confidence in {len(files)} file(s)")
    
    # Missing static analysis coverage
    if factors.linting_coverage < 0.5:
        uncertain.append("Limited linting coverage")
    if factors.security_scan_coverage < 0.5:
        uncertain.append("Limited security scan coverage")
    
    # No tests
    if not factors.has_tests:
        uncertain.append("No test files in PR")
    
    # Unfamiliar languages
    non_python = [lang for lang in factors.languages if lang.lower() != "python"]
    if non_python:
        uncertain.append(f"Non-Python languages: {', '.join(non_python)}")
    
    return uncertain


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
    ) -> Dict[str, Any]:
        """
        Evaluate confidence in a review.
        
        Args:
            review: The generated review
            context: Review context (PR info, static analysis results, etc.)
        
        Returns:
            Evaluation results with confidence score and recommendations
        """
        # Extract factors from context
        factors = self._extract_factors(review, context)
        
        # Calculate confidence score
        confidence_score = calculate_confidence_score(review, factors)
        
        # Determine if human review is needed
        needs_human = needs_human_review(review, confidence_score, self.threshold)
        
        # Identify uncertain areas
        uncertain_areas = identify_uncertain_areas(review, factors)
        
        # Generate reasoning
        reasoning = self._generate_reasoning(
            confidence_score,
            factors,
            needs_human,
            uncertain_areas
        )
        
        return {
            "overall_confidence": confidence_score,
            "needs_human_review": needs_human,
            "reasoning": reasoning,
            "uncertain_areas": uncertain_areas,
            "factors": factors,
        }
    
    def _extract_factors(
        self,
        review: CodeReview,
        context: Dict[str, Any],
    ) -> ConfidenceFactors:
        """Extract confidence factors from context."""
        
        # PR characteristics
        pr_info = context.get("pr_info", {})
        diff_info = context.get("diff_info", {})
        static_analysis = context.get("static_analysis", {})
        
        # Determine PR size
        lines_changed = diff_info.get("total_changes", 0)
        if lines_changed < 100:
            pr_size = "small"
        elif lines_changed < 500:
            pr_size = "medium"
        elif lines_changed < 1000:
            pr_size = "large"
        else:
            pr_size = "very_large"
        
        # Calculate static analysis coverage
        files_changed = len(diff_info.get("files", []))
        linting_files = len(static_analysis.get("linting", {}).get("files_analyzed", []))
        security_files = len(static_analysis.get("security", {}).get("files_analyzed", []))
        complexity_files = len(static_analysis.get("complexity", {}).get("files_analyzed", []))
        
        linting_coverage = linting_files / max(files_changed, 1)
        security_coverage = security_files / max(files_changed, 1)
        complexity_coverage = complexity_files / max(files_changed, 1)
        
        # Calculate average comment confidence
        avg_confidence = (
            sum(c.confidence for c in review.comments) / len(review.comments)
            if review.comments else 0.5
        )
        
        # Detect tests
        files = diff_info.get("files", [])
        has_tests = any("test" in f.lower() for f in files)
        
        return ConfidenceFactors(
            pr_size=pr_size,
            files_changed=files_changed,
            lines_changed=lines_changed,
            languages=diff_info.get("languages", []),
            has_tests=has_tests,
            linting_coverage=linting_coverage,
            security_scan_coverage=security_coverage,
            complexity_analysis_coverage=complexity_coverage,
            num_comments=len(review.comments),
            avg_comment_confidence=avg_confidence,
            has_critical_issues=review.has_blocking_issues(),
            has_security_issues=bool(review.get_comments_by_category(Category.SECURITY)),
            has_description=bool(pr_info.get("description")),
            has_related_files=bool(context.get("file_context")),
            known_patterns=True,  # Could be enhanced with pattern detection
        )
    
    def _generate_reasoning(
        self,
        confidence_score: float,
        factors: ConfidenceFactors,
        needs_human: bool,
        uncertain_areas: List[str],
    ) -> str:
        """Generate human-readable reasoning for confidence assessment."""
        
        if confidence_score >= 0.85:
            quality = "high"
        elif confidence_score >= 0.7:
            quality = "moderate"
        else:
            quality = "low"
        
        reasoning_parts = [
            f"Review confidence is {quality} ({confidence_score:.2f}).",
        ]
        
        # Add size context
        reasoning_parts.append(
            f"PR is {factors.pr_size} ({factors.lines_changed} lines, "
            f"{factors.files_changed} files)."
        )
        
        # Add static analysis context
        if factors.linting_coverage > 0.8:
            reasoning_parts.append("Good static analysis coverage.")
        elif factors.linting_coverage < 0.5:
            reasoning_parts.append("Limited static analysis coverage.")
        
        # Add human review recommendation
        if needs_human:
            reasoning_parts.append("Human review is recommended.")
        
        return " ".join(reasoning_parts)