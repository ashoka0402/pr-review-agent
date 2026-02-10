"""
Constrained, schema-driven prompts for LLM-based code review.

These prompts enforce structured outputs and guide the LLM to produce
actionable, specific feedback aligned with our schemas.
"""

from typing import Dict, List, Optional
from app.llm.schemas import Category, Severity


SYSTEM_PROMPT = """You are an expert code reviewer for a pull request review system. Your role is to provide actionable, specific, and constructive feedback on code changes.

**Core Principles:**
1. Be specific and actionable - avoid generic statements
2. Focus on logic, security, performance, and maintainability
3. Provide code suggestions when possible
4. Acknowledge good practices and improvements
5. Assess your own confidence in each comment

**Severity Levels:**
- CRITICAL: Security vulnerabilities, data loss risks, breaking changes
- ERROR: Logic bugs, incorrect implementations, significant issues
- WARNING: Code smells, potential issues, performance concerns
- INFO: Suggestions, best practices, documentation improvements

**Categories:**
- logic: Correctness, edge cases, business logic
- security: Vulnerabilities, auth issues, data exposure
- performance: Inefficiencies, scalability concerns
- maintainability: Code clarity, complexity, technical debt
- testing: Test coverage, test quality
- documentation: Comments, docstrings, README
- style: Code formatting, naming conventions
- best_practices: Design patterns, idioms

**Output Format:**
You must respond with valid JSON matching this schema:
{
  "summary": {
    "overview": "Executive summary of changes (50-500 chars)",
    "key_concerns": ["concern1", "concern2"],
    "positive_aspects": ["positive1", "positive2"],
    "risk_assessment": "low|medium|high|critical"
  },
  "comments": [
    {
      "file_path": "path/to/file.py",
      "line_number": 42,
      "severity": "error|warning|info|critical",
      "category": "logic|security|performance|maintainability|testing|documentation|style|best_practices",
      "message": "Specific, actionable feedback (10-500 chars)",
      "suggestion": "Optional code fix or alternative approach",
      "confidence": 0.85
    }
  ],
  "recommendation": "APPROVE|COMMENT|REQUEST_CHANGES",
  "confidence": {
    "overall": 0.8,
    "needs_human_review": false,
    "reasoning": "Brief explanation of confidence",
    "uncertain_areas": ["area1", "area2"]
  }
}

**Rules:**
- Maximum 50 comments per review
- Each message must be 10-500 characters
- Avoid generic phrases like "consider refactoring" without specifics
- Include line numbers from the diff, not original file
- Confidence scores between 0.0 and 1.0
- If you see CRITICAL or ERROR issues, recommendation should be REQUEST_CHANGES
- If only INFO/WARNING issues, recommendation can be COMMENT or APPROVE
"""


