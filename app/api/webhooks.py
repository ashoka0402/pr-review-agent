"""
GitHub webhook handler.

Receives and processes GitHub webhook events for pull requests.
Phase 1: Focused on pull_request events (opened, synchronize, reopened).
"""

import logging
from fastapi import APIRouter, Request, BackgroundTasks, Depends, Header
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import json

from app.dependencies import (
    verify_github_signature,
    get_github_client,
    get_llm_client,
    get_s3_client,
)
from app.github.client import GitHubClient
from app.llm.model import LLMClient
from app.storage.s3 import S3Client
from app.agents.reviewer import PRReviewer
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/github",
    status_code=202,
    summary="GitHub webhook receiver",
    description="Receives GitHub webhook events and triggers PR review"
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
    signature_valid: bool = Depends(verify_github_signature),
    github_client: GitHubClient = Depends(get_github_client),
    llm_client: LLMClient = Depends(get_llm_client),
    s3_client: Optional[S3Client] = Depends(get_s3_client),
):
    """
    GitHub webhook endpoint.
    
    Handles incoming GitHub webhook events and triggers background processing.
    
    Phase 1 scope:
    - pull_request events (opened, synchronize, reopened)
    - Event-driven, single-PR analysis
    
    Args:
        request: FastAPI request object
        background_tasks: FastAPI background tasks
        x_github_event: GitHub event type header
        x_github_delivery: GitHub delivery ID header
        signature_valid: Webhook signature verification result
        github_client: GitHub API client
        llm_client: LLM client
        s3_client: Optional S3 storage client
    
    Returns:
        JSONResponse: Acknowledgment response
    """
    # Parse webhook payload
    payload = json.loads(request.state.body)
    
    logger.info(
        "Received GitHub webhook",
        extra={
            "event": x_github_event,
            "delivery_id": x_github_delivery,
            "action": payload.get("action"),
        }
    )
    
    # Handle pull_request events
    if x_github_event == "pull_request":
        await handle_pull_request_event(
            payload=payload,
            delivery_id=x_github_delivery,
            background_tasks=background_tasks,
            github_client=github_client,
            llm_client=llm_client,
            s3_client=s3_client,
        )
        return JSONResponse(
            status_code=202,
            content={
                "message": "Pull request event received",
                "delivery_id": x_github_delivery,
            }
        )
    
    # Handle ping events (GitHub App setup verification)
    elif x_github_event == "ping":
        logger.info("Received ping event", extra={"zen": payload.get("zen")})
        return JSONResponse(
            status_code=200,
            content={"message": "pong"}
        )
    
    # Ignore other events
    else:
        logger.info(
            "Ignoring unsupported event",
            extra={"event": x_github_event}
        )
        return JSONResponse(
            status_code=200,
            content={"message": f"Event {x_github_event} not processed"}
        )


async def handle_pull_request_event(
    payload: Dict[str, Any],
    delivery_id: str,
    background_tasks: BackgroundTasks,
    github_client: GitHubClient,
    llm_client: LLMClient,
    s3_client: Optional[S3Client],
):
    """
    Handles pull_request webhook events.
    
    Phase 1 supported actions:
    - opened: New PR created
    - synchronize: PR updated with new commits
    - reopened: Closed PR reopened
    
    Args:
        payload: Webhook payload
        delivery_id: GitHub delivery ID
        background_tasks: FastAPI background tasks
        github_client: GitHub API client
        llm_client: LLM client
        s3_client: Optional S3 storage client
    """
    action = payload.get("action")
    
    # Phase 1: Only process opened, synchronize, reopened
    if action not in ["opened", "synchronize", "reopened"]:
        logger.info(
            "Ignoring pull_request action",
            extra={"action": action, "delivery_id": delivery_id}
        )
        return
    
    # Extract PR context
    pr_data = payload.get("pull_request", {})
    repository = payload.get("repository", {})
    installation = payload.get("installation", {})
    
    pr_context = {
        "delivery_id": delivery_id,
        "action": action,
        "repository_full_name": repository.get("full_name"),
        "repository_owner": repository.get("owner", {}).get("login"),
        "repository_name": repository.get("name"),
        "pr_number": pr_data.get("number"),
        "pr_title": pr_data.get("title"),
        "pr_author": pr_data.get("user", {}).get("login"),
        "pr_url": pr_data.get("html_url"),
        "base_branch": pr_data.get("base", {}).get("ref"),
        "head_branch": pr_data.get("head", {}).get("ref"),
        "head_sha": pr_data.get("head", {}).get("sha"),
        "installation_id": installation.get("id"),
    }
    
    logger.info(
        "Processing pull request event",
        extra={
            "pr_context": pr_context,
            "delivery_id": delivery_id,
        }
    )
    
    # Schedule background review task
    background_tasks.add_task(
        execute_pr_review,
        pr_context=pr_context,
        github_client=github_client,
        llm_client=llm_client,
        s3_client=s3_client,
    )


