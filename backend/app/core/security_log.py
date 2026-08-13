"""Log de eventos de seguridad (F5-00 — versión mínima).

Deja traza de acciones sensibles que **no** pertenecen a `LogCambioParametro`: esa tabla
guarda el valor anterior/nuevo de parámetros de negocio y se consulta desde el panel de
detalle de las entidades; un reseteo de contraseña no tiene "valores" que mostrar ahí.

Hoy escribe al log de la aplicación. La bitácora de seguridad **formal** —tabla
consultable, retención, pantalla de auditoría— es de **F5 pleno**. Este módulo es la
COSTURA para ese cambio: los servicios llaman a `registrar_evento_seguridad(...)` y el día
que exista la tabla se reescribe el cuerpo de esta función, no los llamadores.

Regla que no se negocia (CLAUDE.md §7): **nunca** se registra la contraseña, ni el hash, ni
datos personales innecesarios. Se registra QUIÉN hizo QUÉ, A QUIÉN y CUÁNDO (la marca de
tiempo la pone el propio logging).
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from app.core.auth.identity import CurrentUser

logger = logging.getLogger("grcoir.seguridad")


class EventoSeguridad(StrEnum):
    """Catálogo de eventos. Crece conforme F5 añada acciones que valga la pena rastrear."""

    PASSWORD_ESTABLECIDA = "password_establecida"


def registrar_evento_seguridad(
    *,
    evento: EventoSeguridad,
    actor: CurrentUser,
    objetivo: str | None = None,
    objetivo_id: Any | None = None,
    detalle: str | None = None,
) -> None:
    """Registra un evento de seguridad.

    Args:
        evento: qué ocurrió (`EventoSeguridad`).
        actor: usuario autenticado que ejecutó la acción (de ahí salen usuario e IP).
        objetivo: identificador legible de sobre quién/qué se actuó (p.ej. `nombre_usuario`).
            NO se pasa el email ni otros datos personales: para identificar de forma
            inequívoca está `objetivo_id`.
        objetivo_id: id del registro afectado.
        detalle: contexto adicional, siempre NO sensible.
    """
    logger.info(
        "evento_seguridad=%s actor=%s actor_id=%s ip=%s objetivo=%s objetivo_id=%s detalle=%s",
        evento.value,
        actor.username,
        actor.usuario_id,
        actor.ip,
        objetivo,
        objetivo_id,
        detalle or "",
    )
