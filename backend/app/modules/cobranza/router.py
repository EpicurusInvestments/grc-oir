"""Router agregador del módulo `cobranza` (F3).

Cada entidad expone sus endpoints en su propio archivo (mismo patrón de F0/F1/F2) y se
cuelgan aquí, para que `main.py` incluya este agregador una sola vez.

Los permisos NO son uniformes dentro del módulo (ver `__init__.py`): `/cobranza/
facturas/*` y `/cobranza/pagos/*` exigen `cobranza:*` (captura CxC); `/cobranza/
requisiciones/*` exige `pagos:*` (captura CxP); `/cobranza/movimientos-bancarios/*`
exige `pagos:leer` en el router + `Area.TESORERIA`/`Admin` verificado en el servicio
(ADR-046 — es la primera vez que Tesorería captura en el proyecto).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.cobranza.adjuntos import router as adjuntos_router
from app.modules.cobranza.cobranza_factura import (
    router_cobranza,
    router_pagos_cliente,
    router_pagos_cliente_por_id,
)
from app.modules.cobranza.movimiento_bancario import router as movimiento_bancario_router
from app.modules.cobranza.requisicion import router as requisicion_router

router = APIRouter(prefix="/cobranza", tags=["cobranza"])

router.include_router(router_cobranza)
router.include_router(router_pagos_cliente)
router.include_router(router_pagos_cliente_por_id)
router.include_router(requisicion_router)
router.include_router(movimiento_bancario_router)
router.include_router(adjuntos_router)
