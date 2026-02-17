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
    pr_description: str,
    diff_content: str,
    static_analysis_results: Optional[Dict],
    risk_signals: Optional[Dict],
    file_context: Optional[Dict[str, str]],
) -> str:
    """Build the review prompt for LLM."""
    
    prompt = f"""You are an expert code reviewer. Analyze this pull request and provide structured feedback.

## Pull Request Information
**Title:** {pr_title}
**Description:** {pr_description if pr_description else "No description provided"}

## Changes
```diff
{diff_content}
```

## Static Analysis Results
{format_static_analysis(static_analysis_results)}

## Risk Signals
{format_risk_signals(risk_signals)}

## Your Task
Analyze the PR and provide your review in JSON format with the following structure:

{{
  "summary": "Brief overall assessment of the PR",
  "risk_score": <number 0-10>,
  "recommendation": "<APPROVE|REQUEST_CHANGES|COMMENT>",
  "findings": [
    {{
      "category": "<Security|Code Quality|Performance|Best Practice|Testing|Documentation>",
      "severity": "<critical|high|medium|low|info>",
      "title": "Short title of the issue",
      "description": "Detailed explanation",
      "suggestion": "How to fix it",
      "file_path": "path/to/file.py",
      "line_number": 42
    }}
  ],
  "inline_comments": [
    {{
      "file_path": "path/to/file.py",
      "line_number": 42,
      "suggestion": "Specific feedback on this line",
      "severity": "<critical|high|medium|low|info>"
    }}
  ],
  "metrics": {{
    "files_changed": 3,
    "lines_added": 150,
    "lines_deleted": 50,
    "complexity_increase": "medium"
  }}
}}

Be thorough but concise. Focus on:
1. Security vulnerabilities
2. Code quality issues
3. Performance concerns
4. Best practices
5. Testing coverage

Return ONLY valid JSON, no markdown formatting."""
    
    return prompt


def format_static_analysis(results: Optional[Dict]) -> str:
    """Format static analysis results."""
    if not results:
        return "No static analysis performed."
    
    lines = []
    for tool, findings in results.items():
        lines.append(f"### {tool}")
        if findings:
            for finding in findings:
                lines.append(f"- {finding}")
        else:
            lines.append("- No issues found")
    
    return "\n".join(lines)


def format_risk_signals(signals: Optional[Dict]) -> str:
    """Format risk signals."""
    if not signals:
        return "No risk signals detected."
    
    lines = []
    for signal_type, details in signals.items():
        lines.append(f"- **{signal_type}**: {details}")
    
    return "\n".join(lines)


def build_refinement_prompt(
    pr_title: str,
    pr_description: str,
    diff_content: str,
    initial_review: str,
    uncertain_areas: List[str],
    static_analysis_results: Optional[Dict] = None,
) -> str:
    """
    Build a refinement prompt for re-analyzing uncertain areas.
    
    Used when confidence is low on certain aspects of the review.
    """
    
    uncertain_areas_str = "\n".join([f"- {area}" for area in uncertain_areas])
    
    prompt = f"""You are an expert code reviewer performing a deeper analysis on uncertain areas.

## Original PR Information
**Title:** {pr_title}
**Description:** {pr_description if pr_description else "No description provided"}

## Changes
```diff
{diff_content}
```

## Initial Review Assessment
```
{initial_review}
```

## Areas Needing Deeper Analysis
{uncertain_areas_str}

## Your Task
Re-analyze the code changes, focusing specifically on the uncertain areas listed above.
Provide a refined review in JSON format:

{{
  "summary": "Refined assessment after deeper analysis",
  "risk_score": <number 0-10>,
  "recommendation": "<APPROVE|REQUEST_CHANGES|COMMENT>",
  "findings": [
    {{
      "category": "<Security|Code Quality|Performance|Best Practice|Testing|Documentation>",
      "severity": "<critical|high|medium|low|info>",
      "title": "Short title of the issue",
      "description": "Detailed explanation",
      "suggestion": "How to fix it",
      "file_path": "path/to/file.py",
      "line_number": 42
    }}
  ],
  "inline_comments": [
    {{
      "file_path": "path/to/file.py",
      "line_number": 42,
      "suggestion": "Specific feedback on this line",
      "severity": "<critical|high|medium|low|info>"
    }}
  ],
  "confidence_improvements": {{
    "areas_clarified": ["area1", "area2"],
    "remaining_concerns": ["concern1"],
    "overall_confidence": 0.9
  }}
}}

Focus on correctness and provide actionable feedback.
Return ONLY valid JSON, no markdown formatting."""
    
    return prompt