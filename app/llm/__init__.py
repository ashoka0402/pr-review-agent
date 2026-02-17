"""
LLM integration module for code review.

This module provides:
- Structured schemas for LLM outputs
- Constrained prompts for code review
- LLM client abstraction (Anthropic/OpenAI)
"""

from app.llm.model import LLMClient, get_llm_client
from app.llm.schemas import (
    CodeReview,
    ReviewRecommendation,
    ReviewComment,
    Finding,
    InlineComment,
    Category,
    Severity,
)

__all__ = [
    "CodeReview",
    "ReviewRecommendation",
    "ReviewComment",
    "Finding",
    "InlineComment",
    "Category",
    "Severity",
]