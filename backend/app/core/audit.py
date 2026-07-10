"""Auditoría de cambios en parámetros sensibles.

Mecanismo transversal (CLAUDE.md, principio 6): los cambios a campos marcados como
sensibles (% de comisión, días de crédito, etc.) se registran en `LogCambioParametro`
con usuario, fecha, valor anterior/nuevo, ip y motivo.

La FIRMA de estos hooks se fijó en F0-00 para que los servicios ya los llamaran; F0-03 es
el primer consumidor real y **estrena la persistencia**: la tabla `log_cambio_parametro`
existe desde F0-03 (su migración) aunque la PANTALLA de administración de la bitácora
pertenezca a F5 (entidad `LogCambioParametro`).

Transacción: el registro se `add`-iciona a la MISMA sesión del servicio dentro de
`_pre_create`/`_pre_update`; el `commit` del repositorio (que escribe la entidad) lo
persiste de forma atómica junto con el cambio auditado.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Index, Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2
from app.core.errors import DomainError
from app.core.field_permissions import verificar as verificar_permiso_campo
from app.core.security import CurrentUser

logger = logging.getLogger("grcoir.audit")


class LogCambioParametro(Base):
    """Bitácora de cambios a parámetros sensibles.

    Los valores anterior/nuevo se guardan como TEXTO (los campos sensibles son
    heterogéneos: Decimal para %, Integer para días de crédito). La entidad se administra
    en F5; aquí solo se define la tabla y se escribe en ella.
    """

    __tablename__ = "log_cambio_parametro"
    __table_args__ = (
        Index("ix_log_cambio_parametro_entidad", "entidad", "entidad_id"),
    )

    log_cambio_parametro_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    entidad: Mapped[str] = mapped_column(Unicode(60))
    entidad_id: Mapped[str] = mapped_column(Unicode(60))  # UUID como texto (genérico)
    campo: Mapped[str] = mapped_column(Unicode(80))
    valor_anterior: Mapped[str | None] = mapped_column(Unicode(400), default=None)
    valor_nuevo: Mapped[str | None] = mapped_column(Unicode(400), default=None)
    usuario: Mapped[str] = mapped_column(Unicode(150))
    ip: Mapped[str | None] = mapped_column(Unicode(64), default=None)
    motivo_cambio: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    fecha_cambio: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


def _texto(valor: Any) -> str | None:
    """Serializa un valor sensible a texto para la bitácora (sin datos personales)."""
    return None if valor is None else str(valor)


def log_cambio_parametro(
    *,
    db: Session,
    entidad: str,
    entidad_id: Any,
    campo: str,
    anterior: Any,
    nuevo: Any,
    usuario: CurrentUser,
    motivo: str | None = None,
) -> None:
    """Registra el cambio de un parámetro sensible en `LogCambioParametro`.

    Cuidado: nunca incluir aquí datos personales/fiscales innecesarios; solo el campo
    auditado y su valor anterior/nuevo. El registro se agrega a la sesión y se persiste
    con el `commit` del repositorio (misma transacción que el cambio de la entidad).
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
    db.add(
        LogCambioParametro(
            entidad=entidad,
            entidad_id=str(entidad_id),
            campo=campo,
            valor_anterior=_texto(anterior),
            valor_nuevo=_texto(nuevo),
            usuario=usuario.username,
            ip=usuario.ip,
            motivo_cambio=motivo,
        )
    )


def registrar_cambio_sensible(
    *,
    db: Session,
    entidad: str,
    entidad_id: Any,
    campo: str,
    anterior: Any,
    nuevo: Any,
    usuario: CurrentUser,
    motivo: str | None,
    requiere_motivo: bool = True,
) -> None:
    """Mecanismo completo de "parámetro sensible": permiso por campo → motivo → bitácora.

    Llamar SOLO cuando el valor efectivamente cambia (en edición) o en el ALTA con
    `anterior=None`. Orden:

    1. `field_permissions.verificar(...)` → 403 si el usuario no puede editar el campo.
    2. Si `requiere_motivo`, exige `motivo` no vacío → 400 en su ausencia. En el alta se
       llama con `requiere_motivo=False` (no hay "cambio", es la captura inicial).
    3. `log_cambio_parametro(...)` deja la traza en la bitácora.
    """
    verificar_permiso_campo(entidad, campo, usuario)
    if requiere_motivo and not (motivo and motivo.strip()):
        raise DomainError(
            f"Se requiere 'motivo_cambio' para modificar el campo sensible '{campo}'.",
            detalles={"campo": campo},
        )
    log_cambio_parametro(
        db=db,
        entidad=entidad,
        entidad_id=entidad_id,
        campo=campo,
        anterior=anterior,
        nuevo=nuevo,
        usuario=usuario,
        motivo=motivo,
    )
