"""Tipo compartido para adjuntos de correo (ADR-105).

ADR-145: el sistema ya no envía correo directamente (se retiró "Enviar por correo" —
SES/SMTP/local); lo único que queda de este paquete es la construcción del `.eml`
(`mime.py`), que sigue necesitando este tipo para describir sus adjuntos.
"""

from __future__ import annotations

# Adjunto: (nombre_archivo, contenido, content_type).
Adjunto = tuple[str, bytes, str]
