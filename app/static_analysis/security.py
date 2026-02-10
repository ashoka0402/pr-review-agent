"""
Security analyzer module.

Integrates with security scanning tools:
- Bandit for Python security issues
- npm audit for JavaScript dependencies (optional)
"""

import subprocess
import json
import logging
import tempfile
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from app.config import settings

logger = logging.getLogger(__name__)


class SecuritySeverity(Enum):
    """Security issue severity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SecurityIssue:
    """Represents a security finding."""
    file: str
    line: int
    severity: SecuritySeverity
    confidence: str  # HIGH, MEDIUM, LOW
    issue_type: str
    issue_text: str
    test_id: str
    tool: str  # bandit, npm-audit, etc.
    more_info: Optional[str] = None


class SecurityAnalyzer:
    """
    Runs security scanning tools on changed files.
    
    Focuses on detecting common security vulnerabilities
    in application code and dependencies.
    """
    
    def __init__(self):
        """Initialize security analyzer."""
        self.issues: List[SecurityIssue] = []
    
    async def analyze(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ) -> List[SecurityIssue]:
        """
        Run security analysis on files.
        
        Args:
            files: List of file metadata
            file_contents: Mapping of filename -> content
        
        Returns:
            List[SecurityIssue]: Detected security issues
        """
        if not settings.ENABLE_SECURITY_SCAN:
            logger.info("Security scanning is disabled")
            return []
        
        self.issues = []
        
        # Group files by language
        python_files = [
            f for f in files 
            if f.get('language') == 'python' and f['filename'] in file_contents
        ]
        
        # Run Python security scanning
        if python_files:
            await self._run_bandit(python_files, file_contents)
        
        logger.info(
            "Security analysis completed",
            extra={
                "total_issues": len(self.issues),
                "by_severity": self._count_by_severity(),
            }
        )
        
        return self.issues
    
    async def _run_bandit(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ):
        """
        Run Bandit security scanner on Python files.
        
        Args:
            files: List of Python file metadata
            file_contents: File contents mapping
        """
        # Create temporary directory for files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write files to temp directory
            temp_files = []
            for file_meta in files:
                filename = file_meta['filename']
                if filename not in file_contents:
                    continue
                
                # Create file path
                temp_path = os.path.join(tmpdir, os.path.basename(filename))
                
                with open(temp_path, 'w') as f:
                    f.write(file_contents[filename])
                
                temp_files.append((temp_path, filename))
            
            if not temp_files:
                return
            
            # Run bandit
            try:
                cmd = [
                    'bandit',
                    '-f', 'json',
                    '-r', tmpdir,
                    '-ll',  # Only low level and above
                ]
                
                # Set severity level from config
                severity_level = settings.BANDIT_SEVERITY_LEVEL.upper()
                if severity_level in ['LOW', 'MEDIUM', 'HIGH']:
                    cmd.extend(['-ll' if severity_level == 'LOW' else '-l'])
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                
                # Parse bandit output (it returns non-zero on findings)
                if result.stdout:
                    try:
                        bandit_data = json.loads(result.stdout)
                        
                        # Map temp paths to original filenames
                        path_map = {}
                        for temp_path, original in temp_files:
                            # Bandit uses absolute paths
                            abs_temp_path = os.path.abspath(temp_path)
                            path_map[abs_temp_path] = original
                        
                        # Parse results
                        for finding in bandit_data.get('results', []):
                            # Map to original filename
                            temp_file = finding['filename']
                            original_file = path_map.get(temp_file, temp_file)
                            
                            # Parse severity
                            severity_str = finding.get('issue_severity', 'MEDIUM').upper()
                            try:
                                severity = SecuritySeverity[severity_str]
                            except KeyError:
                                severity = SecuritySeverity.MEDIUM
                            
                            self.issues.append(SecurityIssue(
                                file=original_file,
                                line=finding['line_number'],
                                severity=severity,
                                confidence=finding.get('issue_confidence', 'MEDIUM'),
                                issue_type=finding.get('test_name', 'Unknown'),
                                issue_text=finding.get('issue_text', ''),
                                test_id=finding.get('test_id', ''),
                                tool='bandit',
                                more_info=finding.get('more_info'),
                            ))
                        
                        logger.info(
                            "Bandit scan completed",
                            extra={"findings": len(bandit_data.get('results', []))}
                        )
                        
                    except json.JSONDecodeError:
                        logger.error("Failed to parse Bandit JSON output")
                
            except subprocess.TimeoutExpired:
                logger.warning("Bandit scan timed out")
            except FileNotFoundError:
                logger.warning("Bandit not installed")
            except Exception as e:
                logger.error(f"Bandit error: {e}", exc_info=True)
    
    def _count_by_severity(self) -> Dict[str, int]:
        """
        Count issues by severity.
        
        Returns:
            Dict[str, int]: Severity -> count mapping
        """
        counts = {sev.value: 0 for sev in SecuritySeverity}
        
        for issue in self.issues:
            counts[issue.severity.value] += 1
        
        return counts
    
    def get_critical_issues(self) -> List[SecurityIssue]:
        """
        Get critical and high severity issues.
        
        Returns:
            List[SecurityIssue]: Critical/high issues
        """
        return [
            issue for issue in self.issues 
            if issue.severity in [SecuritySeverity.CRITICAL, SecuritySeverity.HIGH]
        ]
    
    def get_issues_by_file(self) -> Dict[str, List[SecurityIssue]]:
        """
        Group issues by file.
        
        Returns:
            Dict[str, List[SecurityIssue]]: File -> issues mapping
        """
        by_file = {}
        
        for issue in self.issues:
            if issue.file not in by_file:
                by_file[issue.file] = []
            by_file[issue.file].append(issue)
        
        return by_file
    
    def get_issues_by_type(self) -> Dict[str, List[SecurityIssue]]:
        """
        Group issues by type.
        
        Returns:
            Dict[str, List[SecurityIssue]]: Type -> issues mapping
        """
        by_type = {}
        
        for issue in self.issues:
            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = []
            by_type[issue.issue_type].append(issue)
        
        return by_type
    
    def has_critical_findings(self) -> bool:
        """
        Check if there are any critical findings.
        
        Returns:
            bool: True if critical findings exist
        """
        return len(self.get_critical_issues()) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of security findings.
        
        Returns:
            Dict: Security summary
        """
        critical_issues = self.get_critical_issues()
        
        return {
            "total_issues": len(self.issues),
            "by_severity": self._count_by_severity(),
            "critical_count": len(critical_issues),
            "files_with_issues": len(self.get_issues_by_file()),
            "issue_types": list(self.get_issues_by_type().keys()),
            "has_critical": self.has_critical_findings(),
        }
    
    def format_issue_for_review(self, issue: SecurityIssue) -> str:
        """
        Format a security issue for display in review.
        
        Args:
            issue: Security issue
        
        Returns:
            str: Formatted issue message
        """
        msg = f"**[{issue.severity.value}]** {issue.issue_type}\n\n"
        msg += f"{issue.issue_text}\n\n"
        msg += f"Confidence: {issue.confidence}\n"
        
        if issue.more_info:
            msg += f"\nMore info: {issue.more_info}"
        
        return msg