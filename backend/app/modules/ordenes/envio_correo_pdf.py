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
antes). ADR-126 corrigió el diseño original de ADR-120 (que mandaba SIEMPRE el PDF de
Programados sin importar qué botón disparó el diálogo): ahora cada uno de los 3 botones
manda SU PROPIO PDF (servicio/programados/reales) + TODO el Material a Transmitir (si
la OE tiene) — no hay captura manual de destinatario. ADR-140: el destinatario depende
del `tipo` — Servicio/Reales van a los `ContactoAnunciante` activos del ANUNCIANTE;
Programados va a los `ContactoAfiliado` activos del AFILIADO dueño de la Estación.
Reusa la MISMA bitácora que el envío individual (`tipo_pdf` = el tipo real enviado).
"""

from __future__ import annotations

import email.policy
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import APIRouter, Depends, Response
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
from app.integrations.correo.mime import construir_mime
from app.integrations.correo.port import Adjunto, CorreoPort
from app.modules.catalogos.afiliado import ContactoAfiliado
from app.modules.catalogos.anunciante import ContactoAnunciante
from app.modules.catalogos.estacion import Estacion
from app.modules.ordenes.orden_estacion import OrdenEstacion, OrdenEstacionAudio
from app.modules.ordenes.orden_estacion_pdf import (
    generar_pdf_programados,
    generar_pdf_reales,
    generar_pdf_servicio,
)
from app.modules.usuarios.lookup import resolver_usuario_email

logger = logging.getLogger(__name__)


class TipoPdfOrdenEstacion(StrEnum):
    SERVICIO = "servicio"
    PROGRAMADOS = "programados"
    REALES = "reales"
    # ADR-120: NO es un PDF generable por `_GENERADORES`. Ya no se escribe en registros
    # nuevos de `LogEnvioCorreoOrdenEstacion.tipo_pdf` (ADR-126 corrigió el bundle para
    # que use el tipo real servicio/programados/reales) — se conserva solo para poder
    # leer bitácora histórica generada bajo el diseño original de ADR-120.
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
    # ADR-120/ADR-140: el envío "bundle" puede ir a VARIOS contactos activos (del
    # anunciante o del afiliado, según `tipo_pdf`) — se guarda como lista separada por
    # coma (no se necesita una tabla hija para esto, nunca se filtra por un destinatario
    # individual, solo se muestra en el historial).
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


def _armar_paquete_orden_transmision(
    db: Session,
    orden_estacion_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    almacenamiento: AlmacenamientoPort,
) -> tuple[OrdenEstacion, list[str], str, str, list[Adjunto]]:
    """Resuelve destinatarios + arma el paquete de la Orden de Transmisión — el PDF que
    corresponde a `tipo` (servicio/programados/reales) + TODO el Material a Transmitir,
    si la OE tiene.

    ADR-140 (petición del usuario): el destinatario depende del `tipo`, no es siempre el
    mismo — Servicio y Reales van a los `ContactoAnunciante` activos con correo cargado
    del ANUNCIANTE (quien contrató la pauta); Programados va a los `ContactoAfiliado`
    activos con correo cargado del AFILIADO dueño de la Estación (quien transmite).

    ADR-126 (corrección del usuario): ADR-120 mandaba SIEMPRE el PDF de Programados sin
    importar qué de los 3 botones disparó el diálogo — eso estaba mal; cada botón debe
    adjuntar SU PROPIO PDF. Mismo gateo por sub-estado que la descarga individual del
    PDF (p.ej. "reales" antes de 2.3 → 400, vía `_GENERADORES`).

    Compartido por `enviar_correo_orden_transmision` (lo manda por SES/local) y
    `generar_eml_orden_transmision` (ADR-124: lo entrega como `.eml` para que el usuario
    lo abra con su propio cliente de correo). 400 si no hay ningún contacto activo con
    correo (nunca se prepara un envío "a nadie").
    """
    oe = db.get(OrdenEstacion, orden_estacion_id)
    if oe is None:
        raise NotFoundError(
            "OrdenEstacion no encontrada.", detalles={"orden_estacion_id": str(orden_estacion_id)}
        )
    if tipo not in _GENERADORES:
        raise DomainError(f"Tipo de PDF no soportado: {tipo}.")

    if tipo == TipoPdfOrdenEstacion.PROGRAMADOS:
        estacion = db.get(Estacion, oe.estacion_id)
        if estacion is None:
            raise NotFoundError(
                "Estación no encontrada para esta OrdenEstacion.",
                detalles={"estacion_id": str(oe.estacion_id)},
            )
        contactos_afiliado = db.scalars(
            select(ContactoAfiliado).where(
                ContactoAfiliado.afiliado_id == estacion.afiliado_id,
                ContactoAfiliado.activo.is_(True),
            )
        ).all()
        destinatarios = [c.email_contacto for c in contactos_afiliado if c.email_contacto]
        if not destinatarios:
            raise DomainError(
                "El afiliado de esta estación no tiene contactos activos con correo cargado."
            )
    else:
        contactos_anunciante = db.scalars(
            select(ContactoAnunciante).where(
                ContactoAnunciante.anunciante_id == oe.anunciante_id,
                ContactoAnunciante.activo.is_(True),
            )
        ).all()
        destinatarios = [c.email_contacto for c in contactos_anunciante if c.email_contacto]
        if not destinatarios:
            raise DomainError(
                "El anunciante de esta orden no tiene contactos activos con correo cargado."
            )

    generar, nombre_archivo, etiqueta = _GENERADORES[tipo]
    pdf = generar(db, orden_estacion_id)
    adjuntos: list[Adjunto] = [(nombre_archivo, pdf, "application/pdf")]

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
        f'Se adjunta el PDF de "{etiqueta}"'
        f'{" y el material a transmitir" if audios else ""} de la orden '
        f"{oe.folio_orden_estacion}.\n\n"
        "Este correo fue generado automáticamente por el Sistema GRC-OIR — favor de no "
        "responder a esta dirección."
    )
    return oe, destinatarios, asunto, cuerpo, adjuntos


def enviar_correo_orden_transmision(
    db: Session,
    orden_estacion_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    usuario: CurrentUser,
    correo: CorreoPort,
    almacenamiento: AlmacenamientoPort,
) -> LogEnvioCorreoRead:
    """ADR-120/ADR-126: envía el PDF `tipo` (+ Material a Transmitir, si tiene) por
    SES/local — ver `_armar_paquete_orden_transmision`. Mismo criterio de bitácora que
    el envío individual: un registro por intento, se relanza `CorreoError` si falla pero
    el intento SIEMPRE queda registrado.
    """
    _oe, destinatarios, asunto, cuerpo, adjuntos = _armar_paquete_orden_transmision(
        db, orden_estacion_id, tipo, almacenamiento
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
        tipo_pdf=tipo.value,
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


def generar_eml_orden_transmision(
    db: Session,
    orden_estacion_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    usuario: CurrentUser,
    almacenamiento: AlmacenamientoPort,
) -> tuple[bytes, str]:
    """ADR-124/ADR-126/ADR-144 (petición del usuario): arma el MISMO paquete que
    `enviar_correo_orden_transmision` para el PDF `tipo` (mismos
    destinatarios/asunto/adjuntos), pero en vez de mandarlo por SES/local, devuelve el
    archivo `.eml` crudo (con `X-Unsent`, ver `construir_mime`) para que el propio
    usuario lo abra con su cliente de correo de escritorio (Outlook, etc.) — ahí lo abre
    DIRECTO como un mensaje nuevo editable, con "Para"/asunto/adjuntos ya resueltos, y lo
    manda él mismo desde su propia cuenta (útil mientras SES no esté en producción,
    ADR-105/122).

    Se registra en la MISMA bitácora que el envío automático (mismo criterio: se preparó
    el paquete para estos destinatarios), aunque el envío real lo haga el cliente de
    correo del usuario, no este sistema — por eso siempre queda `exitoso=True` (armar el
    archivo no puede "fallar" como sí puede fallar una llamada real a SES).

    ADR-125 probó anteponer los destinatarios como texto en el cuerpo (para copiar/pegar
    en "Para" tras "Reenviar" — ver esa entrada para el porqué) — se quitó a petición del
    usuario; el cuerpo queda igual que el del envío automático.

    ADR-137 (corrección de revisión del equipo): el remitente sale del `Usuario` con la
    sesión abierta (`resolver_usuario_email`), nunca de un valor fijo en el código —
    aunque en la práctica Outlook/el cliente de escritorio siempre sustituye el "De" del
    borrador nuevo por la cuenta propia configurada en esa máquina sin importar lo que
    traiga el archivo (confirmado ADR-124), así que este campo es sobre todo para que el
    `.eml` crudo quede correcto, no cambia a quién ve el destinatario final como
    remitente.
    """
    oe, destinatarios, asunto, cuerpo, adjuntos = _armar_paquete_orden_transmision(
        db, orden_estacion_id, tipo, almacenamiento
    )
    remitente = resolver_usuario_email(db, usuario.username)
    mensaje = construir_mime(
        remitente=remitente,
        destinatario=destinatarios,
        asunto=asunto,
        cuerpo_texto=cuerpo,
        adjuntos=adjuntos,
        como_borrador=True,
    )

    log = LogEnvioCorreoOrdenEstacion(
        orden_estacion_id=orden_estacion_id,
        tipo_pdf=tipo.value,
        destinatario_email=", ".join(destinatarios),
        usuario=usuario.username,
        exitoso=True,
        mensaje_error=None,
    )
    db.add(log)
    db.commit()

    nombre_archivo = f"orden_transmision_{tipo.value}_{oe.folio_orden_estacion}.eml"
    # `as_bytes()` sin política usa LF ("\n") — inválido para RFC 5322 (exige CRLF) y
    # causa que clientes de escritorio (Outlook confirmado: "posible que este mensaje se
    # haya movido o eliminado", con "(Sin asunto)") no logren parsear el archivo. La
    # política SMTP genera con "\r\n" — es la sesión REAL, aunque el destino sea disco.
    return mensaje.as_bytes(policy=email.policy.SMTP), nombre_archivo


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


@router.post(
    "/{item_id}/pdf/{tipo}/correo-orden-transmision", response_model=LogEnvioCorreoRead
)
def enviar_correo_orden_transmision_endpoint(
    item_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    db: Session = Depends(get_db),
    correo: CorreoPort = Depends(get_correo),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> LogEnvioCorreoRead:
    """ADR-120/ADR-126/ADR-140: envía el PDF `tipo` (servicio/programados/reales) + todo
    el Material a Transmitir a los contactos activos (con correo) del ANUNCIANTE
    (servicio/reales) o del AFILIADO de la estación (programados) — sin body, sin
    destinatario capturado a mano. 400 si la OE no ha llegado al sub-estado que ese PDF
    requiere, o si no hay ningún contacto activo con correo cargado del lado que
    corresponda; 502 si el correo no se pudo enviar (queda igual registrado en la
    bitácora)."""
    return enviar_correo_orden_transmision(db, item_id, tipo, usuario, correo, almacenamiento)


@router.post("/{item_id}/pdf/{tipo}/correo-orden-transmision/eml")
def descargar_eml_orden_transmision_endpoint(
    item_id: uuid.UUID,
    tipo: TipoPdfOrdenEstacion,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    db: Session = Depends(get_db),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> Response:
    """ADR-124/ADR-126/ADR-140/ADR-144: arma el paquete del PDF `tipo` (+ Material a
    Transmitir, destinatarios = contactos activos del anunciante o del afiliado, según
    `tipo`) y regresa el archivo `.eml` crudo (con `X-Unsent`) para que el usuario lo
    abra con su cliente de correo de escritorio (Outlook, etc.) — ahí lo abre DIRECTO
    como un mensaje nuevo editable, con todo ya adjunto, y lo manda él mismo. 400 si la
    OE no ha llegado al sub-estado que ese PDF requiere, o si no hay ningún contacto
    activo con correo cargado del lado que corresponda."""
    contenido, nombre_archivo = generar_eml_orden_transmision(
        db, item_id, tipo, usuario, almacenamiento
    )
    return Response(
        content=contenido,
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/{item_id}/envios-correo", response_model=list[LogEnvioCorreoRead])
def listar_envios_correo_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    db: Session = Depends(get_db),
) -> list[LogEnvioCorreoRead]:
    """Historial de envíos por correo de esta OE (los 3 tipos de PDF mezclados,
    ordenados del más reciente al más antiguo)."""
    return listar_envios_correo(db, item_id)
