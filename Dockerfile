# ---------------------------------------------------------------------------
# Coinflip Production Multi-Stage Dockerfile
# Stage 1: Build TanStack React Frontend (Node 22)
# Stage 2: Python 3.12 Runtime for Coinflip Engine & Agent UI
# Multi-cloud deployment: Render, Hugging Face Spaces Docker, Google Cloud Run
# ---------------------------------------------------------------------------

# Stage 1: Build the frontend
FROM node:22-slim AS frontend-builder

WORKDIR /build

# Copy dependency specifications first for Docker layer caching
COPY agent_and_ui/frontend/package*.json ./
RUN npm ci || npm install

# Copy frontend source files and execute build
COPY agent_and_ui/frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim AS runner

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

# Copy application directories and essential project files
COPY shared_contracts/ /app/shared_contracts/
COPY sandbox_engine/ /app/sandbox_engine/
COPY benchmarks/ /app/benchmarks/
COPY agent_and_ui/ /app/agent_and_ui/
COPY NOTICE /app/NOTICE
COPY LICENSE /app/LICENSE
COPY pytest.ini /app/pytest.ini

# Copy fresh built frontend artifacts from Stage 1
COPY --from=frontend-builder /build/index.html /app/agent_and_ui/frontend/index.html
COPY --from=frontend-builder /build/assets /app/agent_and_ui/frontend/assets

# Create writable .cache directory for non-root users (Hugging Face Spaces UID 1000, Render, etc.)
RUN mkdir -p /app/.cache && chmod 777 /app/.cache

# Create a non-privileged user and adjust ownership
RUN useradd -m -u 1000 coinflip && \
    chown -R coinflip:coinflip /app

USER coinflip

# Expose standard web service port
EXPOSE 8000

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/health || exit 1

# Start FastAPI application with dynamic port binding for Render / Cloud Run / Hugging Face Spaces
CMD ["sh", "-c", "uvicorn agent_and_ui.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
