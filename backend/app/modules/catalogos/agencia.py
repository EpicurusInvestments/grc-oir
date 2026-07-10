"""Catálogo Agencia (F0-03).

Agencia de publicidad que representa a uno o varios anunciantes. No accede al sistema
(solo dato interno). Monta la base de F0-00 y añade sus reglas en la capa de servicio:

- **Unicidad de `nombre_agencia`** (case-insensitive, respaldada por índice único).
- **RFC de persona moral** (mismo formato oficial MX que F0-01; reutiliza `RFC_REGEX`).
- **`porcentaje_comision_agencia_default` es PARÁMETRO SENSIBLE**: al capturarlo o
  modificarlo se verifica permiso por campo, se exige motivo (solo en edición) y se
  registra en `LogCambioParametro` (mecanismo `audit.registrar_cambio_sensible`).

Nota de dependientes: la baja de una agencia con anunciantes activos se bloqueará en
`_pre_desactivar` cuando exista la entidad Anunciante (F0-03, tanda 2). En esta tanda la
tabla `anunciante` aún no existe, por lo que la baja lógica no valida dependientes todavía.

Portabilidad SQL Server (ADR-014): comparaciones booleanas con `== True`; la unicidad
case-insensitive se resuelve con `func.lower(...)`, portable a SQL Server y SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from sqlalchemy import CheckConstraint, Numeric, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError
from app.core.security import CurrentUser
from app.modules.catalogos.afiliado import RFC_REGEX  # regex oficial MX (fuente única, F0-01)
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase

# Campo sensible de la entidad (spec BD v2). Auditado + permiso por campo.
CAMPO_COMISION = "porcentaje_comision_agencia_default"


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError("RFC inválido: formato mexicano de 12-13 caracteres.")
    return v


def _normaliza_nombre(valor: str) -> str:
    """Colapsa espacios internos y recorta extremos (la unicidad es case-insensitive)."""
    return " ".join(valor.split())


# ── Modelo ──────────────────────────────────────────────────────────────────────
class Agencia(Base):
    __tablename__ = "agencia"
    __table_args__ = (
        CheckConstraint(
            "porcentaje_comision_agencia_default >= 0 "
            "AND porcentaje_comision_agencia_default <= 100",
            name="ck_agencia_comision",
        ),
    )

    agencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_agencia: Mapped[str] = mapped_column(Unicode(200), unique=True, index=True)
    rfc_agencia: Mapped[str] = mapped_column(Unicode(13), index=True)
    contacto_nombre: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    contacto_email: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    contacto_telefono: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    # PARÁMETRO SENSIBLE (spec): % de comisión por defecto de la agencia.
    porcentaje_comision_agencia_default: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0")
    )
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class AgenciaCreate(BaseModel):
    nombre_agencia: str = Field(min_length=1, max_length=200)
    rfc_agencia: str = Field(min_length=12, max_length=13)
    contacto_nombre: str | None = Field(default=None, max_length=160)
    contacto_email: str | None = Field(default=None, max_length=160)
    contacto_telefono: str | None = Field(default=None, max_length=40)
    porcentaje_comision_agencia_default: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2
    )

    @field_validator("rfc_agencia")
    @classmethod
    def _valida_rfc(cls, v: str) -> str:
        return _normaliza_rfc(v)


class AgenciaUpdate(BaseModel):
    nombre_agencia: str | None = Field(default=None, min_length=1, max_length=200)
    rfc_agencia: str | None = Field(default=None, min_length=12, max_length=13)
    contacto_nombre: str | None = Field(default=None, max_length=160)
    contacto_email: str | None = Field(default=None, max_length=160)
    contacto_telefono: str | None = Field(default=None, max_length=40)
    porcentaje_comision_agencia_default: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    # Transitorio (NO es columna): requerido si se modifica el % sensible. El servicio lo
    # consume y lo retira del payload antes de escribir en la BD.
    motivo_cambio: str | None = Field(default=None, max_length=500)

    @field_validator("rfc_agencia")
    @classmethod
    def _valida_rfc(cls, v: str | None) -> str | None:
        return _normaliza_rfc(v) if v is not None else None


class AgenciaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    agencia_id: uuid.UUID
    nombre_agencia: str
    rfc_agencia: str
    contacto_nombre: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None
    porcentaje_comision_agencia_default: Decimal

    # El % viaja como STRING para preservar la precisión Decimal (mismo criterio ADR-015).
    @field_serializer("porcentaje_comision_agencia_default")
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


# ── Repositorio ───────────────────────────────────────────────────────────────
class AgenciaRepository(BaseRepository[Agencia]):
    def get_by_nombre(
        self, nombre: str, excluir_id: uuid.UUID | None = None
    ) -> Agencia | None:
        # Comparación case-insensitive portable (SQL Server LOWER / SQLite lower); coincide
        # con el comportamiento del índice único bajo collation CI de SQL Server (ver nota
        # de la tanda 1). `nombre` ya llega normalizado en espacios.
        stmt = select(Agencia).where(func.lower(Agencia.nombre_agencia) == nombre.lower())
        if excluir_id is not None:
            stmt = stmt.where(Agencia.agencia_id != excluir_id)
        return self.db.scalars(stmt).first()


# ── Servicio ──────────────────────────────────────────────────────────────────
class AgenciaService(BaseService[Agencia, AgenciaCreate, AgenciaUpdate, AgenciaRead]):
    read_schema = AgenciaRead
    entidad = "Agencia"

    def __init__(self, repo: AgenciaRepository) -> None:
        super().__init__(repo)
        self._agencia_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        payload["nombre_agencia"] = _normaliza_nombre(payload["nombre_agencia"])
        self._verificar_nombre_unico(payload["nombre_agencia"], excluir_id=None)
        # PK explícita para poder auditar el ALTA con el id real (anterior=None).
        payload["agencia_id"] = uuid4()
        audit.registrar_cambio_sensible(
            db=self._agencia_repo.db,
            entidad=self.entidad,
            entidad_id=payload["agencia_id"],
            campo=CAMPO_COMISION,
            anterior=None,
            nuevo=payload[CAMPO_COMISION],
            usuario=usuario,
            motivo=None,
            requiere_motivo=False,  # en el alta no se exige motivo (es la captura inicial)
        )

    def _pre_update(
        self, obj: Agencia, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        motivo = payload.pop("motivo_cambio", None)  # transitorio: nunca llega a la BD

        if "nombre_agencia" in payload:
            payload["nombre_agencia"] = _normaliza_nombre(payload["nombre_agencia"])
            self._verificar_nombre_unico(
                payload["nombre_agencia"], excluir_id=obj.agencia_id
            )

        if (
            CAMPO_COMISION in payload
            and payload[CAMPO_COMISION] != obj.porcentaje_comision_agencia_default
        ):
            audit.registrar_cambio_sensible(
                db=self._agencia_repo.db,
                entidad=self.entidad,
                entidad_id=obj.agencia_id,
                campo=CAMPO_COMISION,
                anterior=obj.porcentaje_comision_agencia_default,
                nuevo=payload[CAMPO_COMISION],
                usuario=usuario,
                motivo=motivo,
                requiere_motivo=True,
            )

    def _verificar_nombre_unico(self, nombre: str, excluir_id: uuid.UUID | None) -> None:
        if self._agencia_repo.get_by_nombre(nombre, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe una agencia con el nombre «{nombre}».",
                detalles={"campo": "nombre_agencia", "valor": nombre},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_agencia_service(db: Session = Depends(get_db)) -> AgenciaService:
    repo = AgenciaRepository(
        db,
        Agencia,
        search_columns=[Agencia.nombre_agencia, Agencia.rfc_agencia],
    )
    return AgenciaService(repo)


router = build_crud_router(
    prefix="/agencias",
    tags=["catalogos:agencias"],
    permiso_base="catalogos",
    read_schema=AgenciaRead,
    create_schema=AgenciaCreate,
    update_schema=AgenciaUpdate,
    get_service=get_agencia_service,
    id_type=uuid.UUID,
)
