"""Importación masiva desde CSV — helper REUTILIZABLE por catálogos (F0-05).

Aísla la parte MECÁNICA y agnóstica al dominio de una carga masiva:
- Lectura del archivo subido con tope de tamaño (procesado en memoria; NUNCA se persiste).
- Decodificación UTF-8 (tolera BOM) y parseo CSV (sniff de delimitador `,`/`;`).
- Validación ESTRUCTURAL (columnas requeridas, archivo vacío, no-UTF-8, exceso de tamaño/
  filas) → aborta con error de dominio (nada se aplica).

La validación POR FILA (tipos/enum del catálogo) y la política de duplicados (upsert/omitir/
rechazar) las pone cada catálogo en su capa de servicio; este módulo solo entrega las filas
crudas ya recortadas y numeradas, y define los tipos del REPORTE (comunes a toda importación).

Patrón acordado (plan F0-05, sección C): flujo *dry-run → confirmar*, stateless (el cliente
re-sube el mismo archivo con `commit=true`); import PARCIAL (filas válidas entran, inválidas
se reportan con motivo); aplicación ATÓMICA del subconjunto válido (responsabilidad del
servicio). Sin pandas: solo `csv`/`io` de la stdlib + `python-multipart` para el upload.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from enum import StrEnum

from fastapi import UploadFile
from pydantic import BaseModel

from app.core.errors import DomainError


# ── Errores estructurales (abortan toda la importación) ───────────────────────────
class ImportacionArchivoError(DomainError):
    """Problema estructural del archivo: nada se aplica (columnas, vacío, no-UTF-8, tipo)."""

    codigo = "archivo_invalido"
    status_code = 400


class ArchivoDemasiadoGrandeError(DomainError):
    """El archivo supera el tope de bytes o de filas configurado."""

    codigo = "archivo_muy_grande"
    status_code = 413


# ── Tipos del reporte (comunes a cualquier importación) ───────────────────────────
class ModoDuplicados(StrEnum):
    ACTUALIZAR = "actualizar"  # upsert (default): actualiza el registro existente
    OMITIR = "omitir"  # deja el existente sin cambios y no cuenta como error
    RECHAZAR = "rechazar"  # trata el duplicado como fila inválida


class EstadoFila(StrEnum):
    CREADA = "creada"
    ACTUALIZADA = "actualizada"
    OMITIDA = "omitida"
    RECHAZADA = "rechazada"


class FilaResultado(BaseModel):
    numero: int  # número de fila de datos en el CSV (1-based, sin contar el encabezado)
    grupo: str | None = None
    clave: str | None = None
    estado: EstadoFila
    motivo: str | None = None


class ResultadoImportacion(BaseModel):
    commit: bool  # false = previsualización (no se escribió nada); true = aplicado
    total_filas: int
    creadas: int
    actualizadas: int
    omitidas: int
    rechazadas: int
    errores_estructura: list[str]  # vacío en el camino normal (los estructurales abortan 400)
    filas: list[FilaResultado]


# ── Fila cruda entregada al servicio ─────────────────────────────────────────────
@dataclass
class FilaCruda:
    numero: int
    datos: dict[str, str]  # columna (en minúsculas) → valor recortado


# ── Lectura del upload (tamaño + tipo) ────────────────────────────────────────────
def leer_upload(archivo: UploadFile, *, max_bytes: int) -> bytes:
    """Lee el archivo subido validando extensión y tamaño. Devuelve los bytes crudos.

    Lee como máximo `max_bytes + 1` para detectar el exceso sin cargar datos ilimitados.
    """
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith(".csv"):
        raise ImportacionArchivoError(
            "El archivo debe ser un CSV (extensión .csv).",
            detalles={"archivo": archivo.filename},
        )
    contenido = archivo.file.read(max_bytes + 1)
    if len(contenido) > max_bytes:
        raise ArchivoDemasiadoGrandeError(
            f"El archivo supera el tamaño máximo permitido ({max_bytes} bytes).",
            detalles={"max_bytes": max_bytes},
        )
    if not contenido:
        raise ImportacionArchivoError("El archivo está vacío.")
    return contenido


# ── Parseo + validación estructural ───────────────────────────────────────────────
def parsear_csv(
    contenido: bytes,
    *,
    columnas_requeridas: list[str],
    columnas_opcionales: list[str] | None = None,
    max_filas: int,
) -> list[FilaCruda]:
    """Decodifica, detecta el delimitador y parsea el CSV a filas crudas recortadas.

    Valida la ESTRUCTURA (aborta con error de dominio si falla):
    - no decodifica como UTF-8 (tolera BOM),
    - archivo sin encabezado,
    - faltan columnas requeridas,
    - excede el número máximo de filas.

    Los encabezados se normalizan a minúsculas/recortados; las columnas no declaradas se
    ignoran. Las líneas totalmente vacías se omiten (no cuentan como fila).
    """
    columnas_opcionales = columnas_opcionales or []

    try:
        texto = contenido.decode("utf-8-sig")  # utf-8-sig descarta el BOM si está presente
    except UnicodeDecodeError as exc:
        raise ImportacionArchivoError(
            "El archivo no está codificado en UTF-8."
        ) from exc

    # Delimitador: se intenta detectar `,` o `;` (Excel es-MX suele exportar `;`).
    muestra = texto[:4096]
    try:
        dialecto = csv.Sniffer().sniff(muestra, delimiters=",;")
        delimitador = dialecto.delimiter
    except csv.Error:
        delimitador = ","

    lector = csv.reader(io.StringIO(texto), delimiter=delimitador)
    try:
        encabezado = next(lector)
    except StopIteration as exc:
        raise ImportacionArchivoError("El archivo no tiene encabezado.") from exc

    columnas = [c.strip().lower() for c in encabezado]
    faltantes = [c for c in columnas_requeridas if c not in columnas]
    if faltantes:
        raise ImportacionArchivoError(
            f"Faltan columnas requeridas: {', '.join(faltantes)}.",
            detalles={"columnas_encontradas": columnas, "requeridas": columnas_requeridas},
        )

    conocidas = set(columnas_requeridas) | set(columnas_opcionales)
    filas: list[FilaCruda] = []
    numero = 0
    for registro in lector:
        # Salta líneas totalmente vacías (sin ningún valor).
        if not any(celda.strip() for celda in registro):
            continue
        numero += 1
        if numero > max_filas:
            raise ArchivoDemasiadoGrandeError(
                f"El archivo supera el máximo de {max_filas} filas.",
                detalles={"max_filas": max_filas},
            )
        datos = {
            col: (registro[i].strip() if i < len(registro) else "")
            for i, col in enumerate(columnas)
            if col in conocidas
        }
        filas.append(FilaCruda(numero=numero, datos=datos))

    return filas


def parsear_activo(valor: str, *, default: bool = True) -> tuple[bool, str | None]:
    """Interpreta la columna `activo` de forma tolerante. Devuelve (valor, error)."""
    v = valor.strip().lower()
    if v == "":
        return default, None
    if v in {"true", "1", "si", "sí", "verdadero", "activo"}:
        return True, None
    if v in {"false", "0", "no", "falso", "inactivo"}:
        return False, None
    return default, f"Valor de 'activo' no reconocido: '{valor}'."
