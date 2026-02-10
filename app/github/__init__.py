"""
GitHub integration package.

This package handles all GitHub API interactions including:
- GitHub App authentication
- API client wrapper
- PR diff and file fetching
"""

from app.github.auth import GitHubAppAuth
from app.github.client import GitHubClient
from app.github.diff_fetcher import DiffFetcher

__all__ = ["GitHubAppAuth", "GitHubClient", "DiffFetcher"]