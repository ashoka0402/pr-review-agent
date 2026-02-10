"""
Diff parser module.

Parses unified diff format to extract:
- Added and removed lines
- Modified line ranges
- File categorization
- Line-level change details
"""

import re
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of change in a diff."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    CONTEXT = "context"


@dataclass
class LineChange:
    """Represents a single line change."""
    line_number: int
    change_type: ChangeType
    content: str
    old_line_number: Optional[int] = None
    new_line_number: Optional[int] = None


@dataclass
class HunkChange:
    """Represents a hunk (continuous block of changes) in a diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[LineChange]
    header: str


@dataclass
class FileDiff:
    """Represents all changes in a single file."""
    filename: str
    old_filename: Optional[str]
    is_new_file: bool
    is_deleted_file: bool
    is_renamed: bool
    hunks: List[HunkChange]
    additions: int
    deletions: int
    language: Optional[str] = None


class DiffParser:
    """
    Parses unified diff format.
    
    Extracts structured information from git unified diffs,
    including line-by-line changes and file metadata.
    """
    
    # Regex patterns for unified diff parsing
    FILE_HEADER_PATTERN = re.compile(r'^diff --git a/(.*?) b/(.*?)$')
    OLD_FILE_PATTERN = re.compile(r'^--- a/(.*)$')
    NEW_FILE_PATTERN = re.compile(r'^\+\+\+ b/(.*)$')
    HUNK_HEADER_PATTERN = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$')
    NEW_FILE_MODE_PATTERN = re.compile(r'^new file mode')
    DELETED_FILE_MODE_PATTERN = re.compile(r'^deleted file mode')
    RENAME_FROM_PATTERN = re.compile(r'^rename from (.*)$')
    RENAME_TO_PATTERN = re.compile(r'^rename to (.*)$')
    
    # Language detection by file extension
    LANGUAGE_MAP = {
        'py': 'python',
        'js': 'javascript',
        'ts': 'typescript',
        'jsx': 'javascript',
        'tsx': 'typescript',
        'java': 'java',
        'go': 'go',
        'rs': 'rust',
        'cpp': 'cpp',
        'c': 'c',
        'h': 'c',
        'hpp': 'cpp',
        'cs': 'csharp',
        'rb': 'ruby',
        'php': 'php',
        'swift': 'swift',
        'kt': 'kotlin',
        'scala': 'scala',
        'sql': 'sql',
        'sh': 'shell',
        'bash': 'shell',
        'yaml': 'yaml',
        'yml': 'yaml',
        'json': 'json',
        'xml': 'xml',
        'html': 'html',
        'css': 'css',
        'md': 'markdown',
        'txt': 'text',
    }
    
    def parse_diff(self, unified_diff: str) -> List[FileDiff]:
        """
        Parse unified diff into structured format.
        
        Args:
            unified_diff: Unified diff string
        
        Returns:
            List[FileDiff]: Parsed file diffs
        """
        if not unified_diff or not unified_diff.strip():
            logger.warning("Empty diff provided")
            return []
        
        lines = unified_diff.split('\n')
        file_diffs = []
        current_file = None
        current_hunk = None
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Start of a new file diff
            if line.startswith('diff --git'):
                if current_file:
                    if current_hunk:
                        current_file.hunks.append(current_hunk)
                    file_diffs.append(current_file)
                
                match = self.FILE_HEADER_PATTERN.match(line)
                if match:
                    current_file = FileDiff(
                        filename=match.group(2),
                        old_filename=match.group(1),
                        is_new_file=False,
                        is_deleted_file=False,
                        is_renamed=False,
                        hunks=[],
                        additions=0,
                        deletions=0,
                    )
                    current_hunk = None
            
            # File mode indicators
            elif current_file and self.NEW_FILE_MODE_PATTERN.match(line):
                current_file.is_new_file = True
            
            elif current_file and self.DELETED_FILE_MODE_PATTERN.match(line):
                current_file.is_deleted_file = True
            
            # Rename detection
            elif current_file and self.RENAME_FROM_PATTERN.match(line):
                current_file.is_renamed = True
                match = self.RENAME_FROM_PATTERN.match(line)
                if match:
                    current_file.old_filename = match.group(1)
            
            # Hunk header
            elif line.startswith('@@'):
                if current_hunk:
                    current_file.hunks.append(current_hunk)
                
                match = self.HUNK_HEADER_PATTERN.match(line)
                if match:
                    old_start = int(match.group(1))
                    old_count = int(match.group(2)) if match.group(2) else 1
                    new_start = int(match.group(3))
                    new_count = int(match.group(4)) if match.group(4) else 1
                    header = match.group(5).strip()
                    
                    current_hunk = HunkChange(
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=[],
                        header=header,
                    )
            
            # Line changes
            elif current_hunk is not None:
                if line.startswith('+') and not line.startswith('+++'):
                    # Added line
                    current_hunk.lines.append(LineChange(
                        line_number=len(current_hunk.lines),
                        change_type=ChangeType.ADDED,
                        content=line[1:],
                        new_line_number=current_hunk.new_start + sum(
                            1 for l in current_hunk.lines 
                            if l.change_type in [ChangeType.ADDED, ChangeType.CONTEXT]
                        ),
                    ))
                    current_file.additions += 1
                
                elif line.startswith('-') and not line.startswith('---'):
                    # Removed line
                    current_hunk.lines.append(LineChange(
                        line_number=len(current_hunk.lines),
                        change_type=ChangeType.REMOVED,
                        content=line[1:],
                        old_line_number=current_hunk.old_start + sum(
                            1 for l in current_hunk.lines 
                            if l.change_type in [ChangeType.REMOVED, ChangeType.CONTEXT]
                        ),
                    ))
                    current_file.deletions += 1
                
                elif line.startswith(' '):
                    # Context line
                    current_hunk.lines.append(LineChange(
                        line_number=len(current_hunk.lines),
                        change_type=ChangeType.CONTEXT,
                        content=line[1:],
                    ))
            
            i += 1
        
        # Add last file
        if current_file:
            if current_hunk:
                current_file.hunks.append(current_hunk)
            file_diffs.append(current_file)
        
        # Detect languages
        for file_diff in file_diffs:
            file_diff.language = self._detect_language(file_diff.filename)
        
        logger.info(
            "Parsed diff",
            extra={
                "files_changed": len(file_diffs),
                "total_additions": sum(f.additions for f in file_diffs),
                "total_deletions": sum(f.deletions for f in file_diffs),
            }
        )
        
        return file_diffs
    
    def _detect_language(self, filename: str) -> Optional[str]:
        """
        Detect programming language from filename.
        
        Args:
            filename: File name or path
        
        Returns:
            Optional[str]: Detected language, or None
        """
        if '.' not in filename:
            return None
        
        extension = filename.split('.')[-1].lower()
        return self.LANGUAGE_MAP.get(extension)
    
    def get_added_lines(self, file_diff: FileDiff) -> List[LineChange]:
        """
        Get all added lines from a file diff.
        
        Args:
            file_diff: Parsed file diff
        
        Returns:
            List[LineChange]: Added lines
        """
        added_lines = []
        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.change_type == ChangeType.ADDED:
                    added_lines.append(line)
        return added_lines
    
    def get_removed_lines(self, file_diff: FileDiff) -> List[LineChange]:
        """
        Get all removed lines from a file diff.
        
        Args:
            file_diff: Parsed file diff
        
        Returns:
            List[LineChange]: Removed lines
        """
        removed_lines = []
        for hunk in file_diff.hunks:
            for line in hunk.lines:
                if line.change_type == ChangeType.REMOVED:
                    removed_lines.append(line)
        return removed_lines
    
    def get_modified_line_ranges(self, file_diff: FileDiff) -> List[Tuple[int, int]]:
        """
        Get ranges of modified lines (new line numbers).
        
        Args:
            file_diff: Parsed file diff
        
        Returns:
            List[Tuple[int, int]]: List of (start, end) line ranges
        """
        ranges = []
        for hunk in file_diff.hunks:
            # Get first and last new line numbers in the hunk
            new_lines = [
                line.new_line_number 
                for line in hunk.lines 
                if line.new_line_number is not None
            ]
            if new_lines:
                ranges.append((min(new_lines), max(new_lines)))
        
        return ranges
    
    def categorize_files(self, file_diffs: List[FileDiff]) -> Dict[str, List[str]]:
        """
        Categorize files by type.
        
        Args:
            file_diffs: List of parsed file diffs
        
        Returns:
            Dict[str, List[str]]: Category -> filenames mapping
        """
        categories = {
            'source_code': [],
            'tests': [],
            'configuration': [],
            'documentation': [],
            'dependencies': [],
            'database': [],
            'other': [],
        }
        
        for file_diff in file_diffs:
            filename = file_diff.filename.lower()
            
            # Test files
            if any(x in filename for x in ['test_', '_test.', 'tests/', '/test/', 'spec/']):
                categories['tests'].append(file_diff.filename)
            
            # Configuration files
            elif any(filename.endswith(x) for x in [
                '.json', '.yaml', '.yml', '.toml', '.ini', '.conf', 
                '.env', 'dockerfile', 'docker-compose.yml'
            ]):
                categories['configuration'].append(file_diff.filename)
            
            # Documentation
            elif any(filename.endswith(x) for x in ['.md', '.txt', '.rst', 'readme']):
                categories['documentation'].append(file_diff.filename)
            
            # Dependencies
            elif any(x in filename for x in [
                'requirements.txt', 'package.json', 'poetry.lock',
                'pipfile', 'cargo.toml', 'go.mod', 'pom.xml'
            ]):
                categories['dependencies'].append(file_diff.filename)
            
            # Database migrations
            elif 'migration' in filename or 'migrate' in filename:
                categories['database'].append(file_diff.filename)
            
            # Source code (has recognized language)
            elif file_diff.language:
                categories['source_code'].append(file_diff.filename)
            
            else:
                categories['other'].append(file_diff.filename)
        
        return categories
    
    def extract_function_changes(self, file_diff: FileDiff) -> List[str]:
        """
        Extract function/method names from hunk headers.
        
        Many diffs include function context in hunk headers.
        
        Args:
            file_diff: Parsed file diff
        
        Returns:
            List[str]: Function names found in headers
        """
        functions = []
        for hunk in file_diff.hunks:
            if hunk.header:
                # Clean up header (remove common prefixes)
                header = hunk.header.strip()
                if header:
                    functions.append(header)
        
        return functions