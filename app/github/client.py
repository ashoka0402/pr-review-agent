"""
GitHub API client wrapper.

Provides a clean interface for interacting with GitHub API,
with automatic authentication and error handling.
"""

import logging
from typing import Dict, List, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.github.auth import GitHubAppAuth

logger = logging.getLogger(__name__)


class GitHubClient:
    """
    GitHub API client with automatic authentication.
    
    Handles:
    - Installation token authentication
    - API requests with retry logic
    - Error handling and logging
    """
    
    def __init__(
        self,
        auth: GitHubAppAuth,
        api_url: str = "https://api.github.com",
        timeout: int = 30,
    ):
        """
        Initialize GitHub API client.
        
        Args:
            auth: GitHub App authentication instance
            api_url: GitHub API base URL
            timeout: Request timeout in seconds
        """
        self.auth = auth
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        
        # Configure session with retry logic
        self.session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH", "PUT"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _get_headers(self, installation_id: int) -> Dict[str, str]:
        """
        Get request headers with installation token.
        
        Args:
            installation_id: GitHub App installation ID
        
        Returns:
            Dict[str, str]: Request headers
        """
        token = self.auth.get_installation_token(
            installation_id=installation_id,
            api_url=self.api_url,
        )
        
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int,
    ) -> Dict[str, Any]:
        """
        Get pull request details.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            installation_id: GitHub App installation ID
        
        Returns:
            Dict: Pull request data
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = self._get_headers(installation_id)
        
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        
        return response.json()
    
    def get_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Get list of files changed in a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            installation_id: GitHub App installation ID
        
        Returns:
            List[Dict]: List of changed files
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        headers = self._get_headers(installation_id)
        
        # Handle pagination
        all_files = []
        page = 1
        per_page = 100
        
        while True:
            params = {"page": page, "per_page": per_page}
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            
            files = response.json()
            if not files:
                break
            
            all_files.extend(files)
            page += 1
            
            # Safety limit
            if page > 10:  # Max 1000 files
                logger.warning(
                    "PR has too many files, stopping pagination",
                    extra={"owner": owner, "repo": repo, "pr_number": pr_number}
                )
                break
        
        return all_files
    
    def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
        installation_id: int,
    ) -> Optional[str]:
        """
        Get file content from repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            path: File path
            ref: Git reference (branch, tag, or commit SHA)
            installation_id: GitHub App installation ID
        
        Returns:
            Optional[str]: File content (decoded), or None if not found
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/contents/{path}"
        headers = self._get_headers(installation_id)
        params = {"ref": ref}
        
        try:
            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Decode base64 content
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            
            return content
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.debug(
                    "File not found",
                    extra={"path": path, "ref": ref}
                )
                return None
            raise
    
    def create_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        body: str,
        path: str,
        line: int,
        installation_id: int,
    ) -> Dict[str, Any]:
        """
        Create an inline review comment on a PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_id: Commit SHA
            body: Comment body
            path: File path
            line: Line number
            installation_id: GitHub App installation ID
        
        Returns:
            Dict: Created comment data
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        headers = self._get_headers(installation_id)
        
        payload = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
        }
        
        response = self.session.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        
        return response.json()
    
    def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        body: str,
        event: str,
        comments: Optional[List[Dict[str, Any]]] = None,
        installation_id: int = None,
    ) -> Dict[str, Any]:
        """
        Create a PR review.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: Pull request number
            commit_id: Commit SHA
            body: Review summary body
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            comments: Optional list of inline comments
            installation_id: GitHub App installation ID
        
        Returns:
            Dict: Created review data
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        headers = self._get_headers(installation_id)
        
        payload = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
        }
        
        if comments:
            payload["comments"] = comments
        
        response = self.session.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        
        return response.json()
    
    def post_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
        installation_id: int,
    ) -> Dict[str, Any]:
        """
        Post a comment on an issue or PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            issue_number: Issue or PR number
            body: Comment body
            installation_id: GitHub App installation ID
        
        Returns:
            Dict: Created comment data
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        headers = self._get_headers(installation_id)
        
        payload = {"body": body}
        
        response = self.session.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        
        return response.json()
    
    def get_compare(
        self,
        owner: str,
        repo: str,
        base: str,
        head: str,
        installation_id: int,
    ) -> Dict[str, Any]:
        """
        Compare two commits.
        
        Args:
            owner: Repository owner
            repo: Repository name
            base: Base commit SHA or ref
            head: Head commit SHA or ref
            installation_id: GitHub App installation ID
        
        Returns:
            Dict: Comparison data including diff
        """
        url = f"{self.api_url}/repos/{owner}/{repo}/compare/{base}...{head}"
        headers = self._get_headers(installation_id)
        headers["Accept"] = "application/vnd.github.v3.diff"
        
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        
        return {
            "diff": response.text,
            "base": base,
            "head": head,
        }