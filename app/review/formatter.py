"""
Formatters for PR review output.

Converts structured review data into GitHub-compatible markdown
for inline comments and review summaries.
"""

import logging
from typing import Dict, List, Optional, Any

from app.llm.schemas import (
    CodeReview,
    ReviewComment,
    ReviewSummary,
    Severity,
    Category,
    ReviewRecommendation,
)

logger = logging.getLogger(__name__)


def format_inline_comment(comment: ReviewComment) -> str:
    """
    Format a single inline review comment as markdown.
    
    Args:
        comment: ReviewComment to format
    
    Returns:
        Markdown-formatted comment string
    """
    # Severity emoji mapping
    severity_emoji = {
        Severity.CRITICAL: "🚨",
        Severity.ERROR: "❌",
        Severity.WARNING: "⚠️",
        Severity.INFO: "ℹ️",
    }
    
    # Category emoji mapping
    category_emoji = {
        Category.LOGIC: "🔍",
        Category.SECURITY: "🔒",
        Category.PERFORMANCE: "⚡",
        Category.MAINTAINABILITY: "🔧",
        Category.TESTING: "✅",
        Category.DOCUMENTATION: "📝",
        Category.STYLE: "🎨",
        Category.BEST_PRACTICES: "💡",
    }
    
    parts = []
    
    # Header with severity and category
    emoji = severity_emoji.get(comment.severity, "")
    cat_emoji = category_emoji.get(comment.category, "")
    header = f"{emoji} **{comment.severity.value.upper()}** {cat_emoji} *{comment.category.value}*"
    parts.append(header)
    parts.append("")
    
    # Main message
    parts.append(comment.message)
    
    # Add suggestion if present
    if comment.suggestion:
        parts.append("")
        parts.append("**Suggestion:**")
        parts.append(f"```\n{comment.suggestion}\n```")
    
    # Add confidence indicator (only for low confidence)
    if comment.confidence < 0.7:
        parts.append("")
        parts.append(f"*Confidence: {comment.confidence:.0%} - Please verify*")
    
    return "\n".join(parts)


