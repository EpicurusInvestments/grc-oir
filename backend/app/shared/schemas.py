"""Schemas compartidos por todos los catálogos."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ListParams(BaseModel):
    """Parámetros de listado: filtros + paginación POR PÁGINA (no scroll infinito)."""

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)
    activo: bool | None = None  # None = todos; True = activos; False = inactivos
    q: str | None = None  # búsqueda de texto sobre las columnas configuradas


class Page(BaseModel, Generic[T]):
    """Respuesta paginada estándar de las listas de catálogos."""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class CambioEstadoIn(BaseModel):
    """Cuerpo del cambio de estado (baja/alta lógica).

    `forzar` permite completar una BAJA aunque existan dependientes activos: el servicio
    bloquea la baja con `DependenciasActivasError` (409) salvo que el cliente confirme y
    reintente con `forzar=True`. No afecta a las altas.
    """

    activo: bool
    forzar: bool = False


class CatalogoReadBase(BaseModel):
    """Campos comunes de salida de todo catálogo. Las entidades extienden de aquí."""

    model_config = ConfigDict(from_attributes=True)

    activo: bool
    created_at: datetime
    updated_at: datetime | None = None
