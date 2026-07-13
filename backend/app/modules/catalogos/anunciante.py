"""Catálogo Anunciante + Marca anidada (F0-03).

**Anunciante**: cliente comercial (el que aparece en la factura). Puede operar **vía
agencia** (`agencia_id` con FK) o **directo** (`agencia_id` NULL). Reglas propias:

- **RFC** con el formato oficial MX (12-13; reutiliza `RFC_REGEX` de F0-01). Puede ser
  moral o física (los directos pueden ser personas físicas).
- **`dias_credito_default` es PARÁMETRO SENSIBLE**: alta y edición pasan por el mecanismo
  de auditoría (`audit.registrar_cambio_sensible`) — permiso por campo (solo Admin por
  ahora), motivo requerido al modificarlo, y registro en `LogCambioParametro`.
- **Filtro de lista Vía agencia / Directo** (según `agencia_id` sea o no NULL).
- **Baja con dependientes**: no se desactiva un anunciante con **marcas activas** salvo
  confirmación (`forzar=True`). *(La validación por contratos activos se añade en la tanda
  3, cuando exista la entidad Contrato.)*

**Marca**: se administra **anidada** dentro del Anunciante (no tiene entrada de sidebar
propia), igual que Estación dentro de Afiliado. Expone su CRUD completo + la ruta
`GET /catalogos/marcas/anunciante/{anunciante_id}` para el panel anidado.

Portabilidad SQL Server (ADR-014): el filtro Directo usa `agencia_id IS NULL`
(`.is_(None)`, válido para NULL); los conteos usan `activo == True` (→ `activo = 1`).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from math import ceil
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import CheckConstraint, ForeignKey, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.errors import DependenciasActivasError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.afiliado import RFC_REGEX  # regex oficial MX (fuente única, F0-01)
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase, ListParams, Page

# Campo sensible de la entidad (spec BD v2). Auditado + permiso por campo.
CAMPO_DIAS_CREDITO = "dias_credito_default"


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError("RFC inválido: formato mexicano de 12-13 caracteres.")
    return v


# ════════════════════════════════════════════════════════════════════════════════
# Anunciante
# ════════════════════════════════════════════════════════════════════════════════
class Anunciante(Base):
    __tablename__ = "anunciante"
    __table_args__ = (
        CheckConstraint("dias_credito_default >= 0", name="ck_anunciante_dias_credito"),
    )

    anunciante_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # NULL = anunciante directo (trato sin agencia).
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agencia.agencia_id"), index=True, default=None
    )
    nombre_comercial: Mapped[str] = mapped_column(Unicode(200), index=True)
    # nombre_fiscal: el que aparece en la factura (puede diferir del comercial).
    nombre_fiscal: Mapped[str] = mapped_column(Unicode(250))
    rfc_anunciante: Mapped[str] = mapped_column(Unicode(13), index=True)
    localizacion: Mapped[str | None] = mapped_column(Unicode(250), default=None)
    referencia_anunciante: Mapped[str | None] = mapped_column(Unicode(250), default=None)
    contacto_nombre: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    contacto_email: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    contacto_telefono: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    # PARÁMETRO SENSIBLE (spec): días de crédito por defecto.
    dias_credito_default: Mapped[int] = mapped_column(default=0)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class AnuncianteCreate(BaseModel):
    agencia_id: uuid.UUID | None = None
    nombre_comercial: str = Field(min_length=1, max_length=200)
    nombre_fiscal: str = Field(min_length=1, max_length=250)
    rfc_anunciante: str = Field(min_length=12, max_length=13)
    localizacion: str | None = Field(default=None, max_length=250)
    referencia_anunciante: str | None = Field(default=None, max_length=250)
    contacto_nombre: str | None = Field(default=None, max_length=160)
    contacto_email: str | None = Field(default=None, max_length=160)
    contacto_telefono: str | None = Field(default=None, max_length=40)
    dias_credito_default: int = Field(default=0, ge=0)

    @field_validator("rfc_anunciante")
    @classmethod
    def _valida_rfc(cls, v: str) -> str:
        return _normaliza_rfc(v)


class AnuncianteUpdate(BaseModel):
    agencia_id: uuid.UUID | None = None
    nombre_comercial: str | None = Field(default=None, min_length=1, max_length=200)
    nombre_fiscal: str | None = Field(default=None, min_length=1, max_length=250)
    rfc_anunciante: str | None = Field(default=None, min_length=12, max_length=13)
    localizacion: str | None = Field(default=None, max_length=250)
    referencia_anunciante: str | None = Field(default=None, max_length=250)
    contacto_nombre: str | None = Field(default=None, max_length=160)
    contacto_email: str | None = Field(default=None, max_length=160)
    contacto_telefono: str | None = Field(default=None, max_length=40)
    dias_credito_default: int | None = Field(default=None, ge=0)
    # Transitorio (NO es columna): requerido si se modifica `dias_credito_default`.
    motivo_cambio: str | None = Field(default=None, max_length=500)

    @field_validator("rfc_anunciante")
    @classmethod
    def _valida_rfc(cls, v: str | None) -> str | None:
        return _normaliza_rfc(v) if v is not None else None


class AnuncianteRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    anunciante_id: uuid.UUID
    agencia_id: uuid.UUID | None = None
    nombre_comercial: str
    nombre_fiscal: str
    rfc_anunciante: str
    localizacion: str | None = None
    referencia_anunciante: str | None = None
    contacto_nombre: str | None = None
    contacto_email: str | None = None
    contacto_telefono: str | None = None
    dias_credito_default: int
    # Derivados (solo lectura; NO se aceptan en Create/Update):
    agencia_nombre: str | None = None  # nombre_agencia de la agencia (None si es directo)
    marcas_count: int = 0  # nº de marcas del anunciante (todas)


class AnuncianteListParams(ListParams):
    """`ListParams` + filtro derivado Vía agencia / Directo."""

    relacion: Literal["todas", "via_agencia", "directo"] = "todas"


# ── Repositorio ───────────────────────────────────────────────────────────────
class AnuncianteRepository(BaseRepository[Anunciante]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        stmt = super()._apply_filters(stmt, params)  # activo + q sobre search_columns
        relacion = getattr(params, "relacion", "todas")
        # IS NULL / IS NOT NULL: portables a SQL Server (ADR-014 solo prohíbe .is_ booleano).
        if relacion == "via_agencia":
            stmt = stmt.where(Anunciante.agencia_id.isnot(None))
        elif relacion == "directo":
            stmt = stmt.where(Anunciante.agencia_id.is_(None))
        return stmt

    def contar_activos_por_agencia(self, agencia_id: uuid.UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Anunciante)
            .where(Anunciante.agencia_id == agencia_id, Anunciante.activo == True)  # noqa: E712
        )
        return int(total or 0)

    def nombres_de_agencias(
        self, agencia_ids: Sequence[uuid.UUID | None]
    ) -> dict[uuid.UUID, str]:
        """Nombre de agencia por id, en UNA consulta (evita N+1). Ignora los None (directos)."""
        ids = {a for a in agencia_ids if a is not None}
        if not ids:
            return {}
        rows = self.db.execute(
            select(Agencia.agencia_id, Agencia.nombre_agencia).where(
                Agencia.agencia_id.in_(ids)
            )
        ).all()
        return {row[0]: row[1] for row in rows}


# ── Servicio ──────────────────────────────────────────────────────────────────
class AnuncianteService(
    BaseService[Anunciante, AnuncianteCreate, AnuncianteUpdate, AnuncianteRead]
):
    read_schema = AnuncianteRead
    entidad = "Anunciante"

    def __init__(
        self,
        repo: AnuncianteRepository,
        *,
        agencia_repo: BaseRepository[Agencia],
        marca_repo: Any,
        contrato_repo: Any,
    ) -> None:
        super().__init__(repo)
        self._anunciante_repo = repo
        self._agencia_repo = agencia_repo
        self._marca_repo = marca_repo
        self._contrato_repo = contrato_repo

    # ── enriquecimiento (agencia_nombre + marcas_count) ─────────────────────────
    def _read(
        self, obj: Anunciante, agencia_nombre: str | None, marcas: int
    ) -> AnuncianteRead:
        return AnuncianteRead.model_validate(obj).model_copy(
            update={"agencia_nombre": agencia_nombre, "marcas_count": marcas}
        )

    def _to_read(self, obj: Anunciante) -> AnuncianteRead:
        nombre = (
            self._anunciante_repo.nombres_de_agencias([obj.agencia_id]).get(obj.agencia_id)
            if obj.agencia_id is not None
            else None
        )
        marcas = self._marca_repo.contar_por_anunciantes([obj.anunciante_id]).get(
            obj.anunciante_id, 0
        )
        return self._read(obj, nombre, marcas)

    def list(self, params: ListParams) -> Page[AnuncianteRead]:
        items, total = self.repo.list(params)
        nombres = self._anunciante_repo.nombres_de_agencias([a.agencia_id for a in items])
        marcas = self._marca_repo.contar_por_anunciantes([a.anunciante_id for a in items])
        return Page[AnuncianteRead](
            items=[
                self._read(
                    a,
                    nombres.get(a.agencia_id) if a.agencia_id is not None else None,
                    marcas.get(a.anunciante_id, 0),
                )
                for a in items
            ],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    # ── reglas ──────────────────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        if payload.get("agencia_id") is not None:
            self._verificar_agencia(payload["agencia_id"])
        # PK explícita para auditar el ALTA de `dias_credito_default` con el id real.
        payload["anunciante_id"] = uuid4()
        audit.registrar_cambio_sensible(
            db=self._anunciante_repo.db,
            entidad=self.entidad,
            entidad_id=payload["anunciante_id"],
            campo=CAMPO_DIAS_CREDITO,
            anterior=None,
            nuevo=payload[CAMPO_DIAS_CREDITO],
            usuario=usuario,
            motivo=None,
            requiere_motivo=False,
        )

    def _pre_update(
        self, obj: Anunciante, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        motivo = payload.pop("motivo_cambio", None)  # transitorio: nunca llega a la BD

        if "agencia_id" in payload and payload["agencia_id"] is not None:
            self._verificar_agencia(payload["agencia_id"])

        if (
            CAMPO_DIAS_CREDITO in payload
            and payload[CAMPO_DIAS_CREDITO] != obj.dias_credito_default
        ):
            audit.registrar_cambio_sensible(
                db=self._anunciante_repo.db,
                entidad=self.entidad,
                entidad_id=obj.anunciante_id,
                campo=CAMPO_DIAS_CREDITO,
                anterior=obj.dias_credito_default,
                nuevo=payload[CAMPO_DIAS_CREDITO],
                usuario=usuario,
                motivo=motivo,
                requiere_motivo=True,
            )

    def _pre_desactivar(
        self, obj: Anunciante, forzar: bool, usuario: CurrentUser
    ) -> None:
        if forzar:
            return
        marcas = self._marca_repo.contar_activas_por_anunciante(obj.anunciante_id)
        contratos = self._contrato_repo.contar_activos_por_anunciante(obj.anunciante_id)
        if marcas or contratos:
            raise DependenciasActivasError(
                "No se puede desactivar el anunciante porque tiene marcas o contratos "
                "activos. Confirma para desactivarlo de todos modos.",
                detalles={"marcas_activas": marcas, "contratos_activos": contratos},
            )

    def _verificar_agencia(self, agencia_id: uuid.UUID) -> None:
        if self._agencia_repo.get(agencia_id) is None:
            raise NotFoundError(
                "Agencia no encontrada para el anunciante.",
                detalles={"agencia_id": str(agencia_id)},
            )


# ════════════════════════════════════════════════════════════════════════════════
# Marca (anidada en Anunciante)
# ════════════════════════════════════════════════════════════════════════════════
class Marca(Base):
    __tablename__ = "marca"

    marca_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anunciante.anunciante_id"), index=True
    )
    nombre_marca: Mapped[str] = mapped_column(Unicode(160), index=True)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # updated_at no está en la spec de Marca; se añade por uniformidad (ADR-011).
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class MarcaCreate(BaseModel):
    anunciante_id: uuid.UUID
    nombre_marca: str = Field(min_length=1, max_length=160)


class MarcaUpdate(BaseModel):
    anunciante_id: uuid.UUID | None = None
    nombre_marca: str | None = Field(default=None, min_length=1, max_length=160)


class MarcaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    marca_id: uuid.UUID
    anunciante_id: uuid.UUID
    nombre_marca: str


class MarcaRepository(BaseRepository[Marca]):
    def contar_activas_por_anunciante(self, anunciante_id: uuid.UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Marca)
            .where(Marca.anunciante_id == anunciante_id, Marca.activo == True)  # noqa: E712
        )
        return int(total or 0)

    def contar_por_anunciantes(
        self, anunciante_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Conteo de marcas (TODAS) por anunciante, en UNA consulta (evita N+1)."""
        if not anunciante_ids:
            return {}
        rows = self.db.execute(
            select(Marca.anunciante_id, func.count(Marca.marca_id))
            .where(Marca.anunciante_id.in_(set(anunciante_ids)))
            .group_by(Marca.anunciante_id)
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    def list_por_anunciante(
        self, anunciante_id: uuid.UUID, params: ListParams
    ) -> tuple[Sequence[Marca], int]:
        base = select(Marca).where(Marca.anunciante_id == anunciante_id)
        if params.activo is not None:
            base = base.where(Marca.activo == params.activo)
        if params.q:
            base = base.where(Marca.nombre_marca.ilike(f"%{params.q.strip()}%"))
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.order_by(Marca.nombre_marca)
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        )
        return self.db.scalars(stmt).all(), int(total)


