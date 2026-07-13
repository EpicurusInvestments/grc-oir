"""Adaptador LOCAL del puerto de almacenamiento (F0-03).

Resuelve el prefijo del contrato siguiendo la estructura acordada en S3
(`contratos/<numero_contrato>/`), pero NO sube ni lista archivos reales: la integración
con S3 está **diferida** a una tarea posterior (falta el bucket `S3_BUCKET_CONTRATOS` y las
credenciales; ver `.env.example` y la ficha f0-03). Cuando exista, se añadirá un
`AlmacenamientoS3` que implemente el mismo puerto y se cambiará solo la inyección.
"""

from __future__ import annotations

import re

from app.core.errors import DomainError

RAIZ_CONTRATOS = "contratos"
# Caracteres seguros para un segmento de clave S3; el resto se colapsa a '-'.
_CHARS_INVALIDOS = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(valor: str) -> str:
    return _CHARS_INVALIDOS.sub("-", valor.strip()).strip("-")


class AlmacenamientoLocal:
    """Implementación del puerto sin backend real (subida diferida)."""

    def prefijo_contrato(self, numero_contrato: str) -> str:
        return f"{RAIZ_CONTRATOS}/{_slug(numero_contrato)}/"

    def listar(self, prefijo: str) -> list[str]:
        # Sin S3 configurado: aún no hay documentos que listar.
        return []

    def subir(
        self,
        *,
        prefijo: str,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None = None,
    ) -> str:
        raise DomainError(
            "La subida de documentos de contrato está diferida: falta configurar el bucket "
            "de S3 (S3_BUCKET_CONTRATOS) y las credenciales.",
            detalles={"prefijo": prefijo, "archivo": nombre_archivo},
        )
