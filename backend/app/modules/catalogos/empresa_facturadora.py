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
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.schemas import CatalogoReadBase


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError(
            "RFC inválido: debe ser 3-4 letras, 6 dígitos (fecha AAMMDD) y 3 caracteres "
            "alfanuméricos (homoclave) — no cualquier texto de 12-13 caracteres."
        )
    return v


# ── Modelo ──────────────────────────────────────────────────────────────────────
class EmpresaFacturadora(Base):
    __tablename__ = "empresa_facturadora"

    empresa_facturadora_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_empresa: Mapped[str] = mapped_column(Unicode(200), index=True)
    rfc_empresa: Mapped[str] = mapped_column(Unicode(13), unique=True, index=True)
    # TEXT en la spec → NVARCHAR(MAX) en SQL Server (TEXT en SQLite). Queda SOLO para no
    # perder lo ya capturado — desde ADR-059 la captura real es con los 10 campos
    # estructurados de abajo (domicilio vía código postal, igual a los grupos
    # ExEmisorDomFiscal/ExReceptorDomFiscal del layout del PAC). Ambos coexisten a propósito.
    direccion_empresa: Mapped[str | None] = mapped_column(UnicodeText(), default=None)
    calle: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    numero_exterior: Mapped[str | None] = mapped_column(Unicode(20), default=None)
    numero_interior: Mapped[str | None] = mapped_column(Unicode(20), default=None)
    colonia: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    localidad: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    referencia_domicilio: Mapped[str | None] = mapped_column(Unicode(250), default=None)
    municipio: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    estado: Mapped[str | None] = mapped_column(Unicode(100), default=None)
    pais: Mapped[str | None] = mapped_column(Unicode(3), default="MEX")
    codigo_postal: Mapped[str | None] = mapped_column(Unicode(5), default=None)
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
    calle: str | None = Field(default=None, max_length=150)
    numero_exterior: str | None = Field(default=None, max_length=20)
    numero_interior: str | None = Field(default=None, max_length=20)
    colonia: str | None = Field(default=None, max_length=150)
    localidad: str | None = Field(default=None, max_length=150)
    referencia_domicilio: str | None = Field(default=None, max_length=250)
    municipio: str | None = Field(default=None, max_length=150)
    estado: str | None = Field(default=None, max_length=100)
    pais: str | None = Field(default="MEX", max_length=3)
    codigo_postal: str | None = Field(default=None, max_length=5)

    @field_validator("rfc_empresa")
    @classmethod
    def _valida_rfc(cls, v: str) -> str:
        return _normaliza_rfc(v)


class EmpresaFacturadoraUpdate(BaseModel):
    nombre_empresa: str | None = Field(default=None, min_length=1, max_length=200)
    rfc_empresa: str | None = Field(default=None, min_length=12, max_length=13)
    direccion_empresa: str | None = Field(default=None)
    calle: str | None = Field(default=None, max_length=150)
    numero_exterior: str | None = Field(default=None, max_length=20)
    numero_interior: str | None = Field(default=None, max_length=20)
    colonia: str | None = Field(default=None, max_length=150)
    localidad: str | None = Field(default=None, max_length=150)
    referencia_domicilio: str | None = Field(default=None, max_length=250)
    municipio: str | None = Field(default=None, max_length=150)
    estado: str | None = Field(default=None, max_length=100)
    pais: str | None = Field(default=None, max_length=3)
    codigo_postal: str | None = Field(default=None, max_length=5)

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
    calle: str | None = None
    numero_exterior: str | None = None
    numero_interior: str | None = None
    colonia: str | None = None
    localidad: str | None = None
    referencia_domicilio: str | None = None
    municipio: str | None = None
    estado: str | None = None
    pais: str | None = None
    codigo_postal: str | None = None


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
            self._verificar_rfc_unico(payload["rfc_empresa"], excluir_id=obj.empresa_facturadora_id)

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