def format_review_summary(
    review: CodeReview,
    confidence: float,
    needs_human_review: bool,
    static_analysis_summary: Optional[Dict[str, int]] = None,
    risk_signals: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Format the overall review summary as markdown.
    
    This appears as the main review body on GitHub.
    
    Args:
        review: Complete CodeReview object
        confidence: Overall confidence score
        needs_human_review: Whether human review is recommended
        static_analysis_summary: Summary of static analysis results
        risk_signals: Risk signals detected
    
    Returns:
        Markdown-formatted summary
    """
    parts = []
    
    # Title
    parts.append("# AI Code Review")
    parts.append("")
    
    # Executive summary
    parts.append("## Summary")
    parts.append(review.summary.overview)
    parts.append("")
    
    # Risk assessment with visual indicator
    risk_emoji = {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴",
    }
    risk_level = review.summary.risk_assessment
    parts.append(
        f"**Risk Assessment:** {risk_emoji.get(risk_level, '⚪')} "
        f"{risk_level.upper()}"
    )
    parts.append("")
    
    # Key concerns
    if review.summary.key_concerns:
        parts.append("## ⚠️ Key Concerns")
        for concern in review.summary.key_concerns:
            parts.append(f"- {concern}")
        parts.append("")
    
    # Positive aspects
    if review.summary.positive_aspects:
        parts.append("##  Positive Aspects")
        for aspect in review.summary.positive_aspects:
            parts.append(f"- {aspect}")
        parts.append("")
    
    # Issue breakdown
    if review.comments:
        parts.append("##  Issue Breakdown")
        parts.append("")
        
        # Count by severity
        severity_counts = {}
        for comment in review.comments:
            severity = comment.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        parts.append("**By Severity:**")
        for severity in [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]:
            count = severity_counts.get(severity.value, 0)
            if count > 0:
                emoji = {"critical": "🚨", "error": "❌", "warning": "⚠️", "info": "ℹ️"}
                parts.append(f"- {emoji.get(severity.value, '')} {severity.value.upper()}: {count}")
        parts.append("")
        
        # Count by category
        category_counts = {}
        for comment in review.comments:
            category = comment.category.value
            category_counts[category] = category_counts.get(category, 0) + 1
        
        parts.append("**By Category:**")
        for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
            parts.append(f"- {category}: {count}")
        parts.append("")
    
    # Static analysis summary
    if static_analysis_summary:
        total_static_issues = sum(static_analysis_summary.values())
        if total_static_issues > 0:
            parts.append("##  Static Analysis")
            for tool, count in static_analysis_summary.items():
                if count > 0:
                    parts.append(f"- {tool}: {count} issues")
            parts.append("")
    
    # Risk signals
    if risk_signals:
        has_risks = any([
            risk_signals.get("is_large_pr"),
            risk_signals.get("critical_files"),
            risk_signals.get("has_db_migration"),
            risk_signals.get("security_sensitive_files"),
        ])
        
        if has_risks:
            parts.append("##  Risk Signals")
            if risk_signals.get("is_large_pr"):
                parts.append(f"- ⚠️ Large PR: {risk_signals.get('total_changes', 0)} lines changed")
            if risk_signals.get("critical_files"):
                critical = risk_signals["critical_files"][:3]
                parts.append(f"- ⚠️ Critical files modified: {', '.join(critical)}")
            if risk_signals.get("has_db_migration"):
                parts.append("- ⚠️ Database migration detected")
            if risk_signals.get("security_sensitive_files"):
                sensitive = risk_signals["security_sensitive_files"][:3]
                parts.append(f"- 🔒 Security-sensitive files: {', '.join(sensitive)}")
            parts.append("")
    
    # Confidence and human review notice
    parts.append("##  Review Confidence")
    confidence_level = "High" if confidence >= 0.8 else "Moderate" if confidence >= 0.7 else "Low"
    parts.append(f"**Confidence Level:** {confidence_level} ({confidence:.0%})")
    parts.append("")
    
    if needs_human_review:
        parts.append("⚠️ **Human review is recommended** due to:")
        if confidence < 0.7:
            parts.append("- Low confidence in automated analysis")
        if review.has_blocking_issues():
            parts.append("- Critical or error-level issues detected")
        if review.summary.risk_assessment in ["high", "critical"]:
            parts.append("- High risk assessment")
        parts.append("")
    
    # Recommendation
    recommendation_text = {
        ReviewRecommendation.APPROVE: "✅ **Approve** - No blocking issues found",
        ReviewRecommendation.COMMENT: "💬 **Comment** - Review feedback provided",
        ReviewRecommendation.REQUEST_CHANGES: "🔴 **Request Changes** - Blocking issues must be addressed",
    }
    parts.append("##  Recommendation")
    parts.append(recommendation_text.get(review.recommendation, "Unknown"))
    parts.append("")
    
    # Footer
    parts.append("---")
    parts.append("*This review was generated by an AI code review agent. "
                "Please use your judgment and verify critical findings.*")
    
    return "\n".join(parts)


class ReviewFormatter:
    """Formatter for review output."""
    
    def __init__(self):
        """Initialize formatter."""
        pass
    
    def format_for_github(
        self,
        review_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Format complete review for GitHub API.
        
        Args:
            review_result: Complete review result from PRReviewer
        
        Returns:
            Formatted data ready for GitHub API submission
        """
        review = review_result["review"]
        
        # Format inline comments
        inline_comments = []
        for comment in review.comments:
            inline_comments.append({
                "path": comment.file_path,
                "line": comment.line_number,
                "body": format_inline_comment(comment),
            })
        
        # Format review body
        review_body = format_review_summary(
            review=review,
            confidence=review_result["confidence"],
            needs_human_review=review_result["needs_human_review"],
            static_analysis_summary=review_result.get("static_analysis_summary"),
            risk_signals=review_result.get("risk_signals"),
        )
        
        # Map recommendation to GitHub event
        event_mapping = {
            ReviewRecommendation.APPROVE: "APPROVE",
            ReviewRecommendation.COMMENT: "COMMENT",
            ReviewRecommendation.REQUEST_CHANGES: "REQUEST_CHANGES",
        }
        event = event_mapping.get(
            review_result["recommendation"],
            "COMMENT"
        )
        
        return {
            "body": review_body,
            "event": event,
            "comments": inline_comments,
        }
    
    def format_for_slack(
        self,
        review_result: Dict[str, Any],
        pr_url: str,
    ) -> Dict[str, Any]:
        """
        Format review for Slack notification.
        
        Args:
            review_result: Complete review result
            pr_url: URL to the pull request
        
        Returns:
            Slack message blocks
        """
        review = review_result["review"]
        recommendation = review_result["recommendation"]
        
        # Color based on recommendation
        color_mapping = {
            ReviewRecommendation.APPROVE: "good",
            ReviewRecommendation.COMMENT: "warning",
            ReviewRecommendation.REQUEST_CHANGES: "danger",
        }
        color = color_mapping.get(recommendation, "#808080")
        
        # Build attachment
        fields = []
        
        # Risk assessment
        fields.append({
            "title": "Risk Assessment",
            "value": review.summary.risk_assessment.upper(),
            "short": True,
        })
        
        # Confidence
        confidence = review_result["confidence"]
        fields.append({
            "title": "Confidence",
            "value": f"{confidence:.0%}",
            "short": True,
        })
        
        # Issue count
        if review.comments:
            fields.append({
                "title": "Issues Found",
                "value": str(len(review.comments)),
                "short": True,
            })
        
        # Key concerns
        if review.summary.key_concerns:
            concerns_text = "\n".join(f"• {c}" for c in review.summary.key_concerns[:3])
            fields.append({
                "title": "Key Concerns",
                "value": concerns_text,
                "short": False,
            })
        
        return {
            "attachments": [
                {
                    "color": color,
                    "title": "AI Code Review Complete",
                    "title_link": pr_url,
                    "text": review.summary.overview,
                    "fields": fields,
                    "footer": "AI Code Review Agent",
                }
            ]
        }
    
    def format_comment_summary(self, review: CodeReview) -> str:
        """
        Format a brief comment summary for logging or notifications.
        
        Args:
            review: CodeReview object
        
        Returns:
            Brief text summary
        """
        summary_parts = [
            f"Review: {review.recommendation.value}",
            f"Comments: {len(review.comments)}",
            f"Risk: {review.summary.risk_assessment}",
        ]
        
        # Add severity breakdown
        severity_counts = {}
        for comment in review.comments:
            severity = comment.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        if severity_counts:
            breakdown = ", ".join(
                f"{sev}: {count}"
                for sev, count in severity_counts.items()
            )
            summary_parts.append(f"Issues: {breakdown}")
        
        return " | ".join(summary_parts)