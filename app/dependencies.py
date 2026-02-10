"""
Shared dependencies for dependency injection.

This module provides reusable dependencies for FastAPI routes,
including GitHub clients, LLM clients, and storage clients.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Header
import hmac
import hashlib

from app.config import settings
from app.github.client import GitHubClient
from app.github.auth import GitHubAppAuth
from app.storage.s3 import S3Client
from app.llm.model import LLMClient


# ============================================================================
# GitHub Dependencies
# ============================================================================

def get_github_auth() -> GitHubAppAuth:
    """
    Provides GitHub App authentication.
    
    Returns:
        GitHubAppAuth: Configured GitHub App authentication instance.
    """
    return GitHubAppAuth(
        app_id=settings.GITHUB_APP_ID,
        private_key=settings.GITHUB_PRIVATE_KEY,
    )


def get_github_client(
    auth: GitHubAppAuth = Depends(get_github_auth)
) -> GitHubClient:
    """
    Provides GitHub API client.
    
    Args:
        auth: GitHub App authentication instance.
    
    Returns:
        GitHubClient: Configured GitHub API client.
    """
    return GitHubClient(
        auth=auth,
        api_url=settings.GITHUB_API_URL,
    )


# ============================================================================
# Webhook Signature Verification
# ============================================================================

async def verify_github_signature(
    x_hub_signature_256: Optional[str] = Header(None),
    body: bytes = None,
) -> bool:
    """
    Verifies GitHub webhook signature.
    
    Args:
        x_hub_signature_256: GitHub webhook signature header.
        body: Raw request body bytes.
    
    Returns:
        bool: True if signature is valid.
    
    Raises:
        HTTPException: If signature is invalid or missing.
    """
    if not x_hub_signature_256:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Hub-Signature-256 header"
        )
    
    if not body:
        raise HTTPException(
            status_code=400,
            detail="Missing request body"
        )
    
    # Compute HMAC signature
    secret = settings.GITHUB_WEBHOOK_SECRET.encode("utf-8")
    expected_signature = "sha256=" + hmac.new(
        secret,
        body,
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures (constant-time comparison)
    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )
    
    return True


# ============================================================================
# LLM Dependencies
# ============================================================================

def get_llm_client() -> LLMClient:
    """
    Provides LLM client based on configuration.
    
    Returns:
        LLMClient: Configured LLM client instance.
    """
    return LLMClient(
        provider=settings.LLM_PROVIDER,
        api_key=get_llm_api_key(),
        model=settings.LLM_MODEL,
        max_tokens=settings.LLM_MAX_TOKENS,
        temperature=settings.LLM_TEMPERATURE,
    )


def get_llm_api_key() -> str:
    """
    Gets the appropriate API key based on LLM provider.
    
    Returns:
        str: API key for the configured LLM provider.
    
    Raises:
        ValueError: If API key is not configured.
    """
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        return settings.ANTHROPIC_API_KEY
    
    elif provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not configured")
        return settings.OPENAI_API_KEY
    
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


# ============================================================================
# Storage Dependencies
# ============================================================================

def get_s3_client() -> Optional[S3Client]:
    """
    Provides S3 client for logs and review storage.
    
    Returns:
        Optional[S3Client]: Configured S3 client, or None if not configured.
    """
    if not settings.S3_BUCKET_NAME:
        return None
    
    return S3Client(
        bucket_name=settings.S3_BUCKET_NAME,
        region=settings.AWS_REGION,
        access_key_id=settings.AWS_ACCESS_KEY_ID,
        secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


# ============================================================================
# Utility Dependencies
# ============================================================================

async def get_request_body(request) -> bytes:
    """
    Extracts raw request body as bytes.
    
    This is used for webhook signature verification.
    
    Args:
        request: FastAPI Request object.
    
    Returns:
        bytes: Raw request body.
    """
    return await request.body()