"""Arranque de la API del Sistema GRC-OIR.

- Todo cuelga de `/api/v1`. OpenAPI activo en `/docs` (no se desactiva).
- Handlers de error centrales (sobre uniforme).
- `/health` (vivo) y `/health/db` (prueba la conexión a RDS bajo demanda); la app
  arranca aunque RDS no sea alcanzable (engine perezoso).
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.db import get_engine
from app.core.errors import register_error_handlers
from app.modules.catalogos.router import router as catalogos_router

app = FastAPI(
    title="Sistema GRC-OIR — API",
    version="0.1.0",
    description="Backend del Sistema GRC-OIR (Grupo Radio Centro / OIR).",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# CORS: el frontend (SPA) vive en otro origen. Los orígenes permitidos son CONFIGURABLES
# (CORS_ORIGINS en el entorno), nunca hardcodeados: en producción se pone el dominio real.
# Se permiten todos los métodos y headers para cubrir el preflight (OPTIONS) de POST/PUT y
# los headers de auth de desarrollo (X-Dev-User / X-Dev-Area). Ver ADR-013.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

# ── Salud ──────────────────────────────────────────────────────────────────────
health = APIRouter(tags=["health"])


@health.get("/health")
def health_check() -> dict[str, str]:
    """Vivo: no toca la base de datos."""
    return {"status": "ok"}


@health.get("/health/db")
def health_db() -> dict[str, str]:
    """Prueba la conexión a SQL Server (RDS). Útil para validar `.env` y red."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "reachable"}
    except SQLAlchemyError as exc:
        return {"status": "error", "db": "unreachable", "detalle": exc.__class__.__name__}


app.include_router(health)

# ── API v1 ──────────────────────────────────────────────────────────────────────
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(catalogos_router)
app.include_router(api_v1)
