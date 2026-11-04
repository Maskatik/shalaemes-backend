import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import Settings
from .db import init_db
from .routers import data, health, profile, sessions, words


def create_app(data_dir: Path | None = None) -> FastAPI:
    settings = Settings.from_env(data_dir)
    docs_enabled = os.getenv("DOCS_ENABLED", "1") == "1"
    app = FastAPI(
        title="ShalaEmes API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings
    init_db(settings.db_path)

    api_token = os.getenv("API_TOKEN", "").strip()
    if api_token:
        @app.middleware("http")
        async def require_api_token(request: Request, call_next):
            if request.url.path.startswith("/api/"):
                header = request.headers.get("authorization", "")
                supplied = header[7:].strip() if header.lower().startswith("bearer ") else request.headers.get("x-api-key", "").strip()
                if not secrets.compare_digest(supplied, api_token):
                    return JSONResponse(status_code=401, content={"detail": "unauthorized"})
            return await call_next(request)

    app.include_router(health.router)
    app.include_router(profile.router)
    app.include_router(sessions.router)
    app.include_router(data.router)
    app.include_router(words.router)
    return app


app = create_app()
