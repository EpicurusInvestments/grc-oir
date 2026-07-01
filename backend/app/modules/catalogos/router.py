"""Router agregador del módulo `catalogos`.

F0-00 no expone ninguna entidad todavía (no hay tablas). Desde F0-01, cada catálogo
construye su router con `build_crud_router(...)` y lo cuelga aquí con `include_router`,
de modo que `main.py` solo incluye este agregador una vez.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

# Desde F0-01, por cada catálogo:
#   from app.modules.catalogos.plaza import router as plaza_router
#   router.include_router(plaza_router)