def build_review_prompt(
    pr_title: str,
    pr_description: Optional[str],
    diff_content: str,
    static_analysis_results: Optional[Dict] = None,
    risk_signals: Optional[Dict] = None,
    file_context: Optional[Dict[str, str]] = None,
) -> str:
    """
    Build the user prompt for code review.
    
    Args:
        pr_title: Pull request title
        pr_description: Pull request description/body
        diff_content: Unified diff of changes
        static_analysis_results: Results from linting, security scanning, complexity analysis
        risk_signals: Risk indicators from heuristic analysis
        file_context: Additional file content context {file_path: content}
    
    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "# Pull Request Review",
        f"\n## PR Title\n{pr_title}",
    ]
    
    if pr_description:
        prompt_parts.append(f"\n## PR Description\n{pr_description}")
    
    # Add static analysis results if available
    if static_analysis_results:
        prompt_parts.append("\n## Static Analysis Results")
        
        if "linting" in static_analysis_results:
            linting = static_analysis_results["linting"]
            if linting.get("issues"):
                prompt_parts.append(f"\n### Linting Issues ({len(linting['issues'])} found)")
                for issue in linting["issues"][:20]:  # Limit to 20 issues
                    prompt_parts.append(
                        f"- {issue['file']}:{issue['line']} [{issue['code']}] {issue['message']}"
                    )
        
        if "security" in static_analysis_results:
            security = static_analysis_results["security"]
            if security.get("issues"):
                prompt_parts.append(f"\n### Security Issues ({len(security['issues'])} found)")
                for issue in security["issues"][:20]:
                    prompt_parts.append(
                        f"- {issue['file']}:{issue['line']} [{issue['severity']}] {issue['issue_text']}"
                    )
        
        if "complexity" in static_analysis_results:
            complexity = static_analysis_results["complexity"]
            if complexity.get("high_complexity_functions"):
                prompt_parts.append("\n### High Complexity Functions")
                for func in complexity["high_complexity_functions"][:10]:
                    prompt_parts.append(
                        f"- {func['function']} in {func['file']}: complexity={func['complexity']}"
                    )
    
    # Add risk signals
    if risk_signals:
        prompt_parts.append("\n## Risk Signals")
        if risk_signals.get("is_large_pr"):
            prompt_parts.append(f"⚠️ Large PR: {risk_signals.get('total_changes', 0)} lines changed")
        if risk_signals.get("critical_files"):
            prompt_parts.append(f"⚠️ Critical files modified: {', '.join(risk_signals['critical_files'][:5])}")
        if risk_signals.get("has_db_migration"):
            prompt_parts.append("⚠️ Contains database migrations")
        if risk_signals.get("security_sensitive_files"):
            prompt_parts.append(f"⚠️ Security-sensitive files: {', '.join(risk_signals['security_sensitive_files'][:5])}")
    
    # Add the diff
    prompt_parts.append(f"\n## Code Changes\n```diff\n{diff_content}\n```")
    
    # Add file context if available
    if file_context:
        prompt_parts.append("\n## Additional File Context")
        for file_path, content in file_context.items():
            # Truncate large files
            truncated_content = content[:5000] + "..." if len(content) > 5000 else content
            prompt_parts.append(f"\n### {file_path}\n```\n{truncated_content}\n```")
    
    # Add instructions
    prompt_parts.append(
        "\n## Instructions\n"
        "Review the code changes above and provide structured feedback as JSON. "
        "Focus on correctness, security, performance, and maintainability. "
        "Be specific and actionable. Acknowledge good practices. "
        "Use the static analysis results to inform your review but add your own insights."
    )
    
    return "\n".join(prompt_parts)


def build_refinement_prompt(
    original_review: Dict,
    feedback: str,
    iteration: int,
) -> str:
    """
    Build a prompt for refining an existing review based on feedback.
    
    Args:
        original_review: The previous review output
        feedback: Feedback or additional context for refinement
        iteration: Current iteration number
    
    Returns:
        Formatted refinement prompt
    """
    return f"""# Review Refinement (Iteration {iteration})

## Previous Review
{original_review}

## Feedback/Additional Context
{feedback}

## Instructions
Refine the previous review based on the feedback above. You may:
- Add new comments if issues were missed
- Remove or modify comments that are incorrect
- Adjust severity levels or confidence scores
- Update the overall recommendation

Maintain the same JSON schema as before. Focus on improving accuracy and actionability.
"""


def build_confidence_assessment_prompt(
    review: Dict,
    context: Dict,
) -> str:
    """
    Build a prompt for assessing confidence in a review.
    
    Args:
        review: The review to assess
        context: Additional context (PR size, complexity, etc.)
    
    Returns:
        Formatted confidence assessment prompt
    """
    return f"""# Review Confidence Assessment

## Review to Assess
{review}

## Context
- PR size: {context.get('pr_size', 'unknown')}
- Files changed: {context.get('files_changed', 0)}
- Languages: {context.get('languages', [])}
- Has tests: {context.get('has_tests', False)}

## Instructions
Assess your confidence in this review. Consider:
- Complexity of the changes
- Availability of context (tests, documentation)
- Clarity of the code
- Your familiarity with the patterns/frameworks used

Respond with JSON:
{{
  "overall": 0.85,
  "needs_human_review": false,
  "reasoning": "Brief explanation",
  "uncertain_areas": ["area1", "area2"]
}}
"""