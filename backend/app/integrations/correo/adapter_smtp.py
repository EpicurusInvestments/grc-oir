"""Adaptador SMTP REAL del puerto de correo (ADR-138).

Implementa el MISMO puerto que los otros dos adaptadores (`CorreoLocal`/`CorreoSES`),
hablando SMTP directo (`smtplib` + STARTTLS) en vez de una API — para servidores que
solo exponen un endpoint SMTP, como el punto SMTP de Amazon SES. Las credenciales SMTP
(usuario/password de este adaptador) son un PAR DISTINTO de un access key/secret de IAM:
aunque el usuario tenga formato `AKIA…`, es un usuario SMTP derivado, generado aparte en
la consola de AWS específicamente para autenticación SMTP — no sirve como
`aws_access_key_id` de `CorreoSES`/boto3, ni viceversa.

Los errores de conexión/autenticación/envío se mapean a `CorreoError` con un mensaje
legible; el detalle técnico (excepción real) se REGISTRA en el log, nunca se filtra al
cliente — mismo criterio que `CorreoSES._error`.
"""

from __future__ import annotations

import logging
import smtplib
from typing import Any, Protocol

from app.integrations.correo.errors import CorreoError
from app.integrations.correo.mime import construir_mime
from app.integrations.correo.port import Adjunto

logger = logging.getLogger(__name__)


class _ClienteSmtp(Protocol):
    def login(self, user: str, password: str) -> Any: ...
    def sendmail(self, from_addr: str, to_addrs: list[str], msg: str) -> Any: ...
    def quit(self) -> Any: ...


def _crear_cliente(host: str, port: int) -> _ClienteSmtp:
    """Conexión SMTP nueva con STARTTLS — una por envío (mismo criterio que un mensaje
    SMTP real: transacción corta, no una conexión persistente de larga duración)."""
    cliente = smtplib.SMTP(host, port, timeout=15)
    cliente.starttls()
    return cliente


class CorreoSmtp:
    """Implementación del puerto sobre un servidor SMTP real (STARTTLS, puerto 587 típico)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        from_name: str | None = None,
        cliente_factory: Any = None,
    ) -> None:
        if not host or not user or not password or not from_email:
            raise CorreoError(
                "Correo SMTP mal configurado: falta host, usuario, password o remitente."
            )
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_email = from_email
        self._from_name = from_name
        # Inyectable: las pruebas pasan una fábrica que devuelve un cliente falso en
        # memoria (sin red ni credenciales reales).
        self._cliente_factory = cliente_factory or _crear_cliente

    def enviar(
        self,
        *,
        destinatario: str | list[str],
        asunto: str,
        cuerpo_texto: str,
        adjuntos: list[Adjunto] | None = None,
    ) -> None:
        destinatarios = [destinatario] if isinstance(destinatario, str) else destinatario
        remitente = (
            f"{self._from_name} <{self._from_email}>" if self._from_name else self._from_email
        )
        mensaje = construir_mime(
            remitente=remitente,
            destinatario=destinatarios,
            asunto=asunto,
            cuerpo_texto=cuerpo_texto,
            adjuntos=adjuntos,
        )

        try:
            cliente = self._cliente_factory(self._host, self._port)
            try:
                cliente.login(self._user, self._password)
                cliente.sendmail(self._from_email, destinatarios, mensaje.as_string())
            finally:
                cliente.quit()
        except Exception as exc:  # noqa: BLE001 — traducimos cualquier fallo de SMTP/red
            raise self._error("No se pudo enviar el correo.", exc) from exc

    def _error(self, mensaje: str, exc: Exception) -> CorreoError:
        logger.error(
            "Fallo de SMTP: %s | host=%s:%s | %s: %s",
            mensaje,
            self._host,
            self._port,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return CorreoError(mensaje, detalles={"tipo": type(exc).__name__})
