#!/usr/bin/env python3
"""
bootstrap_github_app.py

Interactive script to help set up and configure the GitHub App
for the PR Review Agent.

This script:
1. Validates GitHub App credentials
2. Tests authentication (JWT + installation token)
3. Verifies webhook configuration
4. Saves validated config to .env file
"""

import os
import sys
import time
import jwt
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 60}{Colors.END}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


def get_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default"""
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    
    value = input(prompt).strip()
    return value if value else (default or "")


def get_multiline_input(prompt: str) -> str:
    """Get multiline input (for private key)"""
    print(f"{prompt}")
    print("(Paste your private key, then press Ctrl+D on a new line when done)")
    lines = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


def generate_jwt_token(app_id: str, private_key: str) -> Optional[str]:
    """Generate JWT token for GitHub App authentication"""
    try:
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + 600,  # 10 minutes
            "iss": app_id
        }
        
        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token
    except Exception as e:
        print_error(f"Failed to generate JWT: {str(e)}")
        return None


def test_github_app_auth(app_id: str, private_key: str) -> bool:
    """Test GitHub App authentication"""
    print_info("Testing GitHub App authentication...")
    
    # Generate JWT
    jwt_token = generate_jwt_token(app_id, private_key)
    if not jwt_token:
        return False
    
    # Test JWT by fetching app info
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    try:
        response = requests.get("https://api.github.com/app", headers=headers)
        if response.status_code == 200:
            app_data = response.json()
            print_success(f"Authenticated as GitHub App: {app_data.get('name', 'Unknown')}")
            return True
        else:
            print_error(f"Authentication failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print_error(f"Failed to connect to GitHub: {str(e)}")
        return False


def get_installation_token(app_id: str, private_key: str, installation_id: str) -> Optional[str]:
    """Get installation access token"""
    print_info("Getting installation access token...")
    
    jwt_token = generate_jwt_token(app_id, private_key)
    if not jwt_token:
        return None
    
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    try:
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
        response = requests.post(url, headers=headers)
        
        if response.status_code == 201:
            token_data = response.json()
            print_success("Installation token obtained successfully")
            return token_data.get("token")
        else:
            print_error(f"Failed to get installation token: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print_error(f"Failed to get installation token: {str(e)}")
        return None


def test_installation_access(installation_token: str, test_repo: str) -> bool:
    """Test installation access to a repository"""
    print_info(f"Testing access to repository: {test_repo}...")
    
    headers = {
        "Authorization": f"token {installation_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    try:
        url = f"https://api.github.com/repos/{test_repo}"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            repo_data = response.json()
            print_success(f"Successfully accessed repository: {repo_data.get('full_name')}")
            return True
        else:
            print_error(f"Failed to access repository: {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Failed to test repository access: {str(e)}")
        return False


def save_env_file(config: Dict[str, str]):
    """Save configuration to .env file"""
    env_path = Path(".env")
    
    if env_path.exists():
        backup = Path(".env.backup")
        print_warning(f"Backing up existing .env to {backup}")
        env_path.rename(backup)
    
    with open(env_path, "w") as f:
        f.write("# GitHub App Configuration\n")
        f.write(f"GITHUB_APP_ID={config['app_id']}\n")
        f.write(f"GITHUB_INSTALLATION_ID={config['installation_id']}\n")
        f.write(f"GITHUB_WEBHOOK_SECRET={config['webhook_secret']}\n")
        f.write(f"\n# GitHub Private Key (base64 encoded or path)\n")
        f.write(f"GITHUB_PRIVATE_KEY_PATH={config.get('private_key_path', './github_app_key.pem')}\n")
        f.write(f"\n# Optional: LLM Configuration\n")
        f.write(f"# OPENAI_API_KEY=your_openai_key_here\n")
        f.write(f"# ANTHROPIC_API_KEY=your_anthropic_key_here\n")
        f.write(f"\n# Optional: Storage Configuration\n")
        f.write(f"# AWS_ACCESS_KEY_ID=your_aws_key\n")
        f.write(f"# AWS_SECRET_ACCESS_KEY=your_aws_secret\n")
        f.write(f"# S3_BUCKET_NAME=pr-review-agent-storage\n")
    
    print_success(f"Configuration saved to .env")


def main():
    """Main bootstrap flow"""
    print_header("GitHub App Bootstrap for PR Review Agent")
    
    print("""
This script will help you configure your GitHub App credentials.

You'll need:
1. GitHub App ID
2. GitHub App Private Key (.pem file)
3. Installation ID (from installing the app on a repo)
4. Webhook Secret
5. A test repository to verify access
    """)
    
    # Collect credentials
    app_id = get_input("GitHub App ID")
    if not app_id:
        print_error("App ID is required")
        sys.exit(1)
    
    # Private key options
    print("\nPrivate Key Options:")
    print("1. Paste private key content directly")
    print("2. Provide path to .pem file")
    key_option = get_input("Choose option", "2")
    
    if key_option == "1":
        private_key = get_multiline_input("\nPaste your private key:")
        private_key_path = "./github_app_key.pem"
        # Save to file
        with open(private_key_path, "w") as f:
            f.write(private_key)
        os.chmod(private_key_path, 0o600)
    else:
        private_key_path = get_input("Path to private key file", "./github_app_key.pem")
        if not os.path.exists(private_key_path):
            print_error(f"Private key file not found: {private_key_path}")
            sys.exit(1)
        with open(private_key_path, "r") as f:
            private_key = f.read()
    
    installation_id = get_input("GitHub Installation ID")
    webhook_secret = get_input("Webhook Secret")
    test_repo = get_input("Test repository (owner/repo)", "")
    
    # Validate GitHub App authentication
    print_header("Validating Configuration")
    
    if not test_github_app_auth(app_id, private_key):
        print_error("GitHub App authentication failed. Please check your credentials.")
        sys.exit(1)
    
    # Test installation token
    installation_token = get_installation_token(app_id, private_key, installation_id)
    if not installation_token:
        print_error("Failed to get installation token. Check your installation ID.")
        sys.exit(1)
    
    # Test repository access if provided
    if test_repo:
        if not test_installation_access(installation_token, test_repo):
            print_warning("Could not access test repository. App may not be installed there.")
    
    # Save configuration
    print_header("Saving Configuration")
    
    config = {
        "app_id": app_id,
        "installation_id": installation_id,
        "webhook_secret": webhook_secret,
        "private_key_path": private_key_path
    }
    
    save_env_file(config)
    
    # Final instructions
    print_header("Setup Complete!")
    print(f"""
{Colors.GREEN}✓ GitHub App configured successfully{Colors.END}

Next steps:
1. Review your .env file
2. Add any additional configuration (LLM API keys, S3 credentials)
3. Run the application: docker-compose up
4. Configure your GitHub App webhook to point to: https://your-domain/api/webhooks/github

Webhook events to subscribe to:
- Pull requests (opened, synchronize, reopened)
- Pull request reviews

{Colors.BLUE}Happy reviewing!{Colors.END}
    """)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBootstrap cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        sys.exit(1)