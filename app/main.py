"""
FastAPI entrypoint for PR Review Agent.

This module initializes the FastAPI application and registers all routes.
Phase 1: Single-PR, event-driven analysis.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import webhooks, health
from app.config import settings
from app.observability.logging import setup_logging

# Initialize structured logging
setup_logging()

app = FastAPI(
    title="PR Review Agent",
    description="AI-powered Pull Request Review Agent - Phase 1",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])


@app.on_event("startup")
async def startup_event():
    """
    Runs on application startup.
    Initialize connections, validate configuration.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "PR Review Agent starting",
        extra={
            "environment": settings.ENVIRONMENT,
            "github_app_id": settings.GITHUB_APP_ID,
        }
    )


@app.on_event("shutdown")
async def shutdown_event():
    """
    Runs on application shutdown.
    Cleanup resources, close connections.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("PR Review Agent shutting down")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
    )