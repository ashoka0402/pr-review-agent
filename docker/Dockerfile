# Multi-stage Dockerfile for PR Review Agent
# Stage 1: Build stage with all dependencies
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build


    PATH="/root/.local/bin:$PATH" \
    APP_HOME=/app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Copy configuration files
COPY .env.example .env.example

# Make scripts executable
RUN chmod +x scripts/*.sh scripts/*.py
# Expose application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]
