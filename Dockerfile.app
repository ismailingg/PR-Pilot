# =============================================================================
# PR-Pilot — FastAPI Application
# =============================================================================

FROM python:3.12-slim

# System deps — git for merge simulation, curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install semgrep
RUN pip install --no-cache-dir semgrep

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install project dependencies
RUN uv pip install --system --no-cache ".[tools]" 2>/dev/null || \
    uv pip install --system --no-cache -e .

# Create directory for SQLite DB and secrets
RUN mkdir -p /app/data /app/secrets

# Non-root user for security
RUN useradd -m -u 1000 prpilot && chown -R prpilot:prpilot /app
USER prpilot

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "prtool.api:app", "--host", "0.0.0.0", "--port", "8000"]
