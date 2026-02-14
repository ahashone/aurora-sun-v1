# =============================================================================
# Aurora Sun V1 -- Production Dockerfile
# Multi-stage build: install dependencies, then copy into slim runtime image.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build -- install Python dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build-time system dependencies (for compiled wheels like asyncpg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency specification first (layer caching)
COPY pyproject.toml ./

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# ---------------------------------------------------------------------------
# Stage 2: Runtime -- slim image with app code
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Install runtime-only system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user (moltbot) for running the application
RUN groupadd --gid 1000 moltbot && \
    useradd --uid 1000 --gid moltbot --create-home --shell /bin/bash moltbot

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY main.py ./
COPY alembic.ini ./
COPY pyproject.toml ./

# Create logs directory
RUN mkdir -p /app/logs && chown -R moltbot:moltbot /app

# Switch to non-root user
USER moltbot

# Expose application port
EXPOSE 8000

# Health check (matches docker-compose.prod.yml)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD curl -f http://localhost:8000/health || exit 1

# Entry point: uvicorn serving the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
