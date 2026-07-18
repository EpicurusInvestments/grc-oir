"""Catálogo CuentaContable (F0-05).

Catálogo contable interno con estructura PROPIA (a diferencia de las constantes SAT, que son
homogéneas): `codigo_cuenta`, `nombre_cuenta`, `tipo_cuenta` (ENUM). Por eso se modela como
tabla aparte y no dentro de `ConstantesSistema` (Opción 2 — ADR-024), recuperando lo diferido
de F0-04 (ADR-022).

Catálogo simple sobre la base de F0-00: modelo + schemas + servicio (unicidad de
`codigo_cuenta`, case-insensitive) + router. `tipo_cuenta` es VARCHAR + CHECK con los 5
valores de la spec (ingreso/costo/gasto/activo/pasivo); en Python, un `StrEnum` fuente única.

Portabilidad SQL Server: unicidad CI vía `func.lower(...)` (ADR-017); booleanos `== True`.

NOTA (F-6): se implementan los 3 campos de la spec. Queda pendiente confirmar con
contabilidad si requieren campos extra (naturaleza, agrupador, …); de ser así, se amplían.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError
from app.core.security import CurrentUser
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase


class TipoCuenta(StrEnum):
    """Naturaleza de la cuenta contable (spec BD v2). Fuente única del CHECK."""

    INGRESO = "ingreso"
    COSTO = "costo"
    GASTO = "gasto"
    ACTIVO = "activo"
    PASIVO = "pasivo"


_TIPOS_SQL = ", ".join(f"'{t.value}'" for t in TipoCuenta)


def _normaliza(valor: str) -> str:
    return " ".join(valor.split())


# ── Modelo ──────────────────────────────────────────────────────────────────────
class CuentaContable(Base):
    __tablename__ = "cuenta_contable"
    __table_args__ = (
        CheckConstraint(f"tipo_cuenta IN ({_TIPOS_SQL})", name="ck_cuenta_contable_tipo"),
    )

    cuenta_contable_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    codigo_cuenta: Mapped[str] = mapped_column(Unicode(40), unique=True, index=True)
    nombre_cuenta: Mapped[str] = mapped_column(Unicode(200), index=True)
    tipo_cuenta: Mapped[str] = mapped_column(Unicode(20))
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class CuentaContableCreate(BaseModel):
    codigo_cuenta: str = Field(min_length=1, max_length=40)
    nombre_cuenta: str = Field(min_length=1, max_length=200)
    tipo_cuenta: TipoCuenta


class CuentaContableUpdate(BaseModel):
    codigo_cuenta: str | None = Field(default=None, min_length=1, max_length=40)
    nombre_cuenta: str | None = Field(default=None, min_length=1, max_length=200)
    tipo_cuenta: TipoCuenta | None = None


class CuentaContableRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    cuenta_contable_id: uuid.UUID
    codigo_cuenta: str
    nombre_cuenta: str
    tipo_cuenta: TipoCuenta


# ── Repositorio ───────────────────────────────────────────────────────────────
class CuentaContableRepository(BaseRepository[CuentaContable]):
    def get_by_codigo(
        self, codigo: str, excluir_id: uuid.UUID | None = None
    ) -> CuentaContable | None:
        stmt = select(CuentaContable).where(
            func.lower(CuentaContable.codigo_cuenta) == codigo.lower()
        )
        if excluir_id is not None:
            stmt = stmt.where(CuentaContable.cuenta_contable_id != excluir_id)
        return self.db.scalars(stmt).first()


# ── Servicio ──────────────────────────────────────────────────────────────────
class CuentaContableService(
    BaseService[
        CuentaContable, CuentaContableCreate, CuentaContableUpdate, CuentaContableRead
    ]
):
    read_schema = CuentaContableRead
    entidad = "CuentaContable"

    def __init__(self, repo: CuentaContableRepository) -> None:
        super().__init__(repo)
        self._cuenta_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        payload["codigo_cuenta"] = _normaliza(payload["codigo_cuenta"])
        payload["nombre_cuenta"] = _normaliza(payload["nombre_cuenta"])
        payload["tipo_cuenta"] = TipoCuenta(payload["tipo_cuenta"]).value
        self._verificar_codigo_unico(payload["codigo_cuenta"], excluir_id=None)

    def _pre_update(
        self, obj: CuentaContable, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "nombre_cuenta" in payload and payload["nombre_cuenta"] is not None:
            payload["nombre_cuenta"] = _normaliza(payload["nombre_cuenta"])
        if "tipo_cuenta" in payload and payload["tipo_cuenta"] is not None:
            payload["tipo_cuenta"] = TipoCuenta(payload["tipo_cuenta"]).value
        if "codigo_cuenta" in payload and payload["codigo_cuenta"] is not None:
            payload["codigo_cuenta"] = _normaliza(payload["codigo_cuenta"])
            self._verificar_codigo_unico(
                payload["codigo_cuenta"], excluir_id=obj.cuenta_contable_id
            )

    def _verificar_codigo_unico(self, codigo: str, excluir_id: uuid.UUID | None) -> None:
        if self._cuenta_repo.get_by_codigo(codigo, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe una cuenta contable con el código «{codigo}».",
                detalles={"campo": "codigo_cuenta", "valor": codigo},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_cuenta_contable_service(db: Session = Depends(get_db)) -> CuentaContableService:
    repo = CuentaContableRepository(
        db,
        CuentaContable,
        search_columns=[CuentaContable.codigo_cuenta, CuentaContable.nombre_cuenta],
        default_order_by=[CuentaContable.codigo_cuenta],
    )
    return CuentaContableService(repo)


router = build_crud_router(
    prefix="/cuentas-contables",
    tags=["catalogos:cuentas-contables"],
    permiso_base="catalogos",
    read_schema=CuentaContableRead,
    create_schema=CuentaContableCreate,
    update_schema=CuentaContableUpdate,
    get_service=get_cuenta_contable_service,
    id_type=uuid.UUID,
)