class MarcaService(BaseService[Marca, MarcaCreate, MarcaUpdate, MarcaRead]):
    read_schema = MarcaRead
    entidad = "Marca"

    def __init__(self, repo: MarcaRepository, *, anunciante_repo: AnuncianteRepository) -> None:
        super().__init__(repo)
        self._marca_repo = repo
        self._anunciante_repo = anunciante_repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_anunciante(payload["anunciante_id"])

    def _pre_update(
        self, obj: Marca, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "anunciante_id" in payload:
            self._verificar_anunciante(payload["anunciante_id"])

    def list_por_anunciante(
        self, anunciante_id: uuid.UUID, params: ListParams
    ) -> Page[MarcaRead]:
        items, total = self._marca_repo.list_por_anunciante(anunciante_id, params)
        return Page[MarcaRead](
            items=[self._to_read(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def _verificar_anunciante(self, anunciante_id: uuid.UUID) -> None:
        if self._anunciante_repo.get(anunciante_id) is None:
            raise NotFoundError(
                "Anunciante no encontrado para la marca.",
                detalles={"anunciante_id": str(anunciante_id)},
            )


# ── Dependencias + routers ──────────────────────────────────────────────────────
def get_anunciante_service(db: Session = Depends(get_db)) -> AnuncianteService:
    # Import perezoso para evitar el ciclo anunciante ↔ contrato (contrato importa Anunciante
    # en el nivel de módulo; la referencia inversa se resuelve en tiempo de request).
    from app.modules.catalogos.contrato import Contrato, ContratoRepository

    repo = AnuncianteRepository(
        db,
        Anunciante,
        search_columns=[
            Anunciante.nombre_comercial,
            Anunciante.nombre_fiscal,
            Anunciante.rfc_anunciante,
        ],
    )
    return AnuncianteService(
        repo,
        agencia_repo=BaseRepository(db, Agencia),
        marca_repo=MarcaRepository(db, Marca),
        contrato_repo=ContratoRepository(db, Contrato),
    )


def get_marca_service(db: Session = Depends(get_db)) -> MarcaService:
    repo = MarcaRepository(db, Marca, search_columns=[Marca.nombre_marca])
    return MarcaService(repo, anunciante_repo=AnuncianteRepository(db, Anunciante))


router = build_crud_router(
    prefix="/anunciantes",
    tags=["catalogos:anunciantes"],
    permiso_base="catalogos",
    read_schema=AnuncianteRead,
    create_schema=AnuncianteCreate,
    update_schema=AnuncianteUpdate,
    get_service=get_anunciante_service,
    id_type=uuid.UUID,
)

# La factory arma un `listar` genérico; el anunciante necesita ADEMÁS el filtro derivado
# Vía agencia / Directo. Se retira SOLO esa ruta y se registra una equivalente con
# `?relacion`, sin tocar `crud_router.py` (mismo patrón que TarifaPlaza, ADR-015 E-3).
router.routes = [r for r in router.routes if getattr(r, "name", None) != "listar"]


@router.get("", response_model=Page[AnuncianteRead])
def listar_anunciantes(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todos, true=activos, false=inactivos"),
    q: str | None = Query(None, description="Búsqueda por nombre comercial, fiscal o RFC"),
    relacion: Literal["todas", "via_agencia", "directo"] = Query(
        "todas", description="Filtro derivado: con agencia, directo (sin agencia) o todas"
    ),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: AnuncianteService = Depends(get_anunciante_service),
) -> Page[AnuncianteRead]:
    return svc.list(
        AnuncianteListParams(page=page, size=size, activo=activo, q=q, relacion=relacion)
    )


marca_router = build_crud_router(
    prefix="/marcas",
    tags=["catalogos:marcas"],
    permiso_base="catalogos",
    read_schema=MarcaRead,
    create_schema=MarcaCreate,
    update_schema=MarcaUpdate,
    get_service=get_marca_service,
    id_type=uuid.UUID,
)


@marca_router.get("/anunciante/{anunciante_id}", response_model=Page[MarcaRead])
def listar_marcas_por_anunciante(
    anunciante_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todas, true=activas, false=inactivas"),
    q: str | None = Query(None, description="Búsqueda por nombre de marca"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: MarcaService = Depends(get_marca_service),
) -> Page[MarcaRead]:
    """Marcas de un anunciante (para el panel anidado de la pantalla de anunciantes)."""
    return svc.list_por_anunciante(
        anunciante_id, ListParams(page=page, size=size, activo=activo, q=q)
    )
