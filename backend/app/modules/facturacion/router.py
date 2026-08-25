"""Router agregador del módulo `facturacion` (F2).

Cada entidad expone sus endpoints en su propio archivo (mismo patrón de archivo plano de
F0 y F1) y los cuelga aquí, de modo que `main.py` incluya este agregador una sola vez.

Tanda 1: solo endpoints `GET`. La escritura, las transiciones de estado y los adjuntos
llegan en la Tanda 2.

Ojo con los permisos, que NO son uniformes dentro del módulo: `/facturacion/clientes/*`
exige `facturacion:*` (captura Facturación) y el resto exige `costos:*` (captura CxP).
Ver el `__init__.py` del módulo.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.facturacion.costo_adicional import router_costos
from app.modules.facturacion.factura_afiliado import router_afiliados
from app.modules.facturacion.factura_agencia import router_agencias
from app.modules.facturacion.factura_cliente import router_clientes

router = APIRouter(prefix="/facturacion", tags=["facturacion"])

router.include_router(router_clientes)
router.include_router(router_afiliados)
router.include_router(router_agencias)
router.include_router(router_costos)
