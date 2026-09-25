"""Adaptador SES REAL del puerto de correo (ADR-105).

Implementa el MISMO puerto que el adaptador local, usando `boto3` sobre Amazon SES. El
servicio de negocio no distingue entre este adaptador y el local: la selección es por
configuración (`CORREO_BACKEND`, ver `__init__.py`) — mismo criterio que
`AlmacenamientoS3`/ADR-027.

Credenciales: la factory (`get_correo`) las lee de la configuración (`.env` vía
pydantic-settings) y las pasa aquí EXPLÍCITAMENTE, por la misma razón que
`AlmacenamientoS3` (pydantic-settings no exporta a `os.environ`). Si NO se pasan
(qa/producción), boto3 usa su cadena por defecto (rol de instancia / Secrets Manager).

SES no soporta adjuntos en `send_email`: se arma un mensaje MIME (`send_raw_email`), el
mecanismo estándar de boto3 para adjuntar archivos.

Los errores de SES (`ClientError`, problemas de red) se mapean a `CorreoError` con un
mensaje legible; el detalle técnico se REGISTRA en el log, no se filtra al cliente.
"""

from __future__ import annotations

import logging
from typing import Any

from app.integrations.correo.errors import CorreoError
from app.integrations.correo.mime import construir_mime
from app.integrations.correo.port import Adjunto

logger = logging.getLogger(__name__)


def _crear_cliente(region: str, access_key_id: str | None, secret_access_key: str | None) -> Any:
    """Construye un cliente SES.

    Si se reciben `access_key_id`/`secret_access_key`, se pasan EXPLÍCITAMENTE a boto3; si
    no (None/vacías), se omiten para que boto3 use su cadena por defecto (rol de instancia).
    """
    import boto3  # import diferido: solo se necesita cuando el backend SES está activo

    kwargs: dict[str, Any] = {"region_name": region}
    if access_key_id and secret_access_key:
        kwargs["aws_access_key_id"] = access_key_id
        kwargs["aws_secret_access_key"] = secret_access_key
    return boto3.client("ses", **kwargs)


class CorreoSES:
    """Implementación del puerto sobre Amazon SES."""

    def __init__(
        self,
        *,
        region: str,
        from_email: str,
        from_name: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not from_email or not region:
            raise CorreoError("Correo SES mal configurado: falta el remitente o la región.")
        self._from_email = from_email
        self._from_name = from_name
        self._region = region
        # `client` inyectable: las pruebas pasan un cliente falso en memoria (sin red).
        self._client = (
            client
            if client is not None
            else _crear_cliente(region, access_key_id, secret_access_key)
        )

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
            self._client.send_raw_email(
                Source=self._from_email,
                Destinations=destinatarios,
                RawMessage={"Data": mensaje.as_string()},
            )
        except Exception as exc:  # noqa: BLE001 — traducimos cualquier fallo de SES/red
            raise self._error("No se pudo enviar el correo.", exc) from exc

    def _error(self, mensaje: str, exc: Exception) -> CorreoError:
        """Traduce un fallo de SES/red a un error de dominio.

        REGISTRA en el log el detalle REAL de boto3 (tipo, código de error, mensaje, HTTP
        status) para poder diagnosticar; al cliente solo se le devuelve un mensaje
        genérico + el código de SES (no sensible), nunca credenciales ni traceback.
        """
        detalle: dict[str, Any] = {"tipo": type(exc).__name__}

        respuesta = getattr(exc, "response", None)
        if isinstance(respuesta, dict):
            err = respuesta.get("Error", {})
            detalle["codigo_ses"] = err.get("Code")
            detalle["mensaje_ses"] = err.get("Message")
            detalle["http_status"] = respuesta.get("ResponseMetadata", {}).get("HTTPStatusCode")

        logger.error(
            "Fallo de SES: %s | region=%s | %s: %s | detalle=%s",
            mensaje,
            self._region,
            type(exc).__name__,
            exc,
            detalle,
            exc_info=True,
        )
        return CorreoError(mensaje, detalles=detalle)
