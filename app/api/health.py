"""
Health check endpoint.

Provides application health status and readiness checks.
"""

from fastapi import APIRouter, status
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any

from app.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    environment: str
    version: str
    checks: Dict[str, Any]


@router.get(
    "/",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Returns basic application health status"
)
async def health_check():
    """
    Basic health check endpoint.
    
    Returns:
        HealthResponse: Application health status.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        environment=settings.ENVIRONMENT,
        version="1.0.0",
        checks={
            "api": "ok"
        }
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness check",
    description="Returns application readiness status with dependency checks"
)
async def readiness_check():
    """
    Readiness check endpoint.
    
    Verifies that all required dependencies are configured and accessible.
    
    Returns:
        HealthResponse: Application readiness status with dependency checks.
    """
    checks = {}
    
    # Check GitHub configuration
    checks["github_app"] = "ok" if settings.GITHUB_APP_ID else "missing"
    checks["github_auth"] = "ok" if settings.GITHUB_PRIVATE_KEY else "missing"
    checks["github_webhook"] = "ok" if settings.GITHUB_WEBHOOK_SECRET else "missing"
    
    # Check LLM configuration
    llm_api_key_configured = False
    if settings.LLM_PROVIDER.lower() == "anthropic":
        llm_api_key_configured = bool(settings.ANTHROPIC_API_KEY)
    elif settings.LLM_PROVIDER.lower() == "openai":
        llm_api_key_configured = bool(settings.OPENAI_API_KEY)
    
    checks["llm_provider"] = settings.LLM_PROVIDER
    checks["llm_api_key"] = "ok" if llm_api_key_configured else "missing"
    
    # Check S3 configuration (optional)
    checks["s3_bucket"] = "ok" if settings.S3_BUCKET_NAME else "not_configured"
    
    # Determine overall status
    critical_checks = [
        checks["github_app"],
        checks["github_auth"],
        checks["github_webhook"],
        checks["llm_api_key"]
    ]
    
    overall_status = "ready" if all(c == "ok" for c in critical_checks) else "not_ready"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        environment=settings.ENVIRONMENT,
        version="1.0.0",
        checks=checks
    )


@router.get(
    "/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Simple liveness probe for container orchestration"
)
async def liveness_check():
    """
    Liveness check endpoint.
    
    Simple probe to verify the application is running.
    Used by container orchestration systems.
    
    Returns:
        dict: Simple status response.
    """
    return {"status": "alive"}