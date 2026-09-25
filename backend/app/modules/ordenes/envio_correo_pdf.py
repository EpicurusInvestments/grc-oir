"""Envío por correo de los PDFs de OrdenEstacion (ADR-105) — "Orden de servicio",
"Horarios programados" y "Horarios reales", como adjunto al correo que se manda al
contacto de la estación/afiliado (o a quien capture el usuario; la resolución del
destinatario sugerido vive en el frontend, ver `ContactoAfiliado`/`Afiliado.contacto_email`
— este módulo solo recibe el correo ya resuelto).

Reusa los generadores YA existentes de `orden_estacion_pdf.py` (devuelven bytes en
memoria; nada se persiste ahí) — lo único que se agrega aquí es la bitácora
`LogEnvioCorreoOrdenEstacion`: mismo criterio de auditoría que `LogCambioParametro`, pero
en tabla propia (esto no es un cambio de valor de un campo, es el registro de una acción
externa). Un registro por INTENTO, exitoso o no — nunca se borra ni se edita.

ADR-120: además del envío individual de arriba (un PDF, un destinatario capturado a
mano), existe `enviar_correo_orden_transmision` — al generar CUALQUIERA de los 3 PDFs,
la pantalla ofrece "Enviar por correo" (este flujo) o "Imprimir" (abrir el PDF, como
antes). El envío por correo aquí es SIEMPRE el mismo paquete fijo, sin importar qué PDF
disparó el diálogo: asunto "Orden de Transmisión", adjunta el PDF de Programados + TODO
el Material a Transmitir, y se manda automáticamente a los `ContactoAfiliado` activos
con correo cargado del Afiliado dueño de la Estación — no hay captura manual de
destinatario. Reusa la MISMA bitácora (`tipo_pdf="orden_transmision"`, valor nuevo del
CHECK) para no duplicar el historial que el frontend ya muestra.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import CheckConstraint, ForeignKey, Index, Unicode, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db, texto_largo
from app.core.errors import DomainError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.documentos import content_type_de_extension
from app.integrations.almacenamiento.port import AlmacenamientoPort
from app.integrations.correo import CorreoError, get_correo
from app.integrations.correo.port import CorreoPort
from app.modules.catalogos.afiliado import ContactoAfiliado
from app.modules.catalogos.estacion import Estacion
from app.modules.ordenes.orden_estacion import OrdenEstacion, OrdenEstacionAudio
from app.modules.ordenes.orden_estacion_pdf import (
    generar_pdf_programados,
    generar_pdf_reales,
    generar_pdf_servicio,
)

logger = logging.getLogger(__name__)


class TipoPdfOrdenEstacion(StrEnum):
    SERVICIO = "servicio"
    PROGRAMADOS = "programados"
    REALES = "reales"
    # ADR-120: NO es un PDF generable por `_GENERADORES` — solo se usa como valor de
    # `LogEnvioCorreoOrdenEstacion.tipo_pdf` para el envío "bundle" de abajo.
    ORDEN_TRANSMISION = "orden_transmision"


# generador, nombre de archivo, etiqueta legible (para el asunto/cuerpo del correo) — un
# solo lugar para los 3, en vez de repetir el if/elif en el servicio y en el router.
_GeneradorPdf = Callable[[Session, uuid.UUID], bytes]
_GENERADORES: dict[TipoPdfOrdenEstacion, tuple[_GeneradorPdf, str, str]] = {
    TipoPdfOrdenEstacion.SERVICIO: (
        generar_pdf_servicio,
        "orden_de_servicio.pdf",
        "Orden de servicio",
    ),
    TipoPdfOrdenEstacion.PROGRAMADOS: (
        generar_pdf_programados,
        "horarios_programados.pdf",
        "Horarios programados",
    ),
    TipoPdfOrdenEstacion.REALES: (
        generar_pdf_reales,
        "horarios_reales.pdf",
        "Horarios reales de transmisión",
    ),
}


class LogEnvioCorreoOrdenEstacion(Base):
    """Bitácora de envíos por correo de los PDFs de OrdenEstacion."""

    __tablename__ = "log_envio_correo_orden_estacion"
    __table_args__ = (
        CheckConstraint(
            "tipo_pdf IN ('servicio', 'programados', 'reales', 'orden_transmision')",
            name="ck_log_envio_correo_oe_tipo_pdf",
        ),
        Index("ix_log_envio_correo_oe_orden_estacion", "orden_estacion_id"),
    )

    log_envio_correo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_log_envio_correo_oe_orden_estacion",
            ondelete="NO ACTION",
        ),
    )
    tipo_pdf: Mapped[str] = mapped_column(Unicode(20))
    # ADR-120: el envío "bundle" puede ir a VARIOS contactos activos del afiliado — se
    # guarda como lista separada por coma (no se necesita una tabla hija para esto,
    # nunca se filtra por un destinatario individual, solo se muestra en el historial).
    destinatario_email: Mapped[str] = mapped_column(Unicode(2000))
    usuario: Mapped[str] = mapped_column(Unicode(150))
    exitoso: Mapped[bool] = mapped_column()
    mensaje_error: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    fecha_envio: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


class EnvioCorreoIn(BaseModel):
    destinatario_email: EmailStr


class LogEnvioCorreoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_envio_correo_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    tipo_pdf: TipoPdfOrdenEstacion
    destinatario_email: str
    usuario: str
    exitoso: bool
    mensaje_error: str | None = None
    fecha_envio: datetime


def enviar_pdf_orden_estacion_por_correo(
    db: Session,
    orden_estacion_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    data: EnvioCorreoIn,
    usuario: CurrentUser,
    correo: CorreoPort,
) -> LogEnvioCorreoRead:
    """Genera el PDF pedido (mismos generadores del PDF descargable — 400 si la OE no ha
    llegado al sub-estado que ese PDF requiere, p.ej. "reales" antes de 2.3) y lo envía
    por correo como adjunto.

    El intento se registra SIEMPRE que se llegó a intentar el envío (exitoso o no): si
    SES/el adaptador configurado falla, el registro queda con `exitoso=False` y el
    detalle en `mensaje_error`, y el error se relanza (502) para que el cliente lo vea —
    la bitácora no se pierde solo porque el envío falló.
    """
    oe = db.get(OrdenEstacion, orden_estacion_id)
    if oe is None:
        raise NotFoundError(
            "OrdenEstacion no encontrada.", detalles={"orden_estacion_id": str(orden_estacion_id)}
        )
    if tipo not in _GENERADORES:
        raise DomainError(f"Tipo de PDF no soportado para envío individual: {tipo}.")

    generar, nombre_archivo, etiqueta = _GENERADORES[tipo]
    pdf = generar(db, orden_estacion_id)

    asunto = f"{etiqueta} — Orden {oe.folio_orden_estacion}"
    cuerpo = (
        f'Se adjunta el PDF de "{etiqueta}" de la orden {oe.folio_orden_estacion}.\n\n'
        "Este correo fue generado automáticamente por el Sistema GRC-OIR — favor de no "
        "responder a esta dirección."
    )

    exitoso = True
    mensaje_error: str | None = None
    try:
        correo.enviar(
            destinatario=data.destinatario_email,
            asunto=asunto,
            cuerpo_texto=cuerpo,
            adjuntos=[(nombre_archivo, pdf, "application/pdf")],
        )
    except CorreoError as exc:
        exitoso = False
        mensaje_error = exc.mensaje

    log = LogEnvioCorreoOrdenEstacion(
        orden_estacion_id=orden_estacion_id,
        tipo_pdf=tipo.value,
        destinatario_email=data.destinatario_email,
        usuario=usuario.username,
        exitoso=exitoso,
        mensaje_error=mensaje_error,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    if not exitoso:
        raise CorreoError(mensaje_error or "No se pudo enviar el correo.")

    return LogEnvioCorreoRead.model_validate(log)


def enviar_correo_orden_transmision(
    db: Session,
    orden_estacion_id: uuid.UUID,
    usuario: CurrentUser,
    correo: CorreoPort,
    almacenamiento: AlmacenamientoPort,
) -> LogEnvioCorreoRead:
    """ADR-120: envía el paquete FIJO de la Orden de Transmisión — PDF de Programados +
    todo el Material a Transmitir — a los `ContactoAfiliado` activos con correo cargado
    del Afiliado dueño de la Estación de esta OE.

    400 si no hay ningún contacto activo con correo (nunca se intenta enviar "a nadie").
    Mismo criterio de bitácora que el envío individual: un registro por intento, se
    relanza `CorreoError` si falla pero el intento SIEMPRE queda registrado.
    """
    oe = db.get(OrdenEstacion, orden_estacion_id)
    if oe is None:
        raise NotFoundError(
            "OrdenEstacion no encontrada.", detalles={"orden_estacion_id": str(orden_estacion_id)}
        )
    estacion = db.get(Estacion, oe.estacion_id)
    if estacion is None:
        raise NotFoundError(
            "Estación no encontrada para esta OrdenEstacion.",
            detalles={"estacion_id": str(oe.estacion_id)},
        )

    contactos = db.scalars(
        select(ContactoAfiliado).where(
            ContactoAfiliado.afiliado_id == estacion.afiliado_id,
            ContactoAfiliado.activo.is_(True),
        )
    ).all()
    destinatarios = [c.email_contacto for c in contactos if c.email_contacto]
    if not destinatarios:
        raise DomainError(
            "El afiliado de esta estación no tiene contactos activos con correo cargado."
        )

    pdf_programados = generar_pdf_programados(db, orden_estacion_id)
    adjuntos = [("horarios_programados.pdf", pdf_programados, "application/pdf")]

    audios = db.scalars(
        select(OrdenEstacionAudio)
        .where(OrdenEstacionAudio.orden_estacion_id == orden_estacion_id)
        .order_by(OrdenEstacionAudio.orden)
    ).all()
    for audio in audios:
        extension = audio.nombre_archivo.rsplit(".", 1)[-1] if "." in audio.nombre_archivo else ""
        contenido = almacenamiento.obtener(audio.ref)
        adjuntos.append(
            (audio.nombre_archivo, contenido, content_type_de_extension(extension))
        )

    asunto = "Orden de Transmisión"
    cuerpo = (
        f"Se adjuntan el material a transmitir y el PDF de horarios programados de la "
        f"orden {oe.folio_orden_estacion}.\n\n"
        "Este correo fue generado automáticamente por el Sistema GRC-OIR — favor de no "
        "responder a esta dirección."
    )

    exitoso = True
    mensaje_error: str | None = None
    try:
        correo.enviar(
            destinatario=destinatarios,
            asunto=asunto,
            cuerpo_texto=cuerpo,
            adjuntos=adjuntos,
        )
    except CorreoError as exc:
        exitoso = False
        mensaje_error = exc.mensaje

    log = LogEnvioCorreoOrdenEstacion(
        orden_estacion_id=orden_estacion_id,
        tipo_pdf=TipoPdfOrdenEstacion.ORDEN_TRANSMISION.value,
        destinatario_email=", ".join(destinatarios),
        usuario=usuario.username,
        exitoso=exitoso,
        mensaje_error=mensaje_error,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    if not exitoso:
        raise CorreoError(mensaje_error or "No se pudo enviar el correo.")

    return LogEnvioCorreoRead.model_validate(log)


def listar_envios_correo(db: Session, orden_estacion_id: uuid.UUID) -> list[LogEnvioCorreoRead]:
    """Historial de envíos de UNA OrdenEstacion, del más reciente al más antiguo."""
    stmt = (
        select(LogEnvioCorreoOrdenEstacion)
        .where(LogEnvioCorreoOrdenEstacion.orden_estacion_id == orden_estacion_id)
        .order_by(LogEnvioCorreoOrdenEstacion.fecha_envio.desc())
    )
    return [LogEnvioCorreoRead.model_validate(r) for r in db.scalars(stmt).all()]


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/estaciones", tags=["ordenes:estaciones:correo"])


@router.post("/{item_id}/pdf/{tipo}/enviar-correo", response_model=LogEnvioCorreoRead)
def enviar_pdf_correo_orden_estacion(
    item_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    payload: EnvioCorreoIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    db: Session = Depends(get_db),
    correo: CorreoPort = Depends(get_correo),
) -> LogEnvioCorreoRead:
    """Envía el PDF `tipo` (servicio/programados/reales) al correo indicado. Body:
    `{destinatario_email}`. 400 si la OE no ha llegado al sub-estado que ese PDF
    requiere; 502 si el correo no se pudo enviar (queda registrado en la bitácora de
    todos modos)."""
    return enviar_pdf_orden_estacion_por_correo(db, item_id, tipo, payload, usuario, correo)


@router.post("/{item_id}/correo-orden-transmision", response_model=LogEnvioCorreoRead)
def enviar_correo_orden_transmision_endpoint(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    db: Session = Depends(get_db),
    correo: CorreoPort = Depends(get_correo),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> LogEnvioCorreoRead:
    """ADR-120: envía el PDF de Programados + todo el Material a Transmitir a los
    contactos activos (con correo) del afiliado de la estación — sin body, sin
    destinatario capturado a mano. 400 si el afiliado no tiene ningún contacto activo
    con correo cargado; 502 si el correo no se pudo enviar (queda igual registrado en
    la bitácora)."""
    return enviar_correo_orden_transmision(db, item_id, usuario, correo, almacenamiento)


@router.get("/{item_id}/envios-correo", response_model=list[LogEnvioCorreoRead])
def listar_envios_correo_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    db: Session = Depends(get_db),
) -> list[LogEnvioCorreoRead]:
    """Historial de envíos por correo de esta OE (los 3 tipos de PDF mezclados,
    ordenados del más reciente al más antiguo)."""
    return listar_envios_correo(db, item_id)
