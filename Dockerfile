# ---------------------------------------------------------------------------
# Coinflip Production Dockerfile
# Multi-cloud deployment: Fly.io, Render, Google Cloud Run, Nebius VM
# ---------------------------------------------------------------------------

FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Install security updates and curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application directories
COPY agent_and_ui/ /app/agent_and_ui/
COPY sandbox_engine/ /app/sandbox_engine/
COPY benchmarks/ /app/benchmarks/
COPY shared_contracts/ /app/shared_contracts/

# Create a non-privileged user and adjust ownership
RUN useradd -m -u 1000 coinflip && \
    chown -R coinflip:coinflip /app

USER coinflip

# Expose standard web service port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Start FastAPI application with dynamic port binding for Fly.io / Render / Cloud Run
CMD ["sh", "-c", "uvicorn agent_and_ui.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
