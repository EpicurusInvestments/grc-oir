"""Adaptador LOCAL del puerto de almacenamiento (sistema de archivos).

Guarda los documentos en una carpeta raíz configurable (`STORAGE_LOCAL_ROOT`, por defecto
`./_storage_local/`), replicando la estructura de S3 (`contratos/<numero_contrato>/`). Es:

- el **backend por defecto** (`STORAGE_BACKEND=local`) para desarrollo sin AWS, y
- el **doble de pruebas** del puerto (las pruebas de servicio/router lo inyectan apuntando
  a un directorio temporal, sin credenciales ni red).

Cumple el MISMO puerto que el adaptador S3, así que el servicio de Contrato no distingue
entre ambos (ADR-027).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.integrations.almacenamiento.documentos import (
    AlmacenamientoError,
    DocumentoAlmacenado,
    sanear_nombre_archivo,
)

RAIZ_CONTRATOS = "contratos"


class AlmacenamientoLocal:
    """Implementación del puerto sobre el sistema de archivos local."""

    def __init__(self, raiz: str | Path = "_storage_local") -> None:
        self._raiz = Path(raiz)

    def prefijo_contrato(self, numero_contrato: str) -> str:
        # El número de contrato se sanea con las mismas reglas de segmento de clave.
        seguro = sanear_nombre_archivo(numero_contrato + ".pdf").removesuffix(".pdf")
        return f"{RAIZ_CONTRATOS}/{seguro}/"

    def listar(self, prefijo: str) -> list[DocumentoAlmacenado]:
        carpeta = self._raiz / prefijo
        if not carpeta.is_dir():
            return []
        docs: list[DocumentoAlmacenado] = []
        for ruta in sorted(carpeta.iterdir()):
            if not ruta.is_file():
                continue
            stat = ruta.stat()
            docs.append(
                DocumentoAlmacenado(
                    nombre=ruta.name,
                    clave=f"{prefijo}{ruta.name}",
                    tamano_bytes=stat.st_size,
                    modificado_en=datetime.fromtimestamp(stat.st_mtime),
                )
            )
        return docs

    def subir(
        self,
        *,
        prefijo: str,
        nombre_archivo: str,
        contenido: bytes,
        content_type: str | None = None,
    ) -> str:
        clave = f"{prefijo}{nombre_archivo}"
        destino = self._raiz / clave
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(contenido)
        except OSError as exc:  # pragma: no cover — error de E/S del entorno local
            raise AlmacenamientoError(
                "No se pudo guardar el documento en el almacenamiento local."
            ) from exc
        return clave

    def obtener(self, clave: str) -> bytes:
        ruta = self._raiz / clave
        try:
            return ruta.read_bytes()
        except FileNotFoundError as exc:
            raise AlmacenamientoError(
                "El documento no existe en el almacenamiento.",
                detalles={"clave": clave},
            ) from exc
        except OSError as exc:  # pragma: no cover
            raise AlmacenamientoError("No se pudo leer el documento.") from exc

    def borrar(self, clave: str) -> None:
        ruta = self._raiz / clave
        try:
            ruta.unlink(missing_ok=True)  # idempotente: borrar lo inexistente no falla
        except OSError as exc:  # pragma: no cover
            raise AlmacenamientoError("No se pudo eliminar el documento.") from exc
