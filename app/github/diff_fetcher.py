"""
PR diff fetcher module.

Handles fetching and organizing PR diff data including:
- Unified diff retrieval
- Changed files metadata
- Additional file context when needed
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from app.github.client import GitHubClient
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a single file change in a PR."""
    filename: str
    status: str  # added, removed, modified, renamed
    additions: int
    deletions: int
    changes: int
    patch: Optional[str] = None
    previous_filename: Optional[str] = None
    blob_url: Optional[str] = None
    raw_url: Optional[str] = None


@dataclass
class PRDiff:
    """Represents complete PR diff data."""
    pr_number: int
    base_sha: str
    head_sha: str
    total_additions: int
    total_deletions: int
    total_changes: int
    files_changed: int
    file_changes: List[FileChange]
    unified_diff: str
    size_category: str  # small, medium, large, very_large


class DiffFetcher:
    """
    Fetches and organizes PR diff data.
    
    Responsibilities:
    - Retrieve unified diff
    - Parse file changes
    - Categorize diff size
    - Fetch additional file context when needed
    """
    
    def __init__(self, github_client: GitHubClient):
        """
        Initialize diff fetcher.
        
        Args:
            github_client: GitHub API client instance
        """
        self.github_client = github_client
    
    async def fetch_pr_diff(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int,
    ) -> PRDiff:
        """
        Fetch complete PR diff data.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            installation_id: GitHub App installation ID
        
        Returns:
            PRDiff: Complete PR diff data
        """
        logger.info(
            "Fetching PR diff",
            extra={
                "owner": owner,
                "repo": repo,
                "pr_number": pr_number,
            }
        )
        
        # Get PR metadata
        pr_data = self.github_client.get_pull_request(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            installation_id=installation_id,
        )
        
        base_sha = pr_data["base"]["sha"]
        head_sha = pr_data["head"]["sha"]
        
        # Get list of changed files
        files_data = self.github_client.get_pull_request_files(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            installation_id=installation_id,
        )
        
        # Check if diff is too large
        files_changed = len(files_data)
        if files_changed > settings.MAX_FILES_PER_PR:
            logger.warning(
                "PR has too many files",
                extra={
                    "files_changed": files_changed,
                    "max_files": settings.MAX_FILES_PER_PR,
                }
            )
            raise ValueError(
                f"PR has {files_changed} files, exceeds limit of {settings.MAX_FILES_PER_PR}"
            )
        
        # Parse file changes
        file_changes = []
        total_additions = 0
        total_deletions = 0
        
        for file_data in files_data:
            file_change = FileChange(
                filename=file_data["filename"],
                status=file_data["status"],
                additions=file_data["additions"],
                deletions=file_data["deletions"],
                changes=file_data["changes"],
                patch=file_data.get("patch"),
                previous_filename=file_data.get("previous_filename"),
                blob_url=file_data.get("blob_url"),
                raw_url=file_data.get("raw_url"),
            )
            file_changes.append(file_change)
            
            total_additions += file_data["additions"]
            total_deletions += file_data["deletions"]
        
        total_changes = total_additions + total_deletions
        
        # Get unified diff
        compare_data = self.github_client.get_compare(
            owner=owner,
            repo=repo,
            base=base_sha,
            head=head_sha,
            installation_id=installation_id,
        )
        
        unified_diff = compare_data["diff"]
        
        # Check if diff is too large
        diff_size_bytes = len(unified_diff.encode('utf-8'))
        if diff_size_bytes > settings.MAX_DIFF_SIZE_BYTES:
            logger.warning(
                "Diff is too large",
                extra={
                    "diff_size_bytes": diff_size_bytes,
                    "max_size_bytes": settings.MAX_DIFF_SIZE_BYTES,
                }
            )
            # Truncate diff with warning
            unified_diff = unified_diff[:settings.MAX_DIFF_SIZE_BYTES] + "\n\n[DIFF TRUNCATED - TOO LARGE]"
        
        # Categorize diff size
        size_category = self._categorize_diff_size(total_changes)
        
        pr_diff = PRDiff(
            pr_number=pr_number,
            base_sha=base_sha,
            head_sha=head_sha,
            total_additions=total_additions,
            total_deletions=total_deletions,
            total_changes=total_changes,
            files_changed=files_changed,
            file_changes=file_changes,
            unified_diff=unified_diff,
            size_category=size_category,
        )
        
        logger.info(
            "PR diff fetched",
            extra={
                "pr_number": pr_number,
                "files_changed": files_changed,
                "total_changes": total_changes,
                "size_category": size_category,
            }
        )
        
        return pr_diff
    
    def _categorize_diff_size(self, total_changes: int) -> str:
        """
        Categorize diff size based on total line changes.
        
        Args:
            total_changes: Total lines added + deleted
        
        Returns:
            str: Size category (small, medium, large, very_large)
        """
        if total_changes < 50:
            return "small"
        elif total_changes < 200:
            return "medium"
        elif total_changes < settings.LARGE_DIFF_THRESHOLD_LINES:
            return "large"
        else:
            return "very_large"
    
    async def fetch_file_context(
        self,
        owner: str,
        repo: str,
        filepath: str,
        ref: str,
        installation_id: int,
    ) -> Optional[str]:
        """
        Fetch full file content for additional context.
        
        Used when the agent needs to see more context beyond the diff.
        
        Args:
            owner: Repository owner
            repo: Repository name
            filepath: Path to file
            ref: Git reference (commit SHA, branch)
            installation_id: GitHub App installation ID
        
        Returns:
            Optional[str]: File content, or None if not found
        """
        logger.debug(
            "Fetching file context",
            extra={
                "filepath": filepath,
                "ref": ref,
            }
        )
        
        try:
            content = self.github_client.get_file_content(
                owner=owner,
                repo=repo,
                path=filepath,
                ref=ref,
                installation_id=installation_id,
            )
            return content
        except Exception as e:
            logger.warning(
                "Failed to fetch file context",
                extra={
                    "filepath": filepath,
                    "error": str(e),
                }
            )
            return None
    
    def get_changed_file_types(self, pr_diff: PRDiff) -> Dict[str, int]:
        """
        Get distribution of changed file types.
        
        Args:
            pr_diff: PR diff data
        
        Returns:
            Dict[str, int]: File extension -> count mapping
        """
        file_types = {}
        
        for file_change in pr_diff.file_changes:
            # Extract file extension
            if "." in file_change.filename:
                ext = file_change.filename.split(".")[-1].lower()
            else:
                ext = "no_extension"
            
            file_types[ext] = file_types.get(ext, 0) + 1
        
        return file_types
    
    def get_changed_directories(self, pr_diff: PRDiff) -> List[str]:
        """
        Get list of directories affected by the PR.
        
        Args:
            pr_diff: PR diff data
        
        Returns:
            List[str]: List of unique directory paths
        """
        directories = set()
        
        for file_change in pr_diff.file_changes:
            # Extract directory path
            if "/" in file_change.filename:
                directory = "/".join(file_change.filename.split("/")[:-1])
                directories.add(directory)
            else:
                directories.add(".")  # Root directory
        
        return sorted(list(directories))
    
    def filter_files_by_extension(
        self,
        pr_diff: PRDiff,
        extensions: List[str],
    ) -> List[FileChange]:
        """
        Filter file changes by extension.
        
        Args:
            pr_diff: PR diff data
            extensions: List of file extensions to include (without dot)
        
        Returns:
            List[FileChange]: Filtered file changes
        """
        filtered = []
        extensions_lower = [ext.lower() for ext in extensions]
        
        for file_change in pr_diff.file_changes:
            if "." in file_change.filename:
                ext = file_change.filename.split(".")[-1].lower()
                if ext in extensions_lower:
                    filtered.append(file_change)
        
        return filtered