"""Catálogo Afiliado (F0-01).

Empresa externa que opera estaciones. No accede al sistema (solo dato interno). Monta la
base de F0-00 y añade dos reglas propias en la capa de servicio:

- **Unicidad de RFC** (`_pre_create`/`_pre_update`), respaldada por índice UNIQUE.
- **Baja con dependientes** (`_pre_desactivar`): no se desactiva un afiliado con estaciones
  activas salvo confirmación (`forzar=True`).

Nota RFC: el RFC de una persona moral tiene 12 caracteres y el de una física 13. Los
afiliados son empresas (morales), por lo que se valida el formato oficial mexicano de
12-13 caracteres y la columna es `NVARCHAR(13)`. Ver nota en la ficha f0-01.

**Sin `plaza_id` (ADR-096, petición del usuario):** el Afiliado ya NO tiene plaza propia
— la plaza es una propiedad de la Estación, no del Afiliado (un afiliado puede operar
estaciones en varias plazas). El campo `plaza_id`/`plaza_nombre` que existía aquí
(E-1/ADR-005) se eliminó por completo; vive únicamente en `Estacion` desde ADR-094.

**ContactoAfiliado** (entidad NUEVA, fuera de la spec BD v2 — ADR-094, petición del
usuario): el Afiliado ya traía un solo contacto plano (`contacto_nombre`/
`contacto_email`/`contacto_telefono`, arriba). Mismo patrón que `ContactoAnunciante`/
`ContactoAgencia` (ADR-091/092): tabla propia, anidada (CRUD completo + alta/edición
en vivo dentro del propio formulario del padre, no solo desde el detalle), los 3 campos
planos quedan como LEGADO sin tocar.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import ForeignKey, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError, DependenciasActivasError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.schemas import CatalogoReadBase, ListParams, Page

# Formato oficial RFC MX: 3-4 letras (3 moral / 4 física) + AAMMDD + homoclave (3).
RFC_REGEX = re.compile(r"^[A-ZÑ&]{3,4}[0-9]{6}[A-Z0-9]{3}$")


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError(
            "RFC inválido: debe ser 3-4 letras, 6 dígitos (fecha AAMMDD) y 3 caracteres "
            "alfanuméricos (homoclave) — no cualquier texto de 12-13 caracteres."
        )
    return v


class Afiliado(Base):
    __tablename__ = "afiliado"

    afiliado_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    nombre_afiliado: Mapped[str] = mapped_column(Unicode(160), index=True)
    razon_social_afiliado: Mapped[str] = mapped_column(Unicode(200))
    rfc_afiliado: Mapped[str] = mapped_column(Unicode(13), unique=True, index=True)
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
    contacto_nombre: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None
    # Derivado (solo lectura; NO se acepta en Create/Update):
    estaciones_count: int = 0  # nº de estaciones del afiliado (todas)


# ── Repositorio ───────────────────────────────────────────────────────────────
class AfiliadoRepository(BaseRepository[Afiliado]):
    def get_by_rfc(self, rfc: str, excluir_id: uuid.UUID | None = None) -> Afiliado | None:
        stmt = select(Afiliado).where(Afiliado.rfc_afiliado == rfc)
        if excluir_id is not None:
            stmt = stmt.where(Afiliado.afiliado_id != excluir_id)
        return self.db.scalars(stmt).first()


# ── Servicio ──────────────────────────────────────────────────────────────────
class AfiliadoService(BaseService[Afiliado, AfiliadoCreate, AfiliadoUpdate, AfiliadoRead]):
    read_schema = AfiliadoRead
    entidad = "Afiliado"

    def __init__(self, repo: AfiliadoRepository, *, estacion_repo: Any) -> None:
        super().__init__(repo)
        self._afiliado_repo = repo
        self._estacion_repo = estacion_repo

    # ── enriquecimiento (estaciones_count) ──────────────────────────────────────
    def _read(self, obj: Afiliado, count: int) -> AfiliadoRead:
        return AfiliadoRead.model_validate(obj).model_copy(update={"estaciones_count": count})

    def _to_read(self, obj: Afiliado) -> AfiliadoRead:
        # Camino de un solo registro (get/create/update/estado): 1 consulta puntual.
        count = self._estacion_repo.contar_por_afiliados([obj.afiliado_id]).get(obj.afiliado_id, 0)
        return self._read(obj, count)

    def list(self, params: ListParams) -> Page[AfiliadoRead]:
        # Enriquecimiento por LOTE: 2 consultas por página (lista + conteos).
        items, total = self.repo.list(params)
        counts = self._estacion_repo.contar_por_afiliados([a.afiliado_id for a in items])
        return Page[AfiliadoRead](
            items=[self._read(a, counts.get(a.afiliado_id, 0)) for a in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_rfc_unico(payload["rfc_afiliado"], excluir_id=None)

    def _pre_update(self, obj: Afiliado, payload: dict[str, Any], usuario: CurrentUser) -> None:
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


# ════════════════════════════════════════════════════════════════════════════════
# ContactoAfiliado (anidada en Afiliado — entidad nueva, mirror de ContactoAnunciante)
# ════════════════════════════════════════════════════════════════════════════════
class ContactoAfiliado(Base):
    __tablename__ = "contacto_afiliado"

    contacto_afiliado_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    afiliado_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("afiliado.afiliado_id"), index=True
    )
    nombre_contacto: Mapped[str] = mapped_column(Unicode(160))
    puesto_contacto: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    telefono_contacto: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    email_contacto: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class ContactoAfiliadoCreate(BaseModel):
    afiliado_id: uuid.UUID
    nombre_contacto: str = Field(min_length=1, max_length=160)
    puesto_contacto: str | None = Field(default=None, max_length=160)
    telefono_contacto: str | None = Field(default=None, max_length=40)
    email_contacto: str | None = Field(default=None, max_length=160)


class ContactoAfiliadoUpdate(BaseModel):
    afiliado_id: uuid.UUID | None = None
    nombre_contacto: str | None = Field(default=None, min_length=1, max_length=160)
    puesto_contacto: str | None = Field(default=None, max_length=160)
    telefono_contacto: str | None = Field(default=None, max_length=40)
    email_contacto: str | None = Field(default=None, max_length=160)


class ContactoAfiliadoRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    contacto_afiliado_id: uuid.UUID
    afiliado_id: uuid.UUID
    nombre_contacto: str
    puesto_contacto: str | None = None
    telefono_contacto: str | None = None
    email_contacto: str | None = None


class ContactoAfiliadoRepository(BaseRepository[ContactoAfiliado]):
    def list_por_afiliado(
        self, afiliado_id: uuid.UUID, params: ListParams
    ) -> tuple[Sequence[ContactoAfiliado], int]:
        base = select(ContactoAfiliado).where(ContactoAfiliado.afiliado_id == afiliado_id)
        if params.activo is not None:
            base = base.where(ContactoAfiliado.activo == params.activo)
        if params.q:
            base = base.where(ContactoAfiliado.nombre_contacto.ilike(f"%{params.q.strip()}%"))
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.order_by(ContactoAfiliado.nombre_contacto)
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        )
        return self.db.scalars(stmt).all(), int(total)


class ContactoAfiliadoService(
    BaseService[
        ContactoAfiliado, ContactoAfiliadoCreate, ContactoAfiliadoUpdate, ContactoAfiliadoRead
    ]
):
    read_schema = ContactoAfiliadoRead
    entidad = "ContactoAfiliado"

    def __init__(
        self, repo: ContactoAfiliadoRepository, *, afiliado_repo: AfiliadoRepository
    ) -> None:
        super().__init__(repo)
        self._contacto_repo = repo
        self._afiliado_repo = afiliado_repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_afiliado(payload["afiliado_id"])

    def _pre_update(
        self, obj: ContactoAfiliado, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "afiliado_id" in payload:
            self._verificar_afiliado(payload["afiliado_id"])

    def list_por_afiliado(
        self, afiliado_id: uuid.UUID, params: ListParams
    ) -> Page[ContactoAfiliadoRead]:
        items, total = self._contacto_repo.list_por_afiliado(afiliado_id, params)
        return Page[ContactoAfiliadoRead](
            items=[self._to_read(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def _verificar_afiliado(self, afiliado_id: uuid.UUID) -> None:
        if self._afiliado_repo.get(afiliado_id) is None:
            raise NotFoundError(
                "Afiliado no encontrado para el contacto.",
                detalles={"afiliado_id": str(afiliado_id)},
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


def get_contacto_afiliado_service(db: Session = Depends(get_db)) -> ContactoAfiliadoService:
    repo = ContactoAfiliadoRepository(
        db, ContactoAfiliado, search_columns=[ContactoAfiliado.nombre_contacto]
    )
    return ContactoAfiliadoService(repo, afiliado_repo=AfiliadoRepository(db, Afiliado))


contacto_afiliado_router = build_crud_router(
    prefix="/contactos-afiliado",
    tags=["catalogos:contactos-afiliado"],
    permiso_base="catalogos",
    read_schema=ContactoAfiliadoRead,
    create_schema=ContactoAfiliadoCreate,
    update_schema=ContactoAfiliadoUpdate,
    get_service=get_contacto_afiliado_service,
    id_type=uuid.UUID,
)


@contacto_afiliado_router.get(
    "/afiliado/{afiliado_id}", response_model=Page[ContactoAfiliadoRead]
)
def listar_contactos_por_afiliado(
    afiliado_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todos, true=activos, false=inactivos"),
    q: str | None = Query(None, description="Búsqueda por nombre de contacto"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ContactoAfiliadoService = Depends(get_contacto_afiliado_service),
) -> Page[ContactoAfiliadoRead]:
    """Contactos de un afiliado (para el panel anidado de la pantalla de afiliados)."""
    return svc.list_por_afiliado(
        afiliado_id, ListParams(page=page, size=size, activo=activo, q=q)
    )
