"""
Linting analyzer module.

Integrates with linting tools to detect style and correctness issues:
- flake8 for Python style checking
- pylint for Python code quality
- ESLint for JavaScript/TypeScript (optional)
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


class LintSeverity(Enum):
    """Lint issue severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    STYLE = "style"


@dataclass
class LintIssue:
    """Represents a single linting issue."""
    file: str
    line: int
    column: int
    severity: LintSeverity
    code: str
    message: str
    tool: str  # flake8, pylint, eslint, etc.


class LintingAnalyzer:
    """
    Runs linting tools on changed files.
    
    Focuses on files that were added or modified in the PR.
    """
    
    def __init__(self):
        """Initialize linting analyzer."""
        self.issues: List[LintIssue] = []
    
    async def analyze(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ) -> List[LintIssue]:
        """
        Run linting analysis on files.
        
        Args:
            files: List of file metadata (filename, language)
            file_contents: Mapping of filename -> content
        
        Returns:
            List[LintIssue]: Detected linting issues
        """
        if not settings.ENABLE_LINTING:
            logger.info("Linting is disabled")
            return []
        
        self.issues = []
        
        # Group files by language
        python_files = [
            f for f in files 
            if f.get('language') == 'python' and f['filename'] in file_contents
        ]
        
        js_files = [
            f for f in files 
            if f.get('language') in ['javascript', 'typescript'] 
            and f['filename'] in file_contents
        ]
        
        # Run Python linting
        if python_files:
            await self._run_python_linting(python_files, file_contents)
        
        # Run JavaScript linting (if configured)
        if js_files:
            await self._run_javascript_linting(js_files, file_contents)
        
        logger.info(
            "Linting analysis completed",
            extra={
                "total_issues": len(self.issues),
                "by_severity": self._count_by_severity(),
            }
        )
        
        return self.issues
    
    async def _run_python_linting(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ):
        """
        Run Python linting tools (flake8, pylint).
        
        Args:
            files: List of Python file metadata
            file_contents: File contents mapping
        """
        # Run flake8
        flake8_issues = await self._run_flake8(files, file_contents)
        self.issues.extend(flake8_issues)
        
        # Run pylint
        pylint_issues = await self._run_pylint(files, file_contents)
        self.issues.extend(pylint_issues)
    
    async def _run_flake8(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ) -> List[LintIssue]:
        """
        Run flake8 on Python files.
        
        Args:
            files: List of Python file metadata
            file_contents: File contents mapping
        
        Returns:
            List[LintIssue]: Flake8 issues
        """
        issues = []
        
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
                return issues
            
            # Run flake8
            try:
                cmd = [
                    'flake8',
                    '--format=json',
                    f'--max-line-length={settings.FLAKE8_MAX_LINE_LENGTH}',
                    '--extend-ignore=E203,W503',  # Common ignores
                ] + [path for path, _ in temp_files]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                # Parse flake8 output
                if result.stdout:
                    try:
                        flake8_data = json.loads(result.stdout)
                        
                        for temp_path, original_filename in temp_files:
                            if temp_path in flake8_data:
                                for issue_data in flake8_data[temp_path]:
                                    issues.append(LintIssue(
                                        file=original_filename,
                                        line=issue_data['line_number'],
                                        column=issue_data['column_number'],
                                        severity=self._map_flake8_severity(issue_data['code']),
                                        code=issue_data['code'],
                                        message=issue_data['text'],
                                        tool='flake8',
                                    ))
                    except json.JSONDecodeError:
                        # Fallback: parse text output
                        pass
                
            except subprocess.TimeoutExpired:
                logger.warning("Flake8 timed out")
            except FileNotFoundError:
                logger.warning("Flake8 not installed")
            except Exception as e:
                logger.error(f"Flake8 error: {e}")
        
        return issues
    
    async def _run_pylint(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ) -> List[LintIssue]:
        """
        Run pylint on Python files.
        
        Args:
            files: List of Python file metadata
            file_contents: File contents mapping
        
        Returns:
            List[LintIssue]: Pylint issues
        """
        issues = []
        
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
                return issues
            
            # Run pylint
            try:
                cmd = [
                    'pylint',
                    '--output-format=json',
                    '--disable=C0114,C0115,C0116',  # Disable docstring warnings
                ] + [path for path, _ in temp_files]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                
                # Parse pylint output
                if result.stdout:
                    try:
                        pylint_data = json.loads(result.stdout)
                        
                        # Map temp paths to original filenames
                        path_map = {path: orig for path, orig in temp_files}
                        
                        for issue_data in pylint_data:
                            temp_path = issue_data['path']
                            original_filename = path_map.get(temp_path, temp_path)
                            
                            issues.append(LintIssue(
                                file=original_filename,
                                line=issue_data['line'],
                                column=issue_data['column'],
                                severity=self._map_pylint_severity(issue_data['type']),
                                code=issue_data['message-id'],
                                message=issue_data['message'],
                                tool='pylint',
                            ))
                    except json.JSONDecodeError:
                        pass
                
            except subprocess.TimeoutExpired:
                logger.warning("Pylint timed out")
            except FileNotFoundError:
                logger.warning("Pylint not installed")
            except Exception as e:
                logger.error(f"Pylint error: {e}")
        
        return issues
    
    async def _run_javascript_linting(
        self,
        files: List[Dict[str, Any]],
        file_contents: Dict[str, str],
    ):
        """
        Run JavaScript/TypeScript linting (ESLint).
        
        Note: ESLint requires project configuration, so this is optional.
        
        Args:
            files: List of JS/TS file metadata
            file_contents: File contents mapping
        """
        # ESLint integration would go here
        # Requires eslint installed and configured
        logger.debug("JavaScript linting not implemented yet")
        pass
    
    def _map_flake8_severity(self, code: str) -> LintSeverity:
        """
        Map flake8 error code to severity.
        
        Args:
            code: Flake8 error code (e.g., E501, W503)
        
        Returns:
            LintSeverity: Mapped severity
        """
        if code.startswith('E'):
            return LintSeverity.ERROR
        elif code.startswith('W'):
            return LintSeverity.WARNING
        elif code.startswith('F'):
            return LintSeverity.ERROR
        else:
            return LintSeverity.INFO
    
    def _map_pylint_severity(self, pylint_type: str) -> LintSeverity:
        """
        Map pylint message type to severity.
        
        Args:
            pylint_type: Pylint message type
        
        Returns:
            LintSeverity: Mapped severity
        """
        severity_map = {
            'error': LintSeverity.ERROR,
            'warning': LintSeverity.WARNING,
            'refactor': LintSeverity.INFO,
            'convention': LintSeverity.STYLE,
            'info': LintSeverity.INFO,
        }
        
        return severity_map.get(pylint_type.lower(), LintSeverity.INFO)
    
    def _count_by_severity(self) -> Dict[str, int]:
        """
        Count issues by severity.
        
        Returns:
            Dict[str, int]: Severity -> count mapping
        """
        counts = {sev.value: 0 for sev in LintSeverity}
        
        for issue in self.issues:
            counts[issue.severity.value] += 1
        
        return counts
    
    def get_critical_issues(self) -> List[LintIssue]:
        """
        Get only critical (error-level) issues.
        
        Returns:
            List[LintIssue]: Error-level issues
        """
        return [
            issue for issue in self.issues 
            if issue.severity == LintSeverity.ERROR
        ]
    
    def get_issues_by_file(self) -> Dict[str, List[LintIssue]]:
        """
        Group issues by file.
        
        Returns:
            Dict[str, List[LintIssue]]: File -> issues mapping
        """
        by_file = {}
        
        for issue in self.issues:
            if issue.file not in by_file:
                by_file[issue.file] = []
            by_file[issue.file].append(issue)
        
        return by_file
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of linting results.
        
        Returns:
            Dict: Linting summary
        """
        return {
            "total_issues": len(self.issues),
            "by_severity": self._count_by_severity(),
            "critical_issues": len(self.get_critical_issues()),
            "files_with_issues": len(self.get_issues_by_file()),
        }