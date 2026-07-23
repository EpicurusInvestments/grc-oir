"""Adaptador S3 REAL del puerto de almacenamiento (ADR-027).

Implementa el MISMO puerto que el adaptador local usando `boto3` sobre un bucket PRIVADO.
El servicio de Contrato no distingue entre este adaptador y el local: la selección es por
configuración (`STORAGE_BACKEND`, ver `__init__.py`).

Credenciales: la factory (`get_almacenamiento`) las lee de la configuración (`.env` vía
pydantic-settings, que además les quita las comillas) y las pasa aquí EXPLÍCITAMENTE. Esto
es necesario porque pydantic-settings NO exporta a `os.environ`, así que el `.env` por sí
solo no alimenta la cadena de proveedores de boto3 (causaba `NoCredentialsError`). Si NO se
pasan credenciales (qa/producción), boto3 usa su **cadena por defecto**: rol de instancia /
AWS Secrets Manager. Nunca se hardcodean en el código. Ver ADR-027.

Los errores de S3 (`ClientError`, problemas de red) se mapean a `AlmacenamientoError` con
un mensaje legible; el detalle técnico se REGISTRA en el log, no se filtra al cliente.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, cast

from app.integrations.almacenamiento.documentos import (
    AlmacenamientoError,
    DocumentoAlmacenado,
)

logger = logging.getLogger(__name__)


def _crear_cliente(
    region: str, access_key_id: str | None, secret_access_key: str | None
) -> Any:
    """Construye un cliente S3.

    Si se reciben `access_key_id`/`secret_access_key`, se pasan EXPLÍCITAMENTE a boto3; si
    no (None/vacías), se omiten para que boto3 use su cadena por defecto (rol de instancia).
    """
    import boto3  # import diferido: solo se necesita cuando el backend S3 está activo

    kwargs: dict[str, Any] = {"region_name": region}
    if access_key_id and secret_access_key:
        kwargs["aws_access_key_id"] = access_key_id
        kwargs["aws_secret_access_key"] = secret_access_key
    return boto3.client("s3", **kwargs)


class AlmacenamientoS3:
    """Implementación del puerto sobre Amazon S3 (bucket privado)."""

    RAIZ_CONTRATOS = "contratos"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket or not region:
            raise AlmacenamientoError(
                "Almacenamiento S3 mal configurado: falta el bucket o la región."
            )
        self._bucket = bucket
        self._region = region
        # `client` inyectable: las pruebas pasan un cliente falso en memoria (sin red).
        self._client = (
            client
            if client is not None
            else _crear_cliente(region, access_key_id, secret_access_key)
        )

    # NOTA: el saneo del número/nombre es responsabilidad del servicio (documentos.py); aquí
    # solo componemos la clave. Se replica el mismo saneo del número que el adaptador local.
    def prefijo_contrato(self, numero_contrato: str) -> str:
        from app.integrations.almacenamiento.documentos import sanear_nombre_archivo

        seguro = sanear_nombre_archivo(numero_contrato + ".pdf").removesuffix(".pdf")
        return f"{self.RAIZ_CONTRATOS}/{seguro}/"

    def listar(self, prefijo: str) -> list[DocumentoAlmacenado]:
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            docs: list[DocumentoAlmacenado] = []
            for pagina in paginator.paginate(Bucket=self._bucket, Prefix=prefijo):
                for obj in pagina.get("Contents", []):
                    clave = obj["Key"]
                    nombre = clave[len(prefijo):]
                    if not nombre:  # el "objeto carpeta" (clave == prefijo) se ignora
                        continue
                    modificado = obj.get("LastModified")
                    docs.append(
                        DocumentoAlmacenado(
                            nombre=nombre,
                            clave=clave,
                            tamano_bytes=int(obj.get("Size", 0)),
                            modificado_en=(
                                modificado if isinstance(modificado, datetime) else None
                            ),
                        )
                    )
            return docs
        except Exception as exc:  # noqa: BLE001 — traducimos cualquier fallo de S3/red
            raise self._error("No se pudieron listar los documentos.", exc) from exc

    def subir(
        self,
        *,
        prefijo: str,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None = None,
    ) -> str:
        clave = f"{prefijo}{nombre_archivo}"
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=clave,
                Body=contenido,
                ContentType=content_type or "application/pdf",
            )
        except Exception as exc:  # noqa: BLE001
            raise self._error("No se pudo subir el documento.", exc) from exc
        return clave

    def obtener(self, clave: str) -> bytes:
        try:
            respuesta = self._client.get_object(Bucket=self._bucket, Key=clave)
            return cast(bytes, respuesta["Body"].read())
        except Exception as exc:  # noqa: BLE001
            raise self._error("No se pudo obtener el documento.", exc) from exc

    def borrar(self, clave: str) -> None:
        try:
            # delete_object es idempotente en S3 (borrar lo inexistente no falla).
            self._client.delete_object(Bucket=self._bucket, Key=clave)
        except Exception as exc:  # noqa: BLE001
            raise self._error("No se pudo eliminar el documento.", exc) from exc

    def _error(self, mensaje: str, exc: Exception) -> AlmacenamientoError:
        """Traduce un fallo de S3/red a un error de dominio.

        REGISTRA en el log el detalle REAL de boto3 (tipo, código de error de S3, mensaje,
        HTTP status) para poder diagnosticar; al cliente solo se le devuelve un mensaje
        genérico + el código de S3 (no sensible), nunca las credenciales ni el traceback.
        """
        detalle: dict[str, Any] = {"tipo": type(exc).__name__}

        # botocore.ClientError expone response["Error"] con Code/Message y el HTTP status.
        respuesta = getattr(exc, "response", None)
        if isinstance(respuesta, dict):
            err = respuesta.get("Error", {})
            detalle["codigo_s3"] = err.get("Code")
            detalle["mensaje_s3"] = err.get("Message")
            detalle["http_status"] = respuesta.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )

        logger.error(
            "Fallo de S3: %s | bucket=%s region=%s | %s: %s | detalle=%s",
            mensaje,
            self._bucket,
            self._region,
            type(exc).__name__,
            exc,
            detalle,
            exc_info=True,  # incluye el traceback completo de boto3 en el log
        )
        return AlmacenamientoError(mensaje, detalles=detalle)
