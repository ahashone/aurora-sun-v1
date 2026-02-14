"""
Aurora Sun V1 -- Application Entry Point.

Starts the FastAPI server via uvicorn.

Usage:
    python main.py              # Development (reload enabled)
    uvicorn main:app --host 0.0.0.0 --port 8000  # Production

Reference: ARCHITECTURE.md, docker-compose.prod.yml
"""

from __future__ import annotations

import os

import uvicorn

from src.api import create_app

app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("AURORA_PORT", "8000"))
    host = os.getenv("AURORA_HOST", "0.0.0.0")
    reload = os.getenv("AURORA_DEV_MODE", "0") == "1"

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
