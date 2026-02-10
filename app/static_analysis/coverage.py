"""
Coverage analyzer module.

Optional module for ingesting and analyzing test coverage data.
Can parse coverage reports from various formats:
- coverage.py (Python)
- Jest/Istanbul (JavaScript)
- JaCoCo (Java)
"""

import json
import xml.etree.ElementTree as ET
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FileCoverage:
    """Coverage data for a single file."""
    file: str
    line_coverage: float  # Percentage
    branch_coverage: Optional[float] = None
    lines_covered: int = 0
    lines_total: int = 0
    branches_covered: int = 0
    branches_total: int = 0
    uncovered_lines: List[int] = None


@dataclass
class CoverageSummary:
    """Overall coverage summary."""
    line_coverage: float
    branch_coverage: Optional[float]
    files_total: int
    files_covered: int
    lines_total: int
    lines_covered: int
    branches_total: int
    branches_covered: int


class CoverageAnalyzer:
    """
    Analyzes test coverage data.
    
    Note: This is an optional module. Coverage data must be
    provided externally (e.g., from CI pipeline).
    
    Phase 1: Basic coverage report parsing
    Future: Coverage diff analysis (only for changed lines)
    """
    
    def __init__(self):
        """Initialize coverage analyzer."""
        self.file_coverage: Dict[str, FileCoverage] = {}
        self.summary: Optional[CoverageSummary] = None
    
    def parse_coverage_report(
        self,
        report_data: str,
        format: str = 'json',
    ) -> CoverageSummary:
        """
        Parse coverage report from various formats.
        
        Args:
            report_data: Raw coverage report data
            format: Report format (json, xml, lcov)
        
        Returns:
            CoverageSummary: Parsed coverage summary
        """
        if format == 'json':
            return self._parse_json_coverage(report_data)
        elif format == 'xml':
            return self._parse_xml_coverage(report_data)
        else:
            logger.warning(f"Unsupported coverage format: {format}")
            return None
    
    def _parse_json_coverage(self, report_data: str) -> CoverageSummary:
        """
        Parse JSON coverage report (coverage.py format).
        
        Args:
            report_data: JSON coverage data
        
        Returns:
            CoverageSummary: Parsed summary
        """
        try:
            data = json.loads(report_data)
            
            files = data.get('files', {})
            totals = data.get('totals', {})
            
            # Parse file-level coverage
            for filepath, file_data in files.items():
                summary = file_data.get('summary', {})
                
                line_coverage = (
                    summary.get('percent_covered', 0.0)
                )
                
                missing_lines = file_data.get('missing_lines', [])
                
                self.file_coverage[filepath] = FileCoverage(
                    file=filepath,
                    line_coverage=line_coverage,
                    lines_covered=summary.get('covered_lines', 0),
                    lines_total=summary.get('num_statements', 0),
                    uncovered_lines=missing_lines,
                )
            
            # Parse overall summary
            self.summary = CoverageSummary(
                line_coverage=totals.get('percent_covered', 0.0),
                branch_coverage=totals.get('percent_covered_display', None),
                files_total=totals.get('num_files', 0),
                files_covered=len([
                    f for f in self.file_coverage.values() 
                    if f.line_coverage > 0
                ]),
                lines_total=totals.get('num_statements', 0),
                lines_covered=totals.get('covered_lines', 0),
                branches_total=0,
                branches_covered=0,
            )
            
            logger.info(
                "Parsed JSON coverage report",
                extra={
                    "files": len(self.file_coverage),
                    "line_coverage": self.summary.line_coverage,
                }
            )
            
            return self.summary
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON coverage: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing coverage: {e}")
            return None
    
    def _parse_xml_coverage(self, report_data: str) -> CoverageSummary:
        """
        Parse XML coverage report (Cobertura/JaCoCo format).
        
        Args:
            report_data: XML coverage data
        
        Returns:
            CoverageSummary: Parsed summary
        """
        try:
            root = ET.fromstring(report_data)
            
            # Parse packages/classes
            for package in root.findall('.//package'):
                for class_elem in package.findall('classes/class'):
                    filename = class_elem.get('filename')
                    
                    lines_elem = class_elem.find('lines')
                    if lines_elem is not None:
                        lines = lines_elem.findall('line')
                        
                        lines_total = len(lines)
                        lines_covered = sum(
                            1 for line in lines 
                            if int(line.get('hits', 0)) > 0
                        )
                        
                        line_coverage = (
                            (lines_covered / lines_total * 100) 
                            if lines_total > 0 else 0.0
                        )
                        
                        uncovered = [
                            int(line.get('number'))
                            for line in lines
                            if int(line.get('hits', 0)) == 0
                        ]
                        
                        self.file_coverage[filename] = FileCoverage(
                            file=filename,
                            line_coverage=line_coverage,
                            lines_covered=lines_covered,
                            lines_total=lines_total,
                            uncovered_lines=uncovered,
                        )
            
            # Calculate overall summary
            total_lines = sum(f.lines_total for f in self.file_coverage.values())
            covered_lines = sum(f.lines_covered for f in self.file_coverage.values())
            
            overall_coverage = (
                (covered_lines / total_lines * 100) if total_lines > 0 else 0.0
            )
            
            self.summary = CoverageSummary(
                line_coverage=overall_coverage,
                branch_coverage=None,
                files_total=len(self.file_coverage),
                files_covered=len([
                    f for f in self.file_coverage.values() 
                    if f.line_coverage > 0
                ]),
                lines_total=total_lines,
                lines_covered=covered_lines,
                branches_total=0,
                branches_covered=0,
            )
            
            logger.info(
                "Parsed XML coverage report",
                extra={
                    "files": len(self.file_coverage),
                    "line_coverage": self.summary.line_coverage,
                }
            )
            
            return self.summary
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse XML coverage: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing coverage: {e}")
            return None
    
    def get_coverage_for_files(
        self,
        filenames: List[str],
    ) -> Dict[str, FileCoverage]:
        """
        Get coverage data for specific files.
        
        Args:
            filenames: List of file paths
        
        Returns:
            Dict[str, FileCoverage]: Coverage by file
        """
        result = {}
        
        for filename in filenames:
            if filename in self.file_coverage:
                result[filename] = self.file_coverage[filename]
        
        return result
    
    def get_low_coverage_files(
        self,
        threshold: float = 80.0,
    ) -> List[FileCoverage]:
        """
        Get files with coverage below threshold.
        
        Args:
            threshold: Coverage percentage threshold
        
        Returns:
            List[FileCoverage]: Low coverage files
        """
        return [
            coverage for coverage in self.file_coverage.values()
            if coverage.line_coverage < threshold
        ]
    
    def get_uncovered_lines_in_diff(
        self,
        filename: str,
        changed_lines: List[int],
    ) -> List[int]:
        """
        Get uncovered lines that were changed in PR.
        
        This helps identify new code without test coverage.
        
        Args:
            filename: File path
            changed_lines: Line numbers changed in PR
        
        Returns:
            List[int]: Changed lines that are uncovered
        """
        if filename not in self.file_coverage:
            return []
        
        file_cov = self.file_coverage[filename]
        
        if not file_cov.uncovered_lines:
            return []
        
        # Intersection of changed lines and uncovered lines
        uncovered_in_diff = [
            line for line in changed_lines
            if line in file_cov.uncovered_lines
        ]
        
        return uncovered_in_diff
    
    def analyze_coverage_impact(
        self,
        changed_files: List[str],
    ) -> Dict[str, Any]:
        """
        Analyze coverage impact of PR changes.
        
        Args:
            changed_files: List of files changed in PR
        
        Returns:
            Dict: Coverage impact analysis
        """
        changed_coverage = self.get_coverage_for_files(changed_files)
        
        if not changed_coverage:
            return {
                "has_coverage_data": False,
                "message": "No coverage data available for changed files",
            }
        
        # Calculate average coverage of changed files
        avg_coverage = sum(
            f.line_coverage for f in changed_coverage.values()
        ) / len(changed_coverage)
        
        # Count low coverage files
        low_coverage = [
            f for f in changed_coverage.values()
            if f.line_coverage < 80.0
        ]
        
        return {
            "has_coverage_data": True,
            "files_with_coverage": len(changed_coverage),
            "average_coverage": round(avg_coverage, 2),
            "low_coverage_files": len(low_coverage),
            "low_coverage_details": [
                {
                    "file": f.file,
                    "coverage": f.line_coverage,
                }
                for f in low_coverage
            ],
        }
    
    def get_summary_dict(self) -> Optional[Dict[str, Any]]:
        """
        Get coverage summary as dictionary.
        
        Returns:
            Optional[Dict]: Summary data
        """
        if not self.summary:
            return None
        
        return {
            "line_coverage": round(self.summary.line_coverage, 2),
            "branch_coverage": (
                round(self.summary.branch_coverage, 2) 
                if self.summary.branch_coverage else None
            ),
            "files_total": self.summary.files_total,
            "files_covered": self.summary.files_covered,
            "lines_total": self.summary.lines_total,
            "lines_covered": self.summary.lines_covered,
        }