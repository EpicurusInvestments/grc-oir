"""Catálogo Afiliado (F0-01).

Empresa externa que opera estaciones. No accede al sistema (solo dato interno). Monta la
base de F0-00 y añade dos reglas propias en la capa de servicio:

- **Unicidad de RFC** (`_pre_create`/`_pre_update`), respaldada por índice UNIQUE.
- **Baja con dependientes** (`_pre_desactivar`): no se desactiva un afiliado con estaciones
  activas salvo confirmación (`forzar=True`).

Nota RFC: el RFC de una persona moral tiene 12 caracteres y el de una física 13. Los
afiliados son empresas (morales), por lo que se valida el formato oficial mexicano de
12-13 caracteres y la columna es `NVARCHAR(13)`. Ver nota en la ficha f0-01.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import ForeignKey, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError, DependenciasActivasError
from app.core.security import CurrentUser
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase

# Formato oficial RFC MX: 3-4 letras (3 moral / 4 física) + AAMMDD + homoclave (3).
RFC_REGEX = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError("RFC inválido: formato mexicano de 12-13 caracteres.")
    return v


class Afiliado(Base):
    __tablename__ = "afiliado"

    afiliado_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_afiliado: Mapped[str] = mapped_column(Unicode(160), index=True)
    razon_social_afiliado: Mapped[str] = mapped_column(Unicode(200))
    rfc_afiliado: Mapped[str] = mapped_column(
        Unicode(13), unique=True, index=True
    )
    plaza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plaza.plaza_id"), index=True
    )
    contacto_nombre: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    contacto_email: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    contacto_telefono: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class AfiliadoCreate(BaseModel):
    nombre_afiliado: str = Field(min_length=1, max_length=160)
    razon_social_afiliado: str = Field(min_length=1, max_length=200)
    rfc_afiliado: str = Field(min_length=12, max_length=13)
    plaza_id: uuid.UUID
    contacto_nombre: str | None = Field(default=None, max_length=160)
    contacto_email: str | None = Field(default=None, max_length=160)
    contacto_telefono: str | None = Field(default=None, max_length=40)

    @field_validator("rfc_afiliado")
    @classmethod
    def _valida_rfc(cls, v: str) -> str:
        return _normaliza_rfc(v)


class AfiliadoUpdate(BaseModel):
    nombre_afiliado: str | None = Field(default=None, min_length=1, max_length=160)
    razon_social_afiliado: str | None = Field(default=None, min_length=1, max_length=200)
    rfc_afiliado: str | None = Field(default=None, min_length=12, max_length=13)
    plaza_id: uuid.UUID | None = None
    contacto_nombre: str | None = Field(default=None, max_length=160)
    contacto_email: str | None = Field(default=None, max_length=160)
    contacto_telefono: str | None = Field(default=None, max_length=40)

    @field_validator("rfc_afiliado")
    @classmethod
    def _valida_rfc(cls, v: str | None) -> str | None:
        return _normaliza_rfc(v) if v is not None else None


class AfiliadoRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    afiliado_id: uuid.UUID
    nombre_afiliado: str
    razon_social_afiliado: str
    rfc_afiliado: str
    plaza_id: uuid.UUID
    contacto_nombre: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class AfiliadoRepository(BaseRepository[Afiliado]):
    def get_by_rfc(
        self, rfc: str, excluir_id: uuid.UUID | None = None
    ) -> Afiliado | None:
        stmt = select(Afiliado).where(Afiliado.rfc_afiliado == rfc)
        if excluir_id is not None:
            stmt = stmt.where(Afiliado.afiliado_id != excluir_id)
        return self.db.scalars(stmt).first()

    def contar_activos_por_plaza(self, plaza_id: uuid.UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Afiliado)
            .where(Afiliado.plaza_id == plaza_id, Afiliado.activo.is_(True))
        )
        return int(total or 0)


# ── Servicio ──────────────────────────────────────────────────────────────────
class AfiliadoService(BaseService[Afiliado, AfiliadoCreate, AfiliadoUpdate, AfiliadoRead]):
    read_schema = AfiliadoRead
    entidad = "Afiliado"

    def __init__(
        self, repo: AfiliadoRepository, *, estacion_repo: Any
    ) -> None:
        super().__init__(repo)
        self._afiliado_repo = repo
        self._estacion_repo = estacion_repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_rfc_unico(payload["rfc_afiliado"], excluir_id=None)

    def _pre_update(
        self, obj: Afiliado, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "rfc_afiliado" in payload:
            self._verificar_rfc_unico(payload["rfc_afiliado"], excluir_id=obj.afiliado_id)

    def _pre_desactivar(self, obj: Afiliado, forzar: bool, usuario: CurrentUser) -> None:
        if forzar:
            return
        estaciones = self._estacion_repo.contar_activas_por_afiliado(obj.afiliado_id)
        if estaciones:
            raise DependenciasActivasError(
                "No se puede desactivar el afiliado porque tiene estaciones activas. "
                "Confirma para desactivarlo de todos modos.",
                detalles={"estaciones_activas": estaciones},
            )

    def _verificar_rfc_unico(self, rfc: str, excluir_id: uuid.UUID | None) -> None:
        if self._afiliado_repo.get_by_rfc(rfc, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe un afiliado con el RFC {rfc}.",
                detalles={"campo": "rfc_afiliado", "valor": rfc},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_afiliado_service(db: Session = Depends(get_db)) -> AfiliadoService:
    from app.modules.catalogos.estacion import Estacion, EstacionRepository

    repo = AfiliadoRepository(
        db,
        Afiliado,
        search_columns=[
            Afiliado.nombre_afiliado,
            Afiliado.razon_social_afiliado,
            Afiliado.rfc_afiliado,
        ],
    )
    return AfiliadoService(repo, estacion_repo=EstacionRepository(db, Estacion))


router = build_crud_router(
    prefix="/afiliados",
    tags=["catalogos:afiliados"],
    permiso_base="catalogos",
    read_schema=AfiliadoRead,
    create_schema=AfiliadoCreate,
    update_schema=AfiliadoUpdate,
    get_service=get_afiliado_service,
    id_type=uuid.UUID,
)
