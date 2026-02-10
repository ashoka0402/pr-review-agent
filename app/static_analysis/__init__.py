"""
Static analysis package for PR Review Agent.

This package contains modules for running static code analysis tools:
- Linting (flake8, pylint)
- Security scanning (bandit)
- Complexity analysis (cyclomatic complexity, maintainability)
- Test coverage ingestion
"""

from app.static_analysis.linting import LintingAnalyzer
from app.static_analysis.security import SecurityAnalyzer
from app.static_analysis.complexity import ComplexityAnalyzer
from app.static_analysis.coverage import CoverageAnalyzer

__all__ = [
    "LintingAnalyzer",
    "SecurityAnalyzer", 
    "ComplexityAnalyzer",
    "CoverageAnalyzer",
]