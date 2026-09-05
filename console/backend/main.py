"""FastAPI application factory for the ops console.

Run locally: `uv run uvicorn console.backend.main:app --reload`
(needs a reachable Postgres — use the Docker stack or set DATABASE_URL).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from console.backend import auth, chat, health, onboarding, resume
from console.backend.config import Settings, get_settings
from console.backend.db import configure_engine, seed_admin


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Connect + create tables + seed admin on startup (not at import time).
        configure_engine(resolved.database_url)
        seed_admin(resolved)
        yield

    app = FastAPI(title="Agent OS — Ops Console", version="0.1.0", lifespan=lifespan)
    # Pin request-time settings to the snapshot the engine is built from.
    app.dependency_overrides[get_settings] = lambda: resolved

    origins = os.environ.get("OPS_CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(onboarding.router)
    app.include_router(resume.router)
    app.include_router(chat.router)
    return app


app = create_app()
