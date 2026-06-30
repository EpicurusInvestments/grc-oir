"""Auditoría de cambios en parámetros sensibles.

Hook transversal con FIRMA ESTABLE desde la Entrega 1. Los servicios lo llaman DESPUÉS
de cambiar un campo sensible (% comisión, días de crédito, etc.). Así, cuando en F5 se
implemente la tabla `LogCambioParametro`, solo se rellena la persistencia: las llamadas
ya estarán colocadas en los servicios.

Estado F0-00: registra el cambio en el logger de la aplicación (sin persistir).
# TODO(F5): persistir en LogCambioParametro (entidad, entidad_id, campo, valor_anterior,
#           valor_nuevo, usuario, fecha_cambio, ip, motivo_cambio).
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.security import CurrentUser

logger = logging.getLogger("grcoir.audit")


def log_cambio_parametro(
    *,
    entidad: str,
    entidad_id: str,
    campo: str,
    anterior: Any,
    nuevo: Any,
    usuario: CurrentUser,
    motivo: str | None = None,
) -> None:
    """Registra el cambio de un parámetro sensible.

    Cuidado: nunca incluir aquí datos personales/fiscales innecesarios; solo el campo
    auditado y su valor anterior/nuevo.
    """
    logger.info(
        "cambio_parametro entidad=%s id=%s campo=%s anterior=%r nuevo=%r "
        "usuario=%s ip=%s motivo=%s",
        entidad,
        entidad_id,
        campo,
        anterior,
        nuevo,
        usuario.username,
        usuario.ip,
        motivo or "",
    )
    # TODO(F5): repo.crear(LogCambioParametro(...))
