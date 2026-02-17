"""
Tool registry for the PR review agent.

Provides a structured interface to access diff fetching, static analysis,
and other review utilities.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from app.github.client import GitHubClient
from app.github.diff_fetcher import DiffFetcher
from app.analysis.diff_parser import DiffParser
from app.analysis.dependency_graph import DependencyGraph
from app.analysis.risk_detector import RiskDetector
from app.static_analysis.linting import LintingAnalyzer
from app.static_analysis.security import SecurityAnalyzer
from app.static_analysis.complexity import ComplexityAnalyzer

logger = logging.getLogger(__name__)


class ToolType(str, Enum):
    """Available tool types."""
    DIFF_FETCH = "diff_fetch"
    FILE_FETCH = "file_fetch"
    DIFF_PARSE = "diff_parse"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    RISK_DETECTION = "risk_detection"
    LINTING = "linting"
    SECURITY_SCAN = "security_scan"
    COMPLEXITY_ANALYSIS = "complexity_analysis"


@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool_type: ToolType
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def __bool__(self) -> bool:
        """Allow truthiness checks."""
        return self.success


class ReviewTool(ABC):
    """Abstract base class for review tools."""
    
    @property
    @abstractmethod
    def tool_type(self) -> ToolType:
        """Return the tool type."""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass


class DiffFetchTool(ReviewTool):
    """Tool for fetching PR diffs."""

    def __init__(self, github_client: GitHubClient):
        self.diff_fetcher = DiffFetcher(github_client)

    @property
    def tool_type(self) -> ToolType:
        return ToolType.DIFF_FETCH

    async def execute(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int,
    ) -> ToolResult:
        """
        Fetch PR diff.
        """
        try:
            diff_data = await self.diff_fetcher.fetch_pr_diff(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                installation_id=installation_id,
            )

            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data=diff_data,
            )

        except Exception as e:
            logger.error(f"Diff fetch failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e),
            )



class FileFetchTool(ReviewTool):
    """Tool for fetching file contents from PR."""
    
    def __init__(self, github_client: GitHubClient):
        self.github_client = github_client
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.FILE_FETCH
    
    async def execute(
        self,
        owner: str,
        repo: str,
        ref: str,
        file_paths: List[str]
    ) -> ToolResult:
        """
        Fetch file contents.
        
        Args:
            owner: Repository owner
            repo: Repository name
            ref: Git ref (commit SHA, branch)
            file_paths: List of file paths to fetch
        
        Returns:
            ToolResult with file contents {path: content}
        """
        try:
            file_contents = {}
            for path in file_paths[:10]:  # Limit to 10 files
                try:
                    content = await self.github_client.get_file_content(
                        owner, repo, path, ref
                    )
                    file_contents[path] = content
                except Exception as e:
                    logger.warning(f"Failed to fetch {path}: {e}")
            
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data={"files": file_contents}
            )
        except Exception as e:
            logger.error(f"File fetch failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class DiffParseTool(ReviewTool):
    """Tool for parsing diffs."""
    
    def __init__(self):
        self.parser = DiffParser()
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.DIFF_PARSE
    
    async def execute(self, diff_content: str) -> ToolResult:
        """
        Parse diff content.
        
        Args:
            diff_content: Raw unified diff
        
        Returns:
            ToolResult with parsed changes
        """
        try:
            changes = self.parser.parse_diff(diff_content)
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data={"changes": changes}
            )
        except Exception as e:
            logger.error(f"Diff parsing failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class DependencyAnalysisTool(ReviewTool):
    """Tool for dependency analysis."""
    
    def __init__(self):
        self.analyzer = DependencyGraph()
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.DEPENDENCY_ANALYSIS
    
    async def execute(self, file_contents: Dict[str, str]) -> ToolResult:
        """
        Analyze dependencies.
        
        Args:
            file_contents: Dictionary of {file_path: content}
        
        Returns:
            ToolResult with dependency graph and impact analysis
        """
        try:
            graph = self.analyzer.build_dependency_graph(file_contents)
            impact_radius = self.analyzer.calculate_impact_radius(graph)
            circular_deps = self.analyzer.detect_circular_dependencies(graph)
            
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data={
                    "graph": graph,
                    "impact_radius": impact_radius,
                    "circular_dependencies": circular_deps
                }
            )
        except Exception as e:
            logger.error(f"Dependency analysis failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class RiskDetectionTool(ReviewTool):
    """Tool for heuristic risk detection."""
    
    def __init__(self):
        self.detector = RiskDetector()
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.RISK_DETECTION
    
    async def execute(
        self,
        diff_content: str,
        file_paths: List[str],
        lines_changed: int
    ) -> ToolResult:
        """
        Detect risk signals.
        
        Args:
            diff_content: Raw diff
            file_paths: List of changed files
            lines_changed: Total lines changed
        
        Returns:
            ToolResult with risk signals
        """
        try:
            signals = self.detector.detect_risk_signals(
                diff_content, file_paths, lines_changed
            )
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data=signals
            )
        except Exception as e:
            logger.error(f"Risk detection failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class LintingTool(ReviewTool):
    """Tool for linting."""
    
    def __init__(self):
        self.runner = LintingAnalyzer()
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.LINTING
    
    async def execute(self, file_contents: Dict[str, str]) -> ToolResult:
        """
        Run linting.
        
        Args:
            file_contents: Dictionary of {file_path: content}
        
        Returns:
            ToolResult with linting issues
        """
        try:
            results = await self.runner.run_linting(file_contents)
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data=results
            )
        except Exception as e:
            logger.error(f"Linting failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class SecurityScanTool(ReviewTool):
    """Tool for security scanning."""
    
    def __init__(self):
        self.scanner = SecurityAnalyzer()
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.SECURITY_SCAN
    
    async def execute(self, file_contents: Dict[str, str]) -> ToolResult:
        """
        Run security scanning.
        
        Args:
            file_contents: Dictionary of {file_path: content}
        
        Returns:
            ToolResult with security issues
        """
        try:
            results = await self.scanner.run_security_scan(file_contents)
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data=results
            )
        except Exception as e:
            logger.error(f"Security scan failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class ComplexityAnalysisTool(ReviewTool):
    """Tool for complexity analysis."""
    
    def __init__(self):
        self.analyzer = ComplexityAnalyzer()
    
    @property
    def tool_type(self) -> ToolType:
        return ToolType.COMPLEXITY_ANALYSIS
    
    async def execute(self, file_contents: Dict[str, str]) -> ToolResult:
        """
        Run complexity analysis.
        
        Args:
            file_contents: Dictionary of {file_path: content}
        
        Returns:
            ToolResult with complexity metrics
        """
        try:
            results = await self.analyzer.analyze_complexity(file_contents)
            return ToolResult(
                tool_type=self.tool_type,
                success=True,
                data=results
            )
        except Exception as e:
            logger.error(f"Complexity analysis failed: {e}")
            return ToolResult(
                tool_type=self.tool_type,
                success=False,
                error=str(e)
            )


class ToolRegistry:
    """Registry for managing and accessing review tools."""
    
    def __init__(self, github_client: GitHubClient):
        """
        Initialize tool registry.
        
        Args:
            github_client: GitHub API client
        """
        self.tools: Dict[ToolType, ReviewTool] = {
            ToolType.DIFF_FETCH: DiffFetchTool(github_client),
            ToolType.FILE_FETCH: FileFetchTool(github_client),
            ToolType.DIFF_PARSE: DiffParseTool(),
            ToolType.DEPENDENCY_ANALYSIS: DependencyAnalysisTool(),
            ToolType.RISK_DETECTION: RiskDetectionTool(),
            ToolType.LINTING: LintingTool(),
            ToolType.SECURITY_SCAN: SecurityScanTool(),
            ToolType.COMPLEXITY_ANALYSIS: ComplexityAnalysisTool(),
        }
    
    def get_tool(self, tool_type: ToolType) -> ReviewTool:
        """
        Get a tool by type.
        
        Args:
            tool_type: The tool type to retrieve
        
        Returns:
            The requested tool
        
        Raises:
            KeyError: If tool type is not registered
        """
        return self.tools[tool_type]
    
    async def execute_tool(self, tool_type: ToolType, **kwargs) -> ToolResult:
        """
        Execute a tool with given parameters.
        
        Args:
            tool_type: The tool to execute
            **kwargs: Tool-specific parameters
        
        Returns:
            Result of tool execution
        """
        tool = self.get_tool(tool_type)
        logger.info(f"Executing tool: {tool_type.value}")
        return await tool.execute(**kwargs)
    
    async def execute_static_analysis(
        self,
        file_contents: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Execute all static analysis tools.
        
        Args:
            file_contents: Dictionary of {file_path: content}
        
        Returns:
            Combined results from all static analysis tools
        """
        results = {}
        
        # Run linting
        lint_result = await self.execute_tool(
            ToolType.LINTING,
            file_contents=file_contents
        )
        if lint_result.success:
            results["linting"] = lint_result.data
        
        # Run security scan
        security_result = await self.execute_tool(
            ToolType.SECURITY_SCAN,
            file_contents=file_contents
        )
        if security_result.success:
            results["security"] = security_result.data
        
        # Run complexity analysis
        complexity_result = await self.execute_tool(
            ToolType.COMPLEXITY_ANALYSIS,
            file_contents=file_contents
        )
        if complexity_result.success:
            results["complexity"] = complexity_result.data
        
        return results