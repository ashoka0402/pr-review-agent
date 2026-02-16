# PR Review Agent

> **AI-Powered Pull Request Review Agent with Agentic Reasoning**

An intelligent, production-grade GitHub App that automatically analyzes pull requests and provides structured, actionable code review feedback powered by LLMs and static analysis.

[![CI Pipeline](https://github.com/your-org/pr-review-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/pr-review-agent/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development](#development)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

The **PR Review Agent** combines deterministic static analysis with LLM-powered intelligence and agentic reasoning to deliver high-quality, context-aware code reviews automatically. It integrates seamlessly with GitHub as a GitHub App, analyzing pull requests in real-time and posting structured feedback directly to your PRs.

### Core Philosophy

1. **Deterministic First, LLM Second** - Static analysis provides ground truth; LLMs add intelligence
2. **Schema-Enforced Outputs** - Structured, consistent review format
3. **Agentic Reasoning** - Self-improving analysis with bounded iterations
4. **Production-Grade** - Built for reliability, observability, and scale

---

## Key Features

### Comprehensive Analysis

- **Unified diff parsing** with line-level change tracking
- **Multi-language support** with automatic language detection
- **Cross-file dependency analysis** to catch integration issues
- **Heuristic risk detection** for large PRs, critical files, and security-sensitive areas

### Static Analysis

- **Linting** (flake8, pylint) for code quality
- **Security scanning** (Bandit) for vulnerabilities
- **Complexity analysis** (cyclomatic complexity, maintainability index)
- **Test coverage integration** (optional)

### AI-Powered Intelligence

- **LLM-based code review** with multiple provider support (OpenAI, Anthropic, Azure)
- **Constrained, schema-driven prompts** to prevent hallucinations
- **Context-aware analysis** using PR metadata, commit history, and file relationships

### Agentic Reasoning

- **Tool-using agent** that can re-analyze ambiguous or complex changes
- **Confidence-based refinement** before publishing reviews
- **Bounded iterations** to prevent runaway costs
- **Self-improving feedback loop** for better accuracy over time

### Rich Review Output

- **Structured findings** with severity levels, categories, and suggestions
- **Inline comments** mapped to specific diff lines
- **Overall risk scoring** (0-10 scale)
- **Actionable recommendations**: Approve, Changes Requested, or Needs Attention

### Production Ready

- **Event-driven architecture** with webhook processing
- **Stateless design** for horizontal scalability
- **Comprehensive observability** (structured logging, metrics, error tracking)
- **S3 integration** for review artifact storage
- **Docker support** with multi-stage builds
- **CI/CD pipeline** with automated testing and deployment

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         GitHub                              │
│                    (Webhook Events)                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Webhook Handler                  │
│                  (Signature Verification)                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Background Processor                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌─────────────┐ ┌────────────┐
│ Diff Parser  │ │ Risk        │ │  GitHub    │
│              │ │ Analyzer    │ │  Client    │
└──────┬───────┘ └──────┬──────┘ └─────┬──────┘
       │                │              │
       └────────────────┼──────────────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Static Analysis Engine                    │
│         (Linting, Security, Complexity Analysis)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      LLM Layer                              │
│            (Schema-Driven Prompt Generation)                │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agentic Reasoning                        │
│        (Tool-Using Agent with Bounded Iterations)           │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                   Review Formatter                          │
│         (Structured Output with Inline Comments)            │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌─────────────┐ ┌────────────┐
│   GitHub     │ │     S3      │ │  Metrics   │
│   Review     │ │   Storage   │ │  & Logs    │
└──────────────┘ └─────────────┘ └────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose 
- GitHub App credentials
- LLM API key (OpenAI)

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/pr-review-agent.git
cd pr-review-agent
```

### 2. Set Up GitHub App

Run the interactive bootstrap script:

```bash
python scripts/bootstrap_github_app.py
```

Or manually create a GitHub App:

1. Go to GitHub Settings → Developer settings → GitHub Apps
2. Create a new GitHub App with these settings:
   - **Webhook URL**: `https://your-domain.com/api/webhooks/github`
   - **Webhook secret**: Generate a strong secret
   - **Permissions**:
     - Repository: Contents (Read), Pull Requests (Read & Write)
   - **Subscribe to events**: Pull request, Pull request review

3. Generate and download the private key
4. Install the app on your repositories

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required variables:

- `GITHUB_APP_ID`
- `GITHUB_INSTALLATION_ID`
- `GITHUB_WEBHOOK_SECRET`
- `GITHUB_PRIVATE_KEY_PATH`
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`

### 4. Run with Docker Compose

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f app

# Check health
curl http://localhost/health
```

### 5. Run Locally (Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Configure GitHub Webhook

Point your GitHub App webhook to:

```
https://your-domain.com/api/webhooks/github
```

For local development, use ngrok:

```bash
ngrok http 8000
# Use the ngrok URL as your webhook URL
```

---

## Configuration

### Environment Variables

See [`.env.example`](.env.example) for all available configuration options.

**Key configurations:**

| Variable                     | Description                             | Default  |
| ---------------------------- | --------------------------------------- | -------- |
| `LLM_PROVIDER`               | LLM provider (openai, anthropic, azure) | `openai` |
| `MAX_AGENT_ITERATIONS`       | Max agentic reasoning loops             | `3`      |
| `AGENT_CONFIDENCE_THRESHOLD` | Confidence required to publish          | `0.75`   |
| `AUTO_APPROVE_THRESHOLD`     | Risk score for auto-approval            | `3.0`    |
| `LOG_LEVEL`                  | Logging verbosity                       | `INFO`   |

### Risk Analysis Thresholds

Customize risk detection in `.env`:

```bash
LARGE_PR_FILE_THRESHOLD=15
LARGE_PR_LINES_THRESHOLD=500
HIGH_COMPLEXITY_THRESHOLD=15
CRITICAL_FILE_PATTERNS=auth,security,payment,database,config
```

### Static Analysis

Enable/disable specific tools:

```bash
ENABLE_FLAKE8=true
ENABLE_PYLINT=true
ENABLE_BANDIT=true
ENABLE_COMPLEXITY_ANALYSIS=true
```

---

## 📖 Usage

### Automatic Reviews

Once installed, the agent automatically reviews PRs when:

- A new PR is opened
- Commits are pushed to an open PR
- A PR is reopened

### Manual Trigger

Comment on a PR to trigger re-analysis:

```
@pr-review-agent review
```

### Review Output

The agent posts:

1. **Overall Summary** - High-level assessment with risk score
2. **Inline Comments** - Specific issues mapped to code lines
3. **Recommendations** - Approve, Request Changes, or Needs Attention

Example review comment:

```
## PR Analysis Summary

**Risk Score:** 6.5/10 (Medium-High)

### Findings
- 🔴 **Security**: Potential SQL injection in `app/db.py:42`
- 🟡 **Code Quality**: High cyclomatic complexity in `app/utils.py:105`
- 🟢 **Best Practice**: Good use of type hints

### Recommendation
**Changes Requested** - Address security concerns before merging.
```

---

## Development

### Project Structure

```
pr-review-agent/
├── app/
│   ├── main.py                 # FastAPI entrypoint
│   ├── config.py               # Configuration management
│   ├── dependencies.py         # Dependency injection
│   ├── api/                    # API routes and webhooks
│   ├── github/                 # GitHub integration
│   ├── analysis/               # Diff parsing and risk analysis
│   ├── static_analysis/        # Linting, security, complexity
│   ├── llm/                    # LLM client abstraction
│   ├── agent/                  # Agentic reasoning engine
│   ├── review/                 # Review formatting and output
│   ├── storage/                # S3 and artifact storage
│   └── observability/          # Logging and metrics
├── scripts/
│   ├── run_static_checks.sh    # Run all static analysis
│   └── bootstrap_github_app.py # GitHub App setup helper
├── docker/
│   ├── Dockerfile
│   └── nginx.conf
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── .github/workflows/
│   └── ci.yml                  # CI/CD pipeline
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/ -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run static checks
bash scripts/run_static_checks.sh
```

### Code Quality

```bash
# Format code
black app/ --line-length 120
isort app/ --profile black

# Type checking
mypy app/ --ignore-missing-imports

# Linting
flake8 app/ --max-line-length=120
pylint app/ --max-line-length=120
```

### Local Development Workflow

1. **Create a feature branch**

   ```bash
   git checkout -b feature/your-feature
   ```

2. **Make changes and test**

   ```bash
   pytest
   bash scripts/run_static_checks.sh
   ```

3. **Commit with conventional commits**

   ```bash
   git commit -m "feat: add new feature"
   ```

4. **Push and create PR**
   ```bash
   git push origin feature/your-feature
   ```

---

## Deployment

### Docker Deployment

```bash
# Build image
docker build -f docker/Dockerfile -t pr-review-agent:latest .

# Run container
docker run -d \
  --name pr-review-agent \
  -p 8000:8000 \
  --env-file .env \
  pr-review-agent:latest
```

### Docker Compose (Production)

```bash
# Deploy all services
docker-compose -f docker-compose.yml up -d

# Scale application
docker-compose up -d --scale app=3
```

### Kubernetes (Advanced)

Example deployment manifests in `k8s/` (coming soon).

### Environment-Specific Configuration

**Development:**

```bash
DEBUG=true
LOG_LEVEL=DEBUG
MOCK_LLM_RESPONSES=true
```

**Production:**

```bash
DEBUG=false
LOG_LEVEL=INFO
WORKERS=4
VERIFY_WEBHOOK_SIGNATURE=true
ENABLE_S3_STORAGE=true
```

---

## API Documentation
Let's see if the metrics are true -----------testing pr
### Endpoints

| Endpoint               | Method | Description            |
| ---------------------- | ------ | ---------------------- |
| `/health`              | GET    | Health check           |
| `/ready`               | GET    | Readiness check        |
| `/api/webhooks/github` | POST   | GitHub webhook handler |
| `/metrics`             | GET    | Prometheus metrics     |

### Webhook Events

The agent listens for:

- `pull_request.opened`
- `pull_request.synchronize`
- `pull_request.reopened`

### API Response Format

```json
{
  "status": "processing",
  "pr_number": 123,
  "repository": "owner/repo",
  "message": "Review queued for processing"
}
```

---


### Development Setup

1. Fork the repository
2. Clone your fork
3. Create a feature branch
4. Make your changes
5. Run tests and static checks
6. Submit a pull request

### Code Standards

- Follow PEP 8 style guide
- Write tests for new features
- Maintain >80% code coverage
- Use type hints
- Document public APIs
  
---

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Static analysis powered by [Bandit](https://github.com/PyCQA/bandit), [Flake8](https://flake8.pycqa.org/), and [Pylint](https://pylint.org/)
- LLM integration via [OpenAI](https://openai.com/) and [Anthropic](https://anthropic.com/)

---

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/pr-review-agent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/pr-review-agent/discussions)
- **Email**: support@your-org.com

---

**Made with ❤️ by the PR Review Agent Team**
