"""Catálogo EmpresaFacturadora (F0-04).

Razón social del grupo que emite facturas; puede haber varias. Catálogo simple montado
sobre la base de F0-00: modelo + schemas + servicio (unicidad de RFC) + router.

Notas de la spec BD v2 (pág. 9):
- `direccion_empresa` es TEXT → se mapea con `UnicodeText` (NVARCHAR(MAX) en SQL Server,
  TEXT en SQLite) para ser fiel a la spec.
- RFC de persona moral: mismo formato oficial MX que F0-01 (reutiliza `RFC_REGEX`); único
  por razón social (decisión E-2).

Portabilidad SQL Server (ADR-014): comparaciones booleanas con `== True`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Unicode, UnicodeText, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError
from app.core.security import CurrentUser
from app.modules.catalogos.afiliado import RFC_REGEX  # regex oficial MX (fuente única, F0-01)
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError("RFC inválido: formato mexicano de 12-13 caracteres.")
    return v


# ── Modelo ──────────────────────────────────────────────────────────────────────
class EmpresaFacturadora(Base):
    __tablename__ = "empresa_facturadora"

    empresa_facturadora_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_empresa: Mapped[str] = mapped_column(Unicode(200), index=True)
    rfc_empresa: Mapped[str] = mapped_column(Unicode(13), unique=True, index=True)
    # TEXT en la spec → NVARCHAR(MAX) en SQL Server (TEXT en SQLite).
    direccion_empresa: Mapped[str | None] = mapped_column(UnicodeText(), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # updated_at por uniformidad (ADR-011), como el resto de catálogos.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class EmpresaFacturadoraCreate(BaseModel):
    nombre_empresa: str = Field(min_length=1, max_length=200)
    rfc_empresa: str = Field(min_length=12, max_length=13)
    direccion_empresa: str | None = Field(default=None)

    @field_validator("rfc_empresa")
    @classmethod
    def _valida_rfc(cls, v: str) -> str:
        return _normaliza_rfc(v)


class EmpresaFacturadoraUpdate(BaseModel):
    nombre_empresa: str | None = Field(default=None, min_length=1, max_length=200)
    rfc_empresa: str | None = Field(default=None, min_length=12, max_length=13)
    direccion_empresa: str | None = Field(default=None)

    @field_validator("rfc_empresa")
    @classmethod
    def _valida_rfc(cls, v: str | None) -> str | None:
        return _normaliza_rfc(v) if v is not None else None


class EmpresaFacturadoraRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    empresa_facturadora_id: uuid.UUID
    nombre_empresa: str
    rfc_empresa: str
    direccion_empresa: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class EmpresaFacturadoraRepository(BaseRepository[EmpresaFacturadora]):
    def get_by_rfc(
        self, rfc: str, excluir_id: uuid.UUID | None = None
    ) -> EmpresaFacturadora | None:
        stmt = select(EmpresaFacturadora).where(EmpresaFacturadora.rfc_empresa == rfc)
        if excluir_id is not None:
            stmt = stmt.where(EmpresaFacturadora.empresa_facturadora_id != excluir_id)
        return self.db.scalars(stmt).first()


# ── Servicio ──────────────────────────────────────────────────────────────────
class EmpresaFacturadoraService(
    BaseService[
        EmpresaFacturadora,
        EmpresaFacturadoraCreate,
        EmpresaFacturadoraUpdate,
        EmpresaFacturadoraRead,
    ]
):
    read_schema = EmpresaFacturadoraRead
    entidad = "EmpresaFacturadora"

    def __init__(self, repo: EmpresaFacturadoraRepository) -> None:
        super().__init__(repo)
        self._empresa_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_rfc_unico(payload["rfc_empresa"], excluir_id=None)

    def _pre_update(
        self, obj: EmpresaFacturadora, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "rfc_empresa" in payload:
            self._verificar_rfc_unico(
                payload["rfc_empresa"], excluir_id=obj.empresa_facturadora_id
            )

    def _verificar_rfc_unico(self, rfc: str, excluir_id: uuid.UUID | None) -> None:
        if self._empresa_repo.get_by_rfc(rfc, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe una empresa facturadora con el RFC {rfc}.",
                detalles={"campo": "rfc_empresa", "valor": rfc},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_empresa_facturadora_service(
    db: Session = Depends(get_db),
) -> EmpresaFacturadoraService:
    repo = EmpresaFacturadoraRepository(
        db,
        EmpresaFacturadora,
        search_columns=[EmpresaFacturadora.nombre_empresa, EmpresaFacturadora.rfc_empresa],
    )
    return EmpresaFacturadoraService(repo)


router = build_crud_router(
    prefix="/empresas-facturadoras",
    tags=["catalogos:empresas-facturadoras"],
    permiso_base="catalogos",
    read_schema=EmpresaFacturadoraRead,
    create_schema=EmpresaFacturadoraCreate,
    update_schema=EmpresaFacturadoraUpdate,
    get_service=get_empresa_facturadora_service,
    id_type=uuid.UUID,
)
