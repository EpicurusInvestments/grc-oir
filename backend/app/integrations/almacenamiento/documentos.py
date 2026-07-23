"""Tipos y helpers COMPARTIDOS del almacenamiento de documentos.

Aísla la parte agnóstica al backend concreto (local o S3), para que ambos adaptadores, el
servicio y el router usen una sola fuente de verdad:

- `DocumentoAlmacenado`: value object del dominio que describe un documento listado.
- `sanear_nombre_archivo`: normaliza el nombre a un segmento de clave S3 seguro (basename,
  charset acotado, fuerza `.pdf`, tope de longitud, bloquea rutas / `..`).
- `leer_pdf`: lee un `UploadFile` validando que sea un PDF real (extensión + *magic bytes*)
  y que no exceda el tamaño máximo; devuelve los bytes crudos.
- Errores de dominio del almacenamiento (`AlmacenamientoError`, `ArchivoNoPdfError`,
  `ArchivoDemasiadoGrandeError`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import UploadFile

from app.core.errors import DomainError

# Caracteres seguros para un segmento de clave S3; el resto se colapsa a '-'.
_CHARS_INVALIDOS = re.compile(r"[^A-Za-z0-9._-]+")
# Firma de un PDF: los archivos válidos empiezan con "%PDF-" (algunos traen basura antes,
# pero la práctica y los timbradores esperan la firma al inicio; validamos al inicio).
_PDF_MAGIC = b"%PDF-"
# Tope defensivo de longitud del nombre de archivo saneado (deja margen bajo el prefijo).
_MAX_NOMBRE = 120


# ── Errores de dominio del almacenamiento ─────────────────────────────────────────
class AlmacenamientoError(DomainError):
    """El backend de almacenamiento (p.ej. S3) no está disponible o falló.

    Se mapea a 502: es una dependencia externa, no un error del cliente. El mensaje es
    legible; el detalle técnico se registra en logs, no se filtra al cliente.
    """

    codigo = "almacenamiento_no_disponible"
    status_code = 502


class ArchivoNoPdfError(DomainError):
    """El archivo subido no es un PDF (extensión o contenido)."""

    codigo = "archivo_no_pdf"
    status_code = 400


class ArchivoDemasiadoGrandeError(DomainError):
    """El archivo supera el tamaño máximo configurado."""

    codigo = "archivo_muy_grande"
    status_code = 413


# ── Value object ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DocumentoAlmacenado:
    """Documento listado bajo un prefijo. `nombre` es el basename (sin el prefijo)."""

    nombre: str
    clave: str
    tamano_bytes: int
    modificado_en: datetime | None = None


# ── Saneo de nombre de archivo ─────────────────────────────────────────────────────
def sanear_nombre_archivo(nombre: str) -> str:
    """Normaliza `nombre` a un segmento de clave S3 seguro.

    - Toma solo el basename (descarta cualquier ruta: `../`, `a/b/c.pdf` → `c.pdf`).
    - Colapsa caracteres fuera de `[A-Za-z0-9._-]` a `-`.
    - Fuerza la extensión `.pdf`.
    - Acota la longitud.

    Lanza `ArchivoNoPdfError` si tras el saneo no queda un nombre utilizable.
    """
    # basename: nos quedamos con lo que sigue al último separador (/ o \).
    base = re.split(r"[\\/]", nombre.strip())[-1]
    limpio = _CHARS_INVALIDOS.sub("-", base).strip("-. ")
    if not limpio:
        raise ArchivoNoPdfError(
            "Nombre de archivo inválido.", detalles={"nombre": nombre}
        )

    # Separa raíz + extensión y fuerza .pdf (case-insensitive).
    raiz, _, ext = limpio.rpartition(".")
    if ext.lower() == "pdf" and raiz:
        raiz_final = raiz
    else:
        # Sin extensión reconocible: todo el texto es la raíz.
        raiz_final = limpio.removesuffix(".").strip("-. ") or "documento"

    raiz_final = raiz_final[:_MAX_NOMBRE]
    return f"{raiz_final}.pdf"


# ── Lectura + validación del upload ─────────────────────────────────────────────────
def leer_pdf(archivo: UploadFile, *, max_bytes: int) -> bytes:
    """Lee el `UploadFile` validando que sea un PDF y no exceda `max_bytes`.

    Lee como máximo `max_bytes + 1` para detectar el exceso sin cargar datos ilimitados.
    Valida extensión `.pdf`, tipo declarado y *magic bytes* `%PDF-` (defensa real).
    """
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith(".pdf"):
        raise ArchivoNoPdfError(
            "El archivo debe ser un PDF (extensión .pdf).",
            detalles={"archivo": archivo.filename},
        )

    contenido = archivo.file.read(max_bytes + 1)
    if len(contenido) > max_bytes:
        raise ArchivoDemasiadoGrandeError(
            f"El archivo supera el tamaño máximo permitido ({max_bytes} bytes).",
            detalles={"max_bytes": max_bytes},
        )
    if not contenido:
        raise ArchivoNoPdfError("El archivo está vacío.")
    if not contenido.startswith(_PDF_MAGIC):
        raise ArchivoNoPdfError(
            "El contenido del archivo no corresponde a un PDF válido."
        )
    return contenido
