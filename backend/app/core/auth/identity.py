"""Identidad del usuario autenticado: el ENUM de áreas y `CurrentUser`.

Vive aquí —y no en `core/security.py`— porque es lo que **producen** los adaptadores de
autenticación (`core/auth/adapter_*.py`) y lo que **consume** el RBAC
(`core/security.py`). Tenerlo en un módulo sin dependencias evita el ciclo de importación
`security ↔ auth`.

`core/security.py` re-exporta ambos, así que los imports existentes de F0
(`from app.core.security import Area, CurrentUser`) siguen funcionando **sin cambios**.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Area(StrEnum):
    """Áreas de la propuesta. Fuente única: el CHECK `ck_usuario_area` se deriva de aquí."""

    VENTAS = "ventas"
    FACTURACION = "facturacion"
    TESORERIA = "tesoreria"
    CXC = "cxc"
    CXP = "cxp"
    DIRECCION = "direccion"
    NOMINAS = "nominas"
    ADMIN = "admin"


@dataclass(frozen=True)
class CurrentUser:
    """Usuario resuelto para el request en curso.

    `username` conserva su semántica de F0 (= `nombre_usuario`) porque es lo que se
    escribe en `LogCambioParametro`: cambiarlo alteraría el formato de la bitácora ya
    persistida. `usuario_id` y `email` son NUEVOS en F5-00 y opcionales: el proveedor
    `dev_headers` no tiene un registro de `usuario` detrás y los deja en `None`.
    """

    username: str
    area: Area
    ip: str | None = None
    usuario_id: uuid.UUID | None = None
    email: str | None = None
