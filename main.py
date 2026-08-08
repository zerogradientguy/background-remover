"""
Entrypoint for the AI Toolkit API.

Run:
    python main.py
    # or
    uvicorn main:app --host 0.0.0.0 --port 8000

For production behind a process manager:
    gunicorn -k uvicorn.workers.UvicornWorker -w 1 main:app
"""
from __future__ import annotations

from app.config import get_settings
from app.server import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