async def execute_pr_review(
    pr_context: Dict[str, Any],
    github_client: GitHubClient,
    llm_client: LLMClient,
    s3_client: Optional[S3Client],
):
    """
    Executes the PR review process.
    
    This is run as a background task after webhook acknowledgment.
    
    Workflow:
    1. Authenticate with GitHub installation
    2. Fetch PR diff and metadata
    3. Run static analysis
    4. Execute LLM-based review
    5. Post review back to GitHub
    6. Store review artifacts
    
    Args:
        pr_context: PR context extracted from webhook
        github_client: GitHub API client
        llm_client: LLM client
        s3_client: Optional S3 storage client
    """
    try:
        logger.info(
            "Starting PR review",
            extra={
                "pr_number": pr_context["pr_number"],
                "repository": pr_context["repository_full_name"],
            }
        )
        
        # Initialize PR reviewer agent
        

        reviewer = PRReviewer(
            settings=settings,
            github_client=github_client,
            llm_client=llm_client,
        )

        
        # Execute review
        # Execute review
        review_result = await reviewer.review_pr(
            owner=pr_context["repository_owner"],
            repo=pr_context["repository_name"],
            pr_number=pr_context["pr_number"],
            pr_info={
                "title": pr_context["pr_title"],
                "description": "",
                "author": pr_context["pr_author"],
                "url": pr_context["pr_url"],
                
            },
            installation_id=pr_context["installation_id"],
            
        )

        
        logger.info(
            "PR review completed",
            extra={
                "pr_number": pr_context["pr_number"],
                "repository": pr_context["repository_full_name"],
                "risk_score": review_result.get("risk_score"),
                "recommendation": review_result.get("recommendation"),
            }
        )
        
    except Exception as e:
        logger.error(
            "PR review failed",
            extra={
                "pr_number": pr_context["pr_number"],
                "repository": pr_context["repository_full_name"],
                "error": str(e),
            },
            exc_info=True,
        )
        
        # Optionally post error comment to PR
        try:
            await post_error_comment(
                pr_context=pr_context,
                github_client=github_client,
                error=e,
            )
        except Exception as comment_error:
            logger.error(
                "Failed to post error comment",
                extra={"error": str(comment_error)},
                exc_info=True,
            )


async def post_error_comment(
    pr_context: Dict[str, Any],
    github_client: GitHubClient,
    error: Exception,
):
    """
    Posts an error comment to the PR when review fails.
    
    Args:
        pr_context: PR context
        github_client: GitHub API client
        error: Exception that occurred
    """
    comment_body = f"""## ⚠️ PR Review Failed

The automated PR review encountered an error and could not complete.

**Error**: {str(error)}

Please check the logs or contact the maintainers for assistance.
"""
    
    github_client.post_issue_comment(
        owner=pr_context["repository_owner"],
        repo=pr_context["repository_name"],
        issue_number=pr_context["pr_number"],
        body=comment_body,
        installation_id=pr_context["installation_id"],
    )