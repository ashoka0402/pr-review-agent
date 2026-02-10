"""
Risk scoring for pull requests.

Calculates overall risk scores based on review findings, static analysis,
and PR characteristics.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from app.llm.schemas import CodeReview, Severity, Category

logger = logging.getLogger(__name__)


@dataclass
class RiskScore:
    """Overall risk score for a PR."""
    
    total: float  # 0.0-100.0
    level: str  # "low", "medium", "high", "critical"
    
    # Component scores
    severity_score: float
    complexity_score: float
    size_score: float
    security_score: float
    test_coverage_score: float
    
    # Contributing factors
    blocking_issues: int
    total_issues: int
    lines_changed: int
    files_changed: int
    
    def __str__(self) -> str:
        return f"Risk: {self.level.upper()} ({self.total:.1f}/100)"


def calculate_risk_score(
    review: CodeReview,
    diff_info: Dict[str, Any],
    static_analysis: Optional[Dict[str, Any]] = None,
    risk_signals: Optional[Dict[str, Any]] = None,
) -> RiskScore:
    """
    Calculate overall risk score for a PR.
    
    Risk score is 0-100 where:
    - 0-25: Low risk
    - 26-50: Medium risk
    - 51-75: High risk
    - 76-100: Critical risk
    
    Args:
        review: CodeReview from LLM
        diff_info: PR diff information
        static_analysis: Static analysis results
        risk_signals: Risk signals from heuristic detection
    
    Returns:
        Comprehensive RiskScore object
    """
    # Component scores (each 0-100)
    severity_score = _calculate_severity_score(review)
    complexity_score = _calculate_complexity_score(static_analysis)
    size_score = _calculate_size_score(diff_info)
    security_score = _calculate_security_score(review, static_analysis)
    test_coverage_score = _calculate_test_coverage_score(diff_info, static_analysis)
    
    # Weighted average of components
    weights = {
        "severity": 0.35,     # Issues found have highest weight
        "security": 0.25,     # Security is critical
        "complexity": 0.15,   # Code complexity matters
        "size": 0.15,         # PR size affects risk
        "test_coverage": 0.10,  # Tests provide safety net
    }
    
    total_score = (
        severity_score * weights["severity"] +
        security_score * weights["security"] +
        complexity_score * weights["complexity"] +
        size_score * weights["size"] +
        test_coverage_score * weights["test_coverage"]
    )
    
    # Apply risk signals as multipliers
    if risk_signals:
        total_score = _apply_risk_signal_modifiers(total_score, risk_signals)
    
    # Determine risk level
    if total_score <= 25:
        level = "low"
    elif total_score <= 50:
        level = "medium"
    elif total_score <= 75:
        level = "high"
    else:
        level = "critical"
    
    # Count issues
    blocking_issues = len([
        c for c in review.comments
        if c.severity in [Severity.CRITICAL, Severity.ERROR]
    ])
    
    return RiskScore(
        total=total_score,
        level=level,
        severity_score=severity_score,
        complexity_score=complexity_score,
        size_score=size_score,
        security_score=security_score,
        test_coverage_score=test_coverage_score,
        blocking_issues=blocking_issues,
        total_issues=len(review.comments),
        lines_changed=diff_info.get("total_changes", 0),
        files_changed=len(diff_info.get("files", [])),
    )


def _calculate_severity_score(review: CodeReview) -> float:
    """
    Calculate risk score based on issue severity.
    
    Returns score 0-100 where higher means more risk.
    """
    if not review.comments:
        return 0.0
    
    # Weights for each severity level
    severity_weights = {
        Severity.CRITICAL: 100,
        Severity.ERROR: 60,
        Severity.WARNING: 30,
        Severity.INFO: 5,
    }
    
    # Calculate weighted sum
    total_weight = 0
    for comment in review.comments:
        weight = severity_weights.get(comment.severity, 0)
        # Reduce weight by confidence (low confidence issues count less)
        adjusted_weight = weight * comment.confidence
        total_weight += adjusted_weight
    
    # Normalize by number of comments (cap at 100)
    # More issues = higher risk, but with diminishing returns
    score = min(100, total_weight / max(len(review.comments), 1) * 1.5)
    
    return score


def _calculate_complexity_score(static_analysis: Optional[Dict[str, Any]]) -> float:
    """
    Calculate risk score based on code complexity.
    
    Returns score 0-100 where higher means more risk.
    """
    if not static_analysis or "complexity" not in static_analysis:
        return 30.0  # Default moderate risk if no data
    
    complexity_data = static_analysis["complexity"]
    
    # Count high-complexity functions
    high_complexity = complexity_data.get("high_complexity_functions", [])
    if not high_complexity:
        return 10.0
    
    # Average complexity of flagged functions
    avg_complexity = sum(
        func.get("complexity", 0)
        for func in high_complexity
    ) / len(high_complexity)
    
    # Map complexity to risk score
    # Complexity > 20 is very high risk
    if avg_complexity > 20:
        score = 90
    elif avg_complexity > 15:
        score = 70
    elif avg_complexity > 10:
        score = 50
    else:
        score = 30
    
    # Scale by number of complex functions
    num_complex = min(len(high_complexity), 10)
    score = score * (0.5 + 0.05 * num_complex)
    
    return min(100, score)


def _calculate_size_score(diff_info: Dict[str, Any]) -> float:
    """
    Calculate risk score based on PR size.
    
    Returns score 0-100 where higher means more risk.
    """
    lines_changed = diff_info.get("total_changes", 0)
    files_changed = len(diff_info.get("files", []))
    
    # Lines changed score
    if lines_changed < 50:
        lines_score = 5
    elif lines_changed < 200:
        lines_score = 20
    elif lines_changed < 500:
        lines_score = 40
    elif lines_changed < 1000:
        lines_score = 60
    else:
        lines_score = 80
    
    # Files changed score
    if files_changed < 3:
        files_score = 5
    elif files_changed < 10:
        files_score = 20
    elif files_changed < 25:
        files_score = 40
    else:
        files_score = 60
    
    # Combine (weighted average)
    return lines_score * 0.7 + files_score * 0.3


def _calculate_security_score(
    review: CodeReview,
    static_analysis: Optional[Dict[str, Any]],
) -> float:
    """
    Calculate risk score based on security concerns.
    
    Returns score 0-100 where higher means more risk.
    """
    score = 0.0
    
    # Check for security-related review comments
    security_comments = review.get_comments_by_category(Category.SECURITY)
    if security_comments:
        # Any security issue is significant
        critical_security = [
            c for c in security_comments
            if c.severity in [Severity.CRITICAL, Severity.ERROR]
        ]
        if critical_security:
            score = 95
        else:
            score = 60
    
    # Check static security analysis
    if static_analysis and "security" in static_analysis:
        security_issues = static_analysis["security"].get("issues", [])
        if security_issues:
            # Count by severity
            high_severity = len([
                i for i in security_issues
                if i.get("severity") in ["HIGH", "CRITICAL"]
            ])
            medium_severity = len([
                i for i in security_issues
                if i.get("severity") == "MEDIUM"
            ])
            
            if high_severity > 0:
                score = max(score, 90)
            elif medium_severity > 2:
                score = max(score, 60)
            elif security_issues:
                score = max(score, 40)
    
    return score


def _calculate_test_coverage_score(
    diff_info: Dict[str, Any],
    static_analysis: Optional[Dict[str, Any]],
) -> float:
    """
    Calculate risk score based on test coverage.
    
    Returns score 0-100 where higher means MORE risk (less coverage).
    """
    files = diff_info.get("files", [])
    
    # Check if PR includes test files
    has_tests = any("test" in f.lower() for f in files)
    
    # Check if PR modifies only test files
    only_tests = all("test" in f.lower() for f in files) if files else False
    
    if only_tests:
        return 0  # Test-only changes are low risk
    
    # Check for production code without tests
    has_production_code = any(
        not ("test" in f.lower() or f.endswith(".md") or f.endswith(".txt"))
        for f in files
    )
    
    if has_production_code and not has_tests:
        return 70  # Production code without tests is risky
    
    if has_production_code and has_tests:
        return 30  # Production code with tests is better
    
    # Check coverage data if available
    if static_analysis and "coverage" in static_analysis:
        coverage_pct = static_analysis["coverage"].get("coverage_percentage", 0)
        # Invert coverage to risk score
        return max(0, 100 - coverage_pct)
    
    return 40  # Default moderate risk


def _apply_risk_signal_modifiers(
    base_score: float,
    risk_signals: Dict[str, Any],
) -> float:
    """
    Apply risk signal modifiers to base score.
    
    Args:
        base_score: Base risk score 0-100
        risk_signals: Risk signals from detection
    
    Returns:
        Modified risk score
    """
    score = base_score
    
    # Large PR modifier
    if risk_signals.get("is_large_pr"):
        score *= 1.2
    
    # Critical files modifier
    if risk_signals.get("critical_files"):
        score *= 1.15
    
    # Database migration modifier
    if risk_signals.get("has_db_migration"):
        score *= 1.25
    
    # Security-sensitive files modifier
    if risk_signals.get("security_sensitive_files"):
        score *= 1.2
    
    # Missing tests modifier
    if risk_signals.get("missing_tests"):
        score *= 1.1
    
    # Cap at 100
    return min(100, score)


class RiskScorer:
    """Calculator for PR risk scores."""
    
    def __init__(self):
        """Initialize risk scorer."""
        pass
    
    def calculate(
        self,
        review_result: Dict[str, Any],
    ) -> RiskScore:
        """
        Calculate risk score from review result.
        
        Args:
            review_result: Complete review result from PRReviewer
        
        Returns:
            RiskScore object
        """
        return calculate_risk_score(
            review=review_result["review"],
            diff_info=review_result.get("diff_info", {}),
            static_analysis=review_result.get("static_analysis_summary"),
            risk_signals=review_result.get("risk_signals"),
        )
    
    def explain_score(self, risk_score: RiskScore) -> str:
        """
        Generate human-readable explanation of risk score.
        
        Args:
            risk_score: Calculated RiskScore
        
        Returns:
            Explanation text
        """
        parts = [
            f"Overall Risk: {risk_score.level.upper()} ({risk_score.total:.1f}/100)",
            "",
            "Component Breakdown:",
            f"- Issue Severity: {risk_score.severity_score:.1f}/100",
            f"- Security: {risk_score.security_score:.1f}/100",
            f"- Complexity: {risk_score.complexity_score:.1f}/100",
            f"- Size: {risk_score.size_score:.1f}/100",
            f"- Test Coverage: {risk_score.test_coverage_score:.1f}/100",
            "",
            f"Issues: {risk_score.total_issues} total ({risk_score.blocking_issues} blocking)",
            f"Changes: {risk_score.lines_changed} lines, {risk_score.files_changed} files",
        ]
        
        return "\n".join(parts)