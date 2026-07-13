"""Puerto de almacenamiento de documentos (patrón anti-corrupción).

El dominio (servicios de negocio) depende SOLO de esta interfaz; el adaptador concreto
(S3 real en el futuro, o el local de hoy) se inyecta. Así la subida a S3 se puede activar
sin tocar la capa de negocio.

Estado F0-03: la subida real a S3 está DIFERIDA (no hay bucket/credenciales todavía). El
adaptador local resuelve el **prefijo/carpeta** del contrato en S3
(`contratos/<numero_contrato>/`), pero no sube ni lista archivos reales.
"""

from __future__ import annotations

from typing import Protocol


class AlmacenamientoPort(Protocol):
    """Operaciones de almacenamiento en términos del dominio."""

    def prefijo_contrato(self, numero_contrato: str) -> str:
        """Prefijo/carpeta del contrato en el bucket: `contratos/<numero_contrato>/`."""
        ...

    def listar(self, prefijo: str) -> list[str]:
        """Nombres de archivo bajo un prefijo (vacío mientras S3 no esté configurado)."""
        ...

    def subir(
        self,
        *,
        prefijo: str,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None = None,
    ) -> str:
        """Sube un documento y devuelve su clave. Diferido en F0-03 (ver adaptador local)."""
        ...
