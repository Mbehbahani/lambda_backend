"""
FastAPI application entry-point.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import health, ai

settings = get_settings()

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(ai.router)
