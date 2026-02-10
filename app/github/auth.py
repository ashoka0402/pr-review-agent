"""
GitHub App authentication module.

Handles JWT generation for GitHub App authentication and
installation token management.
"""

import time
import logging
from typing import Dict, Optional
import jwt
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GitHubAppAuth:
    """
    GitHub App authentication handler.
    
    Manages:
    - JWT generation for GitHub App authentication
    - Installation access token retrieval and caching
    """
    
    def __init__(self, app_id: str, private_key: str):
        """
        Initialize GitHub App authentication.
        
        Args:
            app_id: GitHub App ID
            private_key: GitHub App private key (PEM format)
        """
        self.app_id = app_id
        self.private_key = private_key
        self._installation_tokens: Dict[int, Dict] = {}
    
    def generate_jwt(self, expiration_seconds: int = 600) -> str:
        """
        Generate JWT for GitHub App authentication.
        
        JWT is used to authenticate as the GitHub App itself,
        before requesting installation tokens.
        
        Args:
            expiration_seconds: JWT expiration time (max 600 seconds)
        
        Returns:
            str: Encoded JWT token
        """
        now = int(time.time())
        
        payload = {
            "iat": now - 60,  # Issued at (60 seconds in past to account for clock drift)
            "exp": now + expiration_seconds,  # Expiration
            "iss": self.app_id,  # Issuer (GitHub App ID)
        }
        
        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256"
        )
        
        return token
    
    def get_installation_token(
        self,
        installation_id: int,
        api_url: str = "https://api.github.com"
    ) -> str:
        """
        Get installation access token for a specific installation.
        
        Installation tokens are cached and reused until they expire.
        
        Args:
            installation_id: GitHub App installation ID
            api_url: GitHub API base URL
        
        Returns:
            str: Installation access token
        
        Raises:
            Exception: If token retrieval fails
        """
        # Check if we have a valid cached token
        if installation_id in self._installation_tokens:
            cached = self._installation_tokens[installation_id]
            expires_at = datetime.fromisoformat(
                cached["expires_at"].replace("Z", "+00:00")
            )
            
            # Use cached token if it expires more than 5 minutes from now
            if expires_at > datetime.now(expires_at.tzinfo) + timedelta(minutes=5):
                logger.debug(
                    "Using cached installation token",
                    extra={"installation_id": installation_id}
                )
                return cached["token"]
        
        # Generate new installation token
        logger.info(
            "Requesting new installation token",
            extra={"installation_id": installation_id}
        )
        
        jwt_token = self.generate_jwt()
        
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        url = f"{api_url}/app/installations/{installation_id}/access_tokens"
        
        response = requests.post(url, headers=headers)
        
        if response.status_code != 201:
            logger.error(
                "Failed to get installation token",
                extra={
                    "installation_id": installation_id,
                    "status_code": response.status_code,
                    "response": response.text,
                }
            )
            raise Exception(
                f"Failed to get installation token: {response.status_code} {response.text}"
            )
        
        data = response.json()
        token = data["token"]
        expires_at = data["expires_at"]
        
        # Cache the token
        self._installation_tokens[installation_id] = {
            "token": token,
            "expires_at": expires_at,
        }
        
        logger.info(
            "Installation token retrieved",
            extra={
                "installation_id": installation_id,
                "expires_at": expires_at,
            }
        )
        
        return token
    
    def get_app_jwt(self) -> str:
        """
        Get JWT for GitHub App authentication.
        
        Convenience method for getting JWT token.
        
        Returns:
            str: JWT token
        """
        return self.generate_jwt()
    
    def clear_installation_token(self, installation_id: int):
        """
        Clear cached installation token.
        
        Useful for forcing token refresh.
        
        Args:
            installation_id: GitHub App installation ID
        """
        if installation_id in self._installation_tokens:
            del self._installation_tokens[installation_id]
            logger.debug(
                "Cleared cached installation token",
                extra={"installation_id": installation_id}
            )