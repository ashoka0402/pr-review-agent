"""
Analysis package for PR Review Agent.

This package contains modules for analyzing PR diffs including:
- Diff parsing (added/removed lines, file categorization)
- Dependency graph analysis
- Risk detection (large diffs, critical files, heuristics)
"""

from app.analysis.diff_parser import DiffParser
from app.analysis.dependency_graph import DependencyGraph
from app.analysis.risk_detector import RiskDetector

__all__ = ["DiffParser", "DependencyGraph", "RiskDetector"]