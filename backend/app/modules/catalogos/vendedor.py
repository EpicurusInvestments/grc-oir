"""Catálogo Vendedor (F0-04).

Ejecutivo comercial con un `porcentaje_comision_default`. Ese % es **PARÁMETRO SENSIBLE**:
reutiliza EXACTAMENTE el mecanismo de F0-03 (sin código nuevo en `core/`):
`audit.registrar_cambio_sensible(...)` (permiso por campo + motivo + `LogCambioParametro`)
en el alta (anterior=None, sin motivo) y en la edición cuando cambia (motivo requerido).
El historial se consulta con `BaseService.historial` vía `GET /vendedores/{id}/historial`.

La comisión por vendedor principal/secundario se modela en la ORDEN (F1); aquí Vendedor es
solo el catálogo con su comisión default. Portabilidad SQL Server: ADR-011/014.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import CheckConstraint, Numeric, Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase

# Campo sensible de la entidad (spec BD v2). Auditado + permiso por campo (mismo de F0-03).
CAMPO_COMISION = "porcentaje_comision_default"


# ── Modelo ──────────────────────────────────────────────────────────────────────
class Vendedor(Base):
    __tablename__ = "vendedor"
    __table_args__ = (
        CheckConstraint(
            "porcentaje_comision_default >= 0 AND porcentaje_comision_default <= 100",
            name="ck_vendedor_comision",
        ),
    )

    vendedor_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_vendedor: Mapped[str] = mapped_column(Unicode(160), index=True)
    email_vendedor: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    # PARÁMETRO SENSIBLE (spec): % de comisión por defecto del vendedor.
    porcentaje_comision_default: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class VendedorCreate(BaseModel):
    nombre_vendedor: str = Field(min_length=1, max_length=160)
    email_vendedor: str | None = Field(default=None, max_length=160)
    porcentaje_comision_default: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2
    )


class VendedorUpdate(BaseModel):
    nombre_vendedor: str | None = Field(default=None, min_length=1, max_length=160)
    email_vendedor: str | None = Field(default=None, max_length=160)
    porcentaje_comision_default: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    # Transitorio (NO es columna): requerido si se modifica el % sensible.
    motivo_cambio: str | None = Field(default=None, max_length=500)


class VendedorRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    vendedor_id: uuid.UUID
    nombre_vendedor: str
    email_vendedor: str | None = None
    porcentaje_comision_default: Decimal

    # El % viaja como STRING para preservar la precisión Decimal (criterio ADR-015).
    @field_serializer("porcentaje_comision_default")
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


# ── Servicio ──────────────────────────────────────────────────────────────────
class VendedorService(BaseService[Vendedor, VendedorCreate, VendedorUpdate, VendedorRead]):
    read_schema = VendedorRead
    entidad = "Vendedor"

    def __init__(self, repo: BaseRepository[Vendedor]) -> None:
        super().__init__(repo)
        self._vendedor_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        # PK explícita para poder auditar el ALTA con el id real (anterior=None).
        payload["vendedor_id"] = uuid4()
        audit.registrar_cambio_sensible(
            db=self._vendedor_repo.db,
            entidad=self.entidad,
            entidad_id=payload["vendedor_id"],
            campo=CAMPO_COMISION,
            anterior=None,
            nuevo=payload[CAMPO_COMISION],
            usuario=usuario,
            motivo=None,
            requiere_motivo=False,  # en el alta no se exige motivo (captura inicial)
        )

    def _pre_update(
        self, obj: Vendedor, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        motivo = payload.pop("motivo_cambio", None)  # transitorio: nunca llega a la BD
        if (
            CAMPO_COMISION in payload
            and payload[CAMPO_COMISION] != obj.porcentaje_comision_default
        ):
            audit.registrar_cambio_sensible(
                db=self._vendedor_repo.db,
                entidad=self.entidad,
                entidad_id=obj.vendedor_id,
                campo=CAMPO_COMISION,
                anterior=obj.porcentaje_comision_default,
                nuevo=payload[CAMPO_COMISION],
                usuario=usuario,
                motivo=motivo,
                requiere_motivo=True,
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_vendedor_service(db: Session = Depends(get_db)) -> VendedorService:
    repo = BaseRepository(
        db, Vendedor, search_columns=[Vendedor.nombre_vendedor, Vendedor.email_vendedor]
    )
    return VendedorService(repo)


router = build_crud_router(
    prefix="/vendedores",
    tags=["catalogos:vendedores"],
    permiso_base="catalogos",
    read_schema=VendedorRead,
    create_schema=VendedorCreate,
    update_schema=VendedorUpdate,
    get_service=get_vendedor_service,
    id_type=uuid.UUID,
)


@router.get("/{item_id}/historial", response_model=list[audit.LogCambioParametroRead])
def historial_vendedor(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: VendedorService = Depends(get_vendedor_service),
) -> list[audit.LogCambioParametroRead]:
    """Historial de cambios de `porcentaje_comision_default` de UN vendedor, más reciente
    primero. Lectura acotada; la administración completa de auditoría es de F5 (ADR-021)."""
    return list(svc.historial(item_id))
