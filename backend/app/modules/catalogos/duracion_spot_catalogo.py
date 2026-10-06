"""Catálogo DuracionSpotCatalogo (F0-06, fuera de la spec BD v2).

**ADR-159 (petición del usuario):** catálogo NUEVO y DESCONECTADO del `DuracionSpot`
(`app/shared/enums.py`) que hoy usan `TarifaPlaza`/`OrdenCliente`/`OrdenEstacion` — ese
enum NO se toca ("no quiero que modifiques nada de los ENUMS donde configuras el tiempo
de los Spots"). Este módulo solo monta el CRUD de un catálogo administrable por
`producto` (reusa el enum `ProductoTarifa` ya existente en `tarifa.py`, sin duplicarlo)
+ una descripción de duración en TEXTO LIBRE (no un ENUM cerrado): la idea explícita del
usuario es poder "ir agregándole más tiempo etc." sin requerir una migración por cada
valor nuevo — exactamente lo que un ENUM+CHECK no permite.

Por petición expresa ("solo crea el catálogo por ahora no lo usaremos solo quiero ver
el CRUD completo"), NINGÚN otro módulo lee ni escribe esta tabla todavía — ni Tarifa, ni
Órdenes. Se nombra la clase `DuracionSpotCatalogo` (no `DuracionSpot`) para no chocar
con el enum compartido del mismo nombre en `app/shared/enums.py`.

Sin duplicado: para la misma combinación (producto + descripcion_duracion, comparación
case-insensitive) no puede existir otro registro ACTIVO — mismo criterio que `Categoria`
(ADR-017) adaptado a 2 campos en vez de 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError
from app.core.security import CurrentUser
from app.modules.catalogos.tarifa import ProductoTarifa
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.schemas import CatalogoReadBase


def _normaliza_descripcion(valor: str) -> str:
    """Colapsa espacios internos y recorta extremos (misma regla que `Categoria`)."""
    return " ".join(valor.split())


# ── Modelo ──────────────────────────────────────────────────────────────────────
class DuracionSpotCatalogo(Base):
    __tablename__ = "duracion_spot_catalogo"
    __table_args__ = (
        CheckConstraint(
            "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
            name="ck_duracion_spot_catalogo_producto",
        ),
    )

    duracion_spot_catalogo_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    producto: Mapped[str] = mapped_column(Unicode(20), index=True)
    descripcion_duracion: Mapped[str] = mapped_column(Unicode(60))
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class DuracionSpotCatalogoCreate(BaseModel):
    producto: ProductoTarifa
    descripcion_duracion: str = Field(min_length=1, max_length=60)


class DuracionSpotCatalogoUpdate(BaseModel):
    producto: ProductoTarifa | None = Field(default=None)
    descripcion_duracion: str | None = Field(default=None, min_length=1, max_length=60)


class DuracionSpotCatalogoRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    duracion_spot_catalogo_id: uuid.UUID
    producto: ProductoTarifa
    descripcion_duracion: str


# ── Repositorio ───────────────────────────────────────────────────────────────
class DuracionSpotCatalogoRepository(BaseRepository[DuracionSpotCatalogo]):
    def get_por_producto_y_descripcion(
        self, producto: str, descripcion: str, excluir_id: uuid.UUID | None = None
    ) -> DuracionSpotCatalogo | None:
        # Comparación case-insensitive portable (LOWER, ADR-017); `descripcion` ya llega
        # normalizada en espacios.
        stmt = select(DuracionSpotCatalogo).where(
            DuracionSpotCatalogo.producto == producto,
            func.lower(DuracionSpotCatalogo.descripcion_duracion) == descripcion.lower(),
        )
        if excluir_id is not None:
            stmt = stmt.where(DuracionSpotCatalogo.duracion_spot_catalogo_id != excluir_id)
        return self.db.scalars(stmt).first()


# ── Servicio ──────────────────────────────────────────────────────────────────
class DuracionSpotCatalogoService(
    BaseService[
        DuracionSpotCatalogo,
        DuracionSpotCatalogoCreate,
        DuracionSpotCatalogoUpdate,
        DuracionSpotCatalogoRead,
    ]
):
    read_schema = DuracionSpotCatalogoRead
    entidad = "DuracionSpotCatalogo"

    def __init__(self, repo: DuracionSpotCatalogoRepository) -> None:
        super().__init__(repo)
        self._duracion_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        payload["descripcion_duracion"] = _normaliza_descripcion(payload["descripcion_duracion"])
        self._verificar_sin_duplicado(
            payload["producto"], payload["descripcion_duracion"], excluir_id=None
        )

    def _pre_update(
        self, obj: DuracionSpotCatalogo, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "descripcion_duracion" in payload:
            payload["descripcion_duracion"] = _normaliza_descripcion(
                payload["descripcion_duracion"]
            )
        producto = payload.get("producto", obj.producto)
        descripcion = payload.get("descripcion_duracion", obj.descripcion_duracion)
        if "producto" in payload or "descripcion_duracion" in payload:
            self._verificar_sin_duplicado(
                producto, descripcion, excluir_id=obj.duracion_spot_catalogo_id
            )

    def _verificar_sin_duplicado(
        self, producto: str, descripcion: str, excluir_id: uuid.UUID | None
    ) -> None:
        if (
            self._duracion_repo.get_por_producto_y_descripcion(producto, descripcion, excluir_id)
            is not None
        ):
            raise ConflictError(
                f"Ya existe una duración «{descripcion}» para el producto «{producto}».",
                detalles={"producto": producto, "descripcion_duracion": descripcion},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_duracion_spot_catalogo_service(
    db: Session = Depends(get_db),
) -> DuracionSpotCatalogoService:
    repo = DuracionSpotCatalogoRepository(
        db, DuracionSpotCatalogo, search_columns=[DuracionSpotCatalogo.descripcion_duracion]
    )
    return DuracionSpotCatalogoService(repo)


router = build_crud_router(
    prefix="/duraciones-spot",
    tags=["catalogos:duraciones_spot"],
    permiso_base="catalogos",
    read_schema=DuracionSpotCatalogoRead,
    create_schema=DuracionSpotCatalogoCreate,
    update_schema=DuracionSpotCatalogoUpdate,
    get_service=get_duracion_spot_catalogo_service,
    id_type=uuid.UUID,
)
