"""Puerto de almacenamiento de documentos (patrón anti-corrupción).

El dominio (servicios de negocio) depende SOLO de esta interfaz; el adaptador concreto
(S3 real o el local de sistema de archivos) se inyecta por configuración. Así la subida a
S3 se activa sin tocar la capa de negocio (ADR-020 → implementada en ADR-027).

Operaciones en términos del dominio:
- `prefijo_contrato`: carpeta del contrato en el bucket (`contratos/<numero_contrato>/`).
- `listar`: documentos bajo un prefijo (metadata mínima: nombre, clave, tamaño, fecha).
- `subir`: sube un documento y devuelve su clave.
- `obtener`: descarga los bytes de un documento por su clave.
- `borrar`: elimina un documento por su clave.
"""

from __future__ import annotations

from typing import Protocol

from app.integrations.almacenamiento.documentos import DocumentoAlmacenado


class AlmacenamientoPort(Protocol):
    """Operaciones de almacenamiento en términos del dominio."""

    def prefijo_contrato(self, numero_contrato: str) -> str:
        """Prefijo/carpeta del contrato en el bucket: `contratos/<numero_contrato>/`."""
        ...

    def listar(self, prefijo: str) -> list[DocumentoAlmacenado]:
        """Documentos bajo un prefijo (lista vacía si no hay ninguno)."""
        ...

    def subir(
        self,
        *,
        prefijo: str,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None = None,
    ) -> str:
        """Sube un documento bajo el prefijo y devuelve su clave completa."""
        ...

    def obtener(self, clave: str) -> bytes:
        """Descarga los bytes del documento identificado por `clave`."""
        ...

    def borrar(self, clave: str) -> None:
        """Elimina el documento identificado por `clave` (idempotente)."""
        ...
