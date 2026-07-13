"""Router agregador del módulo `catalogos`.

F0-00 no expone ninguna entidad todavía (no hay tablas). Desde F0-01, cada catálogo
construye su router con `build_crud_router(...)` y lo cuelga aquí con `include_router`,
de modo que `main.py` solo incluye este agregador una vez.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.catalogos.afiliado import router as afiliado_router
from app.modules.catalogos.agencia import router as agencia_router
from app.modules.catalogos.anunciante import marca_router
from app.modules.catalogos.anunciante import router as anunciante_router
from app.modules.catalogos.estacion import router as estacion_router
from app.modules.catalogos.plaza import router as plaza_router
from app.modules.catalogos.tarifa import router as tarifa_router

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

# F0-01 · catálogos operativos (Plaza → Afiliado → Estación).
router.include_router(plaza_router)
router.include_router(afiliado_router)
router.include_router(estacion_router)

# F0-02 · tarifas por plaza (depende de Plaza).
router.include_router(tarifa_router)

# F0-03 · catálogos comerciales (Agencia → Anunciante → Marca/Contrato).
# Tanda 1: Agencia · Tanda 2: Anunciante + Marca anidada.
router.include_router(agencia_router)
router.include_router(anunciante_router)
router.include_router(marca_router)
