"""
Structured schemas for LLM-based code review outputs.

These Pydantic models define the expected structure of LLM responses,
ensuring constrained, parseable outputs.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    """Comment severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReviewRecommendation(str, Enum):
    """Overall PR review recommendation."""
    APPROVE = "APPROVE"
    COMMENT = "COMMENT"
    REQUEST_CHANGES = "REQUEST_CHANGES"


class Category(str, Enum):
    """Review comment categories."""
    LOGIC = "logic"
    SECURITY = "security"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    STYLE = "style"
    BEST_PRACTICES = "best_practices"


class ReviewComment(BaseModel):
    """Individual inline review comment."""
    
    file_path: str = Field(
        ...,
        description="Relative path to the file being commented on"
    )
    line_number: int = Field(
        ...,
        ge=1,
        description="Line number in the diff (not the original file)"
    )
    severity: Severity = Field(
        ...,
        description="Severity level of the issue"
    )
    category: Category = Field(
        ...,
        description="Category of the review comment"
    )
    message: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Clear, actionable feedback message"
    )
    suggestion: Optional[str] = Field(
        None,
        max_length=300,
        description="Optional code suggestion or fix"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for this comment (0.0-1.0)"
    )

    @field_validator('message')
    @classmethod
    def validate_message_quality(cls, v: str) -> str:
        """Ensure message is actionable and specific."""
        # Avoid generic phrases
        generic_phrases = [
            "consider refactoring",
            "this could be improved",
            "think about",
            "maybe you should",
        ]
        lower_msg = v.lower()
        if any(phrase in lower_msg for phrase in generic_phrases):
            if len(v) < 50:  # If too short and generic, it's likely not actionable
                raise ValueError(
                    "Message is too generic. Provide specific, actionable feedback."
                )
        return v


class ConfidenceScore(BaseModel):
    """Confidence assessment for review quality."""
    
    overall: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence in the review (0.0-1.0)"
    )
    needs_human_review: bool = Field(
        ...,
        description="Whether human review is recommended"
    )
    reasoning: str = Field(
        ...,
        max_length=300,
        description="Brief explanation of confidence score"
    )
    uncertain_areas: List[str] = Field(
        default_factory=list,
        description="Specific areas where the model is uncertain"
    )


class ReviewSummary(BaseModel):
    """High-level summary of the PR review."""
    
    overview: str = Field(
        ...,
        min_length=50,
        max_length=500,
        description="Executive summary of the PR changes"
    )
    key_concerns: List[str] = Field(
        default_factory=list,
        max_items=5,
        description="Top 3-5 concerns or issues identified"
    )
    positive_aspects: List[str] = Field(
        default_factory=list,
        max_items=3,
        description="Notable positive aspects of the PR"
    )
    risk_assessment: str = Field(
        ...,
        description="Assessment of overall risk level (low/medium/high/critical)"
    )

    @field_validator('risk_assessment')
    @classmethod
    def validate_risk_level(cls, v: str) -> str:
        """Ensure risk assessment is one of the allowed values."""
        allowed = ["low", "medium", "high", "critical"]
        if v.lower() not in allowed:
            raise ValueError(f"Risk assessment must be one of {allowed}")
        return v.lower()


class CodeReview(BaseModel):
    """Complete structured code review output from LLM."""
    
    summary: ReviewSummary = Field(
        ...,
        description="High-level summary of the review"
    )
    comments: List[ReviewComment] = Field(
        default_factory=list,
        max_items=50,
        description="Inline review comments (max 50 to prevent spam)"
    )
    recommendation: ReviewRecommendation = Field(
        ...,
        description="Overall recommendation (APPROVE/COMMENT/REQUEST_CHANGES)"
    )
    confidence: ConfidenceScore = Field(
        ...,
        description="Confidence assessment for this review"
    )

    @field_validator('comments')
    @classmethod
    def validate_comment_severity(cls, comments: List[ReviewComment]) -> List[ReviewComment]:
        """Ensure critical/error comments result in REQUEST_CHANGES recommendation."""
        # This is a soft validation - the agent layer will enforce the final logic
        return comments

    def has_blocking_issues(self) -> bool:
        """Check if review has critical or error-level issues."""
        return any(
            comment.severity in [Severity.CRITICAL, Severity.ERROR]
            for comment in self.comments
        )

    def get_comments_by_severity(self, severity: Severity) -> List[ReviewComment]:
        """Filter comments by severity level."""
        return [c for c in self.comments if c.severity == severity]

    def get_comments_by_category(self, category: Category) -> List[ReviewComment]:
        """Filter comments by category."""
        return [c for c in self.comments if c.category == category]