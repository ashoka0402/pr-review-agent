"""
Configuration module for PR Review Agent.

Loads environment variables and provides centralized settings.
All secrets and configuration are managed through environment variables.
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Secrets are loaded from environment or .env file.
    Never commit secrets to version control.
    """
    
    # Application
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    PORT: int = Field(default=8000, env="PORT")
    ALLOWED_ORIGINS: List[str] = Field(
        default=["*"],
        env="ALLOWED_ORIGINS"
    )
    
    # GitHub App Configuration
    GITHUB_APP_ID: str = Field(..., env="GITHUB_APP_ID")
    GITHUB_PRIVATE_KEY: str = Field(..., env="GITHUB_PRIVATE_KEY")
    GITHUB_WEBHOOK_SECRET: str = Field(..., env="GITHUB_WEBHOOK_SECRET")
    GITHUB_API_URL: str = Field(
        default="https://api.github.com",
        env="GITHUB_API_URL"
    )
    
    # LLM Configuration
    LLM_PROVIDER: str = Field(default="anthropic", env="LLM_PROVIDER")
    ANTHROPIC_API_KEY: str = Field(default="", env="ANTHROPIC_API_KEY")
    OPENAI_API_KEY: str = Field(default="", env="OPENAI_API_KEY")
    LLM_MODEL: str = Field(
        default="claude-sonnet-4-20250514",
        env="LLM_MODEL"
    )
    LLM_MAX_TOKENS: int = Field(default=4096, env="LLM_MAX_TOKENS")
    LLM_TEMPERATURE: float = Field(default=0.3, env="LLM_TEMPERATURE")
    
    # AWS S3 Configuration
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    AWS_ACCESS_KEY_ID: str = Field(default="", env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = Field(default="", env="AWS_SECRET_ACCESS_KEY")
    S3_BUCKET_NAME: str = Field(default="", env="S3_BUCKET_NAME")
    S3_LOGS_PREFIX: str = Field(default="logs/", env="S3_LOGS_PREFIX")
    S3_REVIEWS_PREFIX: str = Field(default="reviews/", env="S3_REVIEWS_PREFIX")
    
    # Static Analysis Configuration
    ENABLE_LINTING: bool = Field(default=True, env="ENABLE_LINTING")
    ENABLE_SECURITY_SCAN: bool = Field(default=True, env="ENABLE_SECURITY_SCAN")
    ENABLE_COMPLEXITY_ANALYSIS: bool = Field(default=True, env="ENABLE_COMPLEXITY_ANALYSIS")
    
    # Linting Tools
    FLAKE8_MAX_LINE_LENGTH: int = Field(default=120, env="FLAKE8_MAX_LINE_LENGTH")
    PYLINT_THRESHOLD: float = Field(default=7.0, env="PYLINT_THRESHOLD")
    
    # Security Scanning
    BANDIT_SEVERITY_LEVEL: str = Field(default="MEDIUM", env="BANDIT_SEVERITY_LEVEL")
    
    # Complexity Thresholds
    CYCLOMATIC_COMPLEXITY_THRESHOLD: int = Field(default=10, env="CYCLOMATIC_COMPLEXITY_THRESHOLD")
    MAINTAINABILITY_INDEX_THRESHOLD: int = Field(default=20, env="MAINTAINABILITY_INDEX_THRESHOLD")
    
    # Agent Configuration
    AGENT_MAX_ITERATIONS: int = Field(default=3, env="AGENT_MAX_ITERATIONS")
    AGENT_CONFIDENCE_THRESHOLD: float = Field(default=0.7, env="AGENT_CONFIDENCE_THRESHOLD")
    
    # Review Configuration
    MAX_DIFF_SIZE_BYTES: int = Field(
        default=1_000_000,  # 1MB
        env="MAX_DIFF_SIZE_BYTES"
    )
    MAX_FILES_PER_PR: int = Field(default=100, env="MAX_FILES_PER_PR")
    REVIEW_TIMEOUT_SECONDS: int = Field(default=300, env="REVIEW_TIMEOUT_SECONDS")
    
    # Risk Detection
    LARGE_DIFF_THRESHOLD_LINES: int = Field(default=500, env="LARGE_DIFF_THRESHOLD_LINES")
    CRITICAL_FILE_PATTERNS: List[str] = Field(
        default=[
            "*/migrations/*",
            "*/settings.py",
            "*/config/*",
            "*/auth/*",
            "Dockerfile",
            "docker-compose.yml",
        ],
        env="CRITICAL_FILE_PATTERNS"
    )
    
    # Observability
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")
    ENABLE_METRICS: bool = Field(default=True, env="ENABLE_METRICS")
    
    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_allowed_origins(cls, v):
        """Parse comma-separated ALLOWED_ORIGINS into a list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("CRITICAL_FILE_PATTERNS", pre=True)
    def parse_critical_file_patterns(cls, v):
        """Parse comma-separated CRITICAL_FILE_PATTERNS into a list."""
        if isinstance(v, str):
            return [pattern.strip() for pattern in v.split(",")]
        return v
    
    @validator("GITHUB_PRIVATE_KEY", pre=True)
    def parse_private_key(cls, v):
        """
        Parse GitHub private key.
        Support both raw key and base64-encoded key.
        """
        if v and "\\n" in v:
            # Replace literal \n with actual newlines
            return v.replace("\\n", "\n")
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Global settings instance
settings = Settings()