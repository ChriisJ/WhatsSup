"""FastAPI entrypoint for WhatsSup."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .bot_bridge import bot_action
from .config import get_settings
from .database import AsyncSessionLocal, init_db
from .interactions import ensure_seed_rules
from .models import User, UserProfile
from .notifiers import NotifierManager
from .routes import auth, blood_pressure, intake, profile, stats, supplements
from .scheduler import start_scheduler
from .seed_catalog import ensure_seed_catalog
from .security import hash_password

logger = logging.getLogger("whatssup")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


async def _bootstrap_admin() -> None:
    s = get_settings()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        if result.scalars().first() is None:
            user = User(
                username=s.default_admin_username,
                password_hash=hash_password(s.default_admin_password),
                is_admin=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            session.add(UserProfile(user_id=user.id))
            await session.commit()
            logger.warning(
                "Created default admin user '%s'. CHANGE THE PASSWORD in .env on first run.",
                user.username,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Init DB + seed
    await init_db()
    await _bootstrap_admin()
    async with AsyncSessionLocal() as session:
        await ensure_seed_catalog(session)
        await ensure_seed_rules(session)

    # 2. Build notifier manager + bridge
    notifiers = NotifierManager.default()

    async def _bridge(action: str, **kwargs):
        async with AsyncSessionLocal() as session:
            return await bot_action(session, action, **kwargs)

    notifiers.discord.attach_intake_repo(_bridge)
    notifiers.telegram.attach_intake_repo(_bridge)
    await notifiers.start_all()

    # 3. Scheduler
    sched = start_scheduler(AsyncSessionLocal, notifiers)

    app.state.notifiers = notifiers
    app.state.scheduler = sched

    try:
        yield
    finally:
        await notifiers.stop_all()
        try:
            sched.shutdown(wait=False)
        except Exception:
            pass


app = FastAPI(
    title="WhatsSup",
    description="Self-hosted supplement & medication tracker with smart reminders.",
    version="0.1.0",
    lifespan=lifespan,
)

# Permissive CORS for local-network self-hosting. Lock this down if you expose to the internet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- API ----
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(supplements.catalog_router)
app.include_router(supplements.tracking_router)
app.include_router(intake.router)
app.include_router(blood_pressure.router)
app.include_router(stats.router)


@app.get("/api/health")
async def health():
    notifiers = getattr(app.state, "notifiers", None)
    async def _safe(check):
        if not notifiers:
            return False
        try:
            return await check()
        except Exception:
            return False

    return {
        "status": "ok",
        "version": "0.1.0",
        "discord_enabled":  await _safe(notifiers.discord.is_enabled),
        "telegram_enabled": await _safe(notifiers.telegram.is_enabled),
        "whatsapp_enabled": await _safe(notifiers.whatsapp.is_enabled),
    }


# ---- Frontend (SPA) ----
if FRONTEND_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND_DIR)),
        name="static",
    )

    @app.get("/")
    async def root():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/manifest.json")
    async def manifest():
        return FileResponse(FRONTEND_DIR / "manifest.json", media_type="application/manifest+json")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(FRONTEND_DIR / "sw.js", media_type="application/javascript")

    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        # SPA-style fallback: serve index.html for unknown non-API routes
        if path.startswith("api/") or path.startswith("static/"):
            return {"detail": "Not found"}
        target = FRONTEND_DIR / path
        if target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    @app.get("/")
    async def root_no_frontend():
        return {
            "name": "WhatsSup API",
            "note": "Frontend not built yet. Visit /docs for Swagger UI.",
        }


def run() -> None:
    """Entrypoint for `python -m backend.main`."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "backend.main:app",
        host=s.app_host,
        port=s.app_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
