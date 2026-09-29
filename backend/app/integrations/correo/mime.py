"""Construcción del mensaje MIME (asunto, cuerpo, adjuntos) — compartida por `CorreoSES`
(lo manda de verdad) y `CorreoLocal` (ADR-122: lo guarda como `.eml` en disco, para poder
revisar cómo quedó armado el mensaje SIN enviar nada real ni depender de SES/AWS).
"""

from __future__ import annotations

from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from app.integrations.correo.port import Adjunto


def construir_mime(
    *,
    remitente: str,
    destinatario: str | list[str],
    asunto: str,
    cuerpo_texto: str,
    adjuntos: list[Adjunto] | None = None,
    como_borrador: bool = False,
) -> MIMEMultipart:
    """`como_borrador=True` (ADR-144, solo usado por `generar_eml_orden_transmision`):
    agrega `X-Unsent: 1` — encabezado no estándar pero respetado por Outlook (y otros
    clientes de escritorio) para decidir CÓMO abrir un `.eml` suelto: con él presente,
    lo abre en una ventana de mensaje NUEVO editable (con "Enviar"), no en modo lectura
    como un correo recibido. Contradice lo que ADR-124 había concluido ("límite fijo,
    el contenido del archivo no lo puede cambiar") — esa conclusión se hizo sin conocer
    este encabezado. Nunca se activa en los adaptadores de envío real (SES/SMTP/Local):
    ahí el mensaje si se manda/guarda de verdad, así que "no enviado" sería incorrecto.
    """
    destinatarios = [destinatario] if isinstance(destinatario, str) else destinatario
    mensaje = MIMEMultipart()
    mensaje["Subject"] = asunto
    mensaje["From"] = remitente
    mensaje["To"] = ", ".join(destinatarios)
    # RFC 5322 las pide en cualquier correo bien formado — sin ellas, algunos clientes
    # (Outlook Web confirmado) no logran adjuntar/incrustar el mensaje original al
    # reenviarlo desde un ".eml" suelto (no es parte de un buzón real) y fallan al
    # guardarlo/enviarlo.
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid()
    if como_borrador:
        mensaje["X-Unsent"] = "1"
    mensaje.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
    for nombre_archivo, contenido, content_type in adjuntos or []:
        subtipo = content_type.split("/", 1)[-1] if "/" in content_type else "octet-stream"
        adjunto = MIMEApplication(contenido, _subtype=subtipo)
        adjunto.add_header("Content-Disposition", "attachment", filename=nombre_archivo)
        mensaje.attach(adjunto)
    return mensaje
