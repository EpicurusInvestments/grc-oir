"""Router agregador del módulo `ordenes` (F1).

Tanda 3 (API de lectura): cada entidad expone sus endpoints `GET` en su propio archivo
(mismo patrón de archivo plano de F0) y los cuelga aquí, de modo que `main.py` solo
incluye este agregador una vez. Los endpoints de escritura (captura/edición) llegan en
la Tanda 5.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.ordenes.adjuntos import router as adjuntos_router
from app.modules.ordenes.incidencia import router as incidencia_router
from app.modules.ordenes.orden_cliente import router_clientes
from app.modules.ordenes.orden_estacion import router_estaciones
from app.modules.ordenes.verificacion import router as verificacion_router

router = APIRouter(prefix="/ordenes", tags=["ordenes"])

router.include_router(router_clientes)
router.include_router(router_estaciones)
router.include_router(verificacion_router)
router.include_router(incidencia_router)
router.include_router(adjuntos_router)
