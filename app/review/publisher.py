"""
Publisher for posting reviews back to GitHub.

Handles the final step of submitting formatted reviews to GitHub PRs,
including error handling and retry logic.
"""

import logging
from typing import Dict, List, Optional, Any

from app.github.client import GitHubClient
from app.review.formatter import ReviewFormatter
from app.review.scorer import RiskScorer

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """Exception raised when publishing fails."""
    pass


class ReviewPublisher:
    """
    Publisher for GitHub PR reviews.
    
    Formats and submits review comments and summary to GitHub.
    """
    
    def __init__(
        self,
        github_client: GitHubClient,
        formatter: Optional[ReviewFormatter] = None,
        scorer: Optional[RiskScorer] = None,
    ):
        """
        Initialize review publisher.
        
        Args:
            github_client: GitHub API client
            formatter: Review formatter (creates one if not provided)
            scorer: Risk scorer (creates one if not provided)
        """
        self.github_client = github_client
        self.formatter = formatter or ReviewFormatter()
        self.scorer = scorer or RiskScorer()
    
    async def publish_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_result: Dict[str, Any],
        commit_sha: str,
    ) -> Dict[str, Any]:
        """
        Publish complete review to GitHub PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            review_result: Complete review result from PRReviewer
            commit_sha: Commit SHA to review
        
        Returns:
            Publication result with GitHub review ID and metadata
        
        Raises:
            PublishError: If publishing fails
        """
        logger.info(f"Publishing review for {owner}/{repo}#{pr_number}")
        
        try:
            # Format for GitHub
            formatted = self.formatter.format_for_github(review_result)
            
            # Calculate risk score
            risk_score = self.scorer.calculate(review_result)
            logger.info(f"Risk score: {risk_score}")
            
            # Post review to GitHub
            review_id = await self._post_review_to_github(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                commit_sha=commit_sha,
                body=formatted["body"],
                event=formatted["event"],
                comments=formatted["comments"],
            )
            
            logger.info(f"Review published successfully (ID: {review_id})")
            
            return {
                "success": True,
                "review_id": review_id,
                "event": formatted["event"],
                "comment_count": len(formatted["comments"]),
                "risk_score": risk_score.total,
                "risk_level": risk_score.level,
            }
            
        except Exception as e:
            logger.error(f"Failed to publish review: {e}", exc_info=True)
            raise PublishError(f"Review publication failed: {e}")
    
    async def publish_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comment: str,
    ) -> int:
        """
        Publish a standalone comment (not a review) to a PR.
        
        Useful for status updates or non-review messages.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            comment: Comment text
        
        Returns:
            Comment ID
        
        Raises:
            PublishError: If publishing fails
        """
        try:
            comment_id = await self.github_client.post_pr_comment(
                owner, repo, pr_number, comment
            )
            logger.info(f"Comment posted (ID: {comment_id})")
            return comment_id
            
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")
            raise PublishError(f"Comment publication failed: {e}")
    
    async def publish_status_check(
        self,
        owner: str,
        repo: str,
        commit_sha: str,
        review_result: Dict[str, Any],
    ) -> None:
        """
        Publish a GitHub status check for the review.
        
        Args:
            owner: Repository owner
            repo: Repository name
            commit_sha: Commit SHA
            review_result: Review result
        
        Raises:
            PublishError: If publishing fails
        """
        try:
            risk_score = self.scorer.calculate(review_result)
            review = review_result["review"]
            
            # Determine state
            if review.recommendation.value == "APPROVE":
                state = "success"
            elif review.recommendation.value == "REQUEST_CHANGES":
                state = "failure"
            else:
                state = "success"  # COMMENT doesn't block
            
            # Create description
            description = (
                f"{risk_score.level.upper()} risk | "
                f"{len(review.comments)} issues | "
                f"{review_result['confidence']:.0%} confidence"
            )
            
            await self.github_client.create_commit_status(
                owner=owner,
                repo=repo,
                sha=commit_sha,
                state=state,
                context="AI Code Review",
                description=description,
                target_url=None,
            )
            
            logger.info(f"Status check published: {state}")
            
        except Exception as e:
            logger.error(f"Failed to publish status check: {e}")
            # Don't raise - status checks are optional
    
    async def _post_review_to_github(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        body: str,
        event: str,
        comments: List[Dict[str, Any]],
    ) -> int:
        """
        Post review to GitHub using the Reviews API.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            commit_sha: Commit SHA to review
            body: Review body (summary)
            event: Review event (APPROVE, COMMENT, REQUEST_CHANGES)
            comments: List of inline comments
        
        Returns:
            GitHub review ID
        """
        # Build review payload
        review_payload = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }
        
        # Add comments if present
        if comments:
            # GitHub requires "comments" field with specific format
            formatted_comments = []
            for comment in comments:
                formatted_comments.append({
                    "path": comment["path"],
                    "position": comment.get("line", 1),  # Position in diff
                    "body": comment["body"],
                })
            review_payload["comments"] = formatted_comments
        
        # Post review
        try:
            review_id = await self.github_client.post_review(
                owner, repo, pr_number, review_payload
            )
            return review_id
            
        except Exception as e:
            # If review with comments fails, try posting just the summary
            logger.warning(f"Failed to post review with comments: {e}")
            logger.info("Attempting to post summary only...")
            
            summary_payload = {
                "commit_id": commit_sha,
                "body": body + "\n\n⚠️ *Inline comments could not be posted. Please check the summary above.*",
                "event": event,
            }
            
            review_id = await self.github_client.post_review(
                owner, repo, pr_number, summary_payload
            )
            
            # Post inline comments as regular PR comments
            if comments:
                await self._post_comments_as_fallback(
                    owner, repo, pr_number, comments
                )
            
            return review_id
    
    async def _post_comments_as_fallback(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comments: List[Dict[str, Any]],
    ) -> None:
        """
        Post inline comments as regular PR comments (fallback).
        
        Used when posting review with inline comments fails.
        """
        logger.info("Posting inline comments as regular comments (fallback)")
        
        # Group comments by file
        comments_by_file: Dict[str, List[Dict[str, Any]]] = {}
        for comment in comments:
            file_path = comment["path"]
            if file_path not in comments_by_file:
                comments_by_file[file_path] = []
            comments_by_file[file_path].append(comment)
        
        # Post one comment per file with all issues
        for file_path, file_comments in comments_by_file.items():
            comment_text = f"**{file_path}**\n\n"
            for fc in file_comments:
                line = fc.get("line", "?")
                comment_text += f"**Line {line}:**\n{fc['body']}\n\n---\n\n"
            
            try:
                await self.github_client.post_pr_comment(
                    owner, repo, pr_number, comment_text
                )
            except Exception as e:
                logger.error(f"Failed to post fallback comment for {file_path}: {e}")
    
    async def publish_error_notice(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        error_message: str,
    ) -> None:
        """
        Publish an error notice when review fails.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            error_message: Error description
        """
        notice = (
            "## ⚠️ AI Code Review Failed\n\n"
            f"The automated code review encountered an error:\n\n"
            f"```\n{error_message}\n```\n\n"
            "A human reviewer should review this PR manually. "
            "You may want to check if:\n"
            "- The PR is too large (>1MB diff, >100 files)\n"
            "- Files contain unsupported formats\n"
            "- The repository configuration is correct\n\n"
            "*Please contact the maintainers if this issue persists.*"
        )
        
        try:
            await self.publish_review_comment(owner, repo, pr_number, notice)
            logger.info("Error notice posted to PR")
        except Exception as e:
            logger.error(f"Failed to post error notice: {e}")
    
    def format_review_summary_for_logs(
        self,
        review_result: Dict[str, Any],
    ) -> str:
        """
        Format brief review summary for logging.
        
        Args:
            review_result: Review result
        
        Returns:
            Brief summary text
        """
        return self.formatter.format_comment_summary(review_result["review"])