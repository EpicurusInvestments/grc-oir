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

**ContactoAgencia** (entidad NUEVA, fuera de la spec BD v2 — petición del usuario): la
Agencia ya traía un solo contacto plano (`contacto_nombre`/`contacto_email`/
`contacto_telefono`, arriba). El usuario pidió poder guardar VARIOS contactos, mismo
alcance que `ContactoAnunciante` (`app/modules/catalogos/anunciante.py`) — mirror línea
por línea de esa entidad, tabla propia (no comparte tabla con `ContactoAnunciante`,
misma razón: FKs simples en vez de una polimórfica). Los 3 campos planos existentes
quedan como LEGADO, sin tocar: se dejan de capturar desde el formulario pero se siguen
mostrando de solo lectura en el detalle si una fila vieja los trae.

Portabilidad SQL Server (ADR-014): comparaciones booleanas con `== True`; la unicidad
case-insensitive se resuelve con `func.lower(...)`, portable a SQL Server y SQLite.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError, DependenciasActivasError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.afiliado import RFC_REGEX  # regex oficial MX (fuente única, F0-01)
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.schemas import CatalogoReadBase, ListParams, Page

# Campo sensible de la entidad (spec BD v2). Auditado + permiso por campo.
CAMPO_COMISION = "porcentaje_comision_agencia_default"


def _normaliza_rfc(valor: str) -> str:
    v = valor.strip().upper()
    if not RFC_REGEX.match(v):
        raise ValueError(
            "RFC inválido: debe ser 3-4 letras, 6 dígitos (fecha AAMMDD) y 3 caracteres "
            "alfanuméricos (homoclave) — no cualquier texto de 12-13 caracteres."
        )
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
    # Clave SAT (catálogo c_RegimenFiscal), sugerida desde `ConstantesSistema` grupo
    # RegimenFiscal — sin FK formal (mismo patrón que `metodo_pago_clave` en F2). Es el
    # régimen de la agencia cuando actúa como RECEPTOR de la factura (trato vía agencia):
    # `ExReceptor.RegimenFiscal` del layout del PAC.
    regimen_fiscal: Mapped[str | None] = mapped_column(Unicode(4), default=None)
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
    regimen_fiscal: str | None = Field(default=None, max_length=4)
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
    regimen_fiscal: str | None = Field(default=None, max_length=4)
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
    regimen_fiscal: str | None = None
    porcentaje_comision_agencia_default: Decimal
    # Derivado (solo lectura; NO se acepta en Create/Update):
    anunciantes_count: int = 0  # nº de anunciantes de la agencia (todos)

    # El % viaja como STRING para preservar la precisión Decimal (mismo criterio ADR-015).
    @field_serializer("porcentaje_comision_agencia_default")
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


# ── Repositorio ───────────────────────────────────────────────────────────────
class AgenciaRepository(BaseRepository[Agencia]):
    def get_by_nombre(self, nombre: str, excluir_id: uuid.UUID | None = None) -> Agencia | None:
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

    def __init__(self, repo: AgenciaRepository, *, anunciante_repo: Any) -> None:
        super().__init__(repo)
        self._agencia_repo = repo
        self._anunciante_repo = anunciante_repo

    # ── enriquecimiento (anunciantes_count) ─────────────────────────────────────
    def _read(self, obj: Agencia, count: int) -> AgenciaRead:
        return AgenciaRead.model_validate(obj).model_copy(update={"anunciantes_count": count})

    def _to_read(self, obj: Agencia) -> AgenciaRead:
        count = self._anunciante_repo.contar_por_agencias([obj.agencia_id]).get(obj.agencia_id, 0)
        return self._read(obj, count)

    def list(self, params: ListParams) -> Page[AgenciaRead]:
        # Enriquecimiento por LOTE: 2 consultas por página (lista + conteos agrupados).
        items, total = self.repo.list(params)
        counts = self._anunciante_repo.contar_por_agencias([a.agencia_id for a in items])
        return Page[AgenciaRead](
            items=[self._read(a, counts.get(a.agencia_id, 0)) for a in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

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

    def _pre_update(self, obj: Agencia, payload: dict[str, Any], usuario: CurrentUser) -> None:
        motivo = payload.pop("motivo_cambio", None)  # transitorio: nunca llega a la BD

        if "nombre_agencia" in payload:
            payload["nombre_agencia"] = _normaliza_nombre(payload["nombre_agencia"])
            self._verificar_nombre_unico(payload["nombre_agencia"], excluir_id=obj.agencia_id)

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

    def _pre_desactivar(self, obj: Agencia, forzar: bool, usuario: CurrentUser) -> None:
        if forzar:
            return
        anunciantes = self._anunciante_repo.contar_activos_por_agencia(obj.agencia_id)
        if anunciantes:
            raise DependenciasActivasError(
                "No se puede desactivar la agencia porque tiene anunciantes activos. "
                "Confirma para desactivarla de todos modos.",
                detalles={"anunciantes_activos": anunciantes},
            )

    def _verificar_nombre_unico(self, nombre: str, excluir_id: uuid.UUID | None) -> None:
        if self._agencia_repo.get_by_nombre(nombre, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe una agencia con el nombre «{nombre}».",
                detalles={"campo": "nombre_agencia", "valor": nombre},
            )


# ════════════════════════════════════════════════════════════════════════════════
# ContactoAgencia (anidada en Agencia — entidad nueva, mirror de ContactoAnunciante)
# ════════════════════════════════════════════════════════════════════════════════
class ContactoAgencia(Base):
    __tablename__ = "contacto_agencia"

    contacto_agencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    agencia_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agencia.agencia_id"), index=True)
    nombre_contacto: Mapped[str] = mapped_column(Unicode(160))
    puesto_contacto: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    telefono_contacto: Mapped[str | None] = mapped_column(Unicode(40), default=None)
    email_contacto: Mapped[str | None] = mapped_column(Unicode(160), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class ContactoAgenciaCreate(BaseModel):
    agencia_id: uuid.UUID
    nombre_contacto: str = Field(min_length=1, max_length=160)
    puesto_contacto: str | None = Field(default=None, max_length=160)
    telefono_contacto: str | None = Field(default=None, max_length=40)
    email_contacto: str | None = Field(default=None, max_length=160)


class ContactoAgenciaUpdate(BaseModel):
    agencia_id: uuid.UUID | None = None
    nombre_contacto: str | None = Field(default=None, min_length=1, max_length=160)
    puesto_contacto: str | None = Field(default=None, max_length=160)
    telefono_contacto: str | None = Field(default=None, max_length=40)
    email_contacto: str | None = Field(default=None, max_length=160)


class ContactoAgenciaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    contacto_agencia_id: uuid.UUID
    agencia_id: uuid.UUID
    nombre_contacto: str
    puesto_contacto: str | None = None
    telefono_contacto: str | None = None
    email_contacto: str | None = None


class ContactoAgenciaRepository(BaseRepository[ContactoAgencia]):
    def list_por_agencia(
        self, agencia_id: uuid.UUID, params: ListParams
    ) -> tuple[Sequence[ContactoAgencia], int]:
        base = select(ContactoAgencia).where(ContactoAgencia.agencia_id == agencia_id)
        if params.activo is not None:
            base = base.where(ContactoAgencia.activo == params.activo)
        if params.q:
            base = base.where(ContactoAgencia.nombre_contacto.ilike(f"%{params.q.strip()}%"))
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.order_by(ContactoAgencia.nombre_contacto)
            .offset((params.page - 1) * params.size)
            .limit(params.size)
        )
        return self.db.scalars(stmt).all(), int(total)


class ContactoAgenciaService(
    BaseService[ContactoAgencia, ContactoAgenciaCreate, ContactoAgenciaUpdate, ContactoAgenciaRead]
):
    read_schema = ContactoAgenciaRead
    entidad = "ContactoAgencia"

    def __init__(self, repo: ContactoAgenciaRepository, *, agencia_repo: AgenciaRepository) -> None:
        super().__init__(repo)
        self._contacto_repo = repo
        self._agencia_repo = agencia_repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_agencia(payload["agencia_id"])

    def _pre_update(
        self, obj: ContactoAgencia, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "agencia_id" in payload:
            self._verificar_agencia(payload["agencia_id"])

    def list_por_agencia(
        self, agencia_id: uuid.UUID, params: ListParams
    ) -> Page[ContactoAgenciaRead]:
        items, total = self._contacto_repo.list_por_agencia(agencia_id, params)
        return Page[ContactoAgenciaRead](
            items=[self._to_read(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def _verificar_agencia(self, agencia_id: uuid.UUID) -> None:
        if self._agencia_repo.get(agencia_id) is None:
            raise NotFoundError(
                "Agencia no encontrada para el contacto.",
                detalles={"agencia_id": str(agencia_id)},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_agencia_service(db: Session = Depends(get_db)) -> AgenciaService:
    # Import perezoso para evitar el ciclo agencia ↔ anunciante (anunciante importa Agencia
    # en el nivel de módulo; aquí la referencia inversa se resuelve en tiempo de request).
    from app.modules.catalogos.anunciante import Anunciante, AnuncianteRepository

    repo = AgenciaRepository(
        db,
        Agencia,
        search_columns=[Agencia.nombre_agencia, Agencia.rfc_agencia],
    )
    return AgenciaService(repo, anunciante_repo=AnuncianteRepository(db, Anunciante))


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


@router.get("/{item_id}/historial", response_model=list[audit.LogCambioParametroRead])
def historial_agencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: AgenciaService = Depends(get_agencia_service),
) -> list[audit.LogCambioParametroRead]:
    """Historial de cambios a parámetros sensibles de UNA agencia (más reciente primero).

    Lectura acotada de la bitácora (solo esta entidad); la administración completa de
    auditoría es de F5. Requiere permiso de lectura de catálogos (ADR-021).
    """
    return list(svc.historial(item_id))


def get_contacto_agencia_service(db: Session = Depends(get_db)) -> ContactoAgenciaService:
    repo = ContactoAgenciaRepository(
        db, ContactoAgencia, search_columns=[ContactoAgencia.nombre_contacto]
    )
    return ContactoAgenciaService(repo, agencia_repo=AgenciaRepository(db, Agencia))


contacto_agencia_router = build_crud_router(
    prefix="/contactos-agencia",
    tags=["catalogos:contactos-agencia"],
    permiso_base="catalogos",
    read_schema=ContactoAgenciaRead,
    create_schema=ContactoAgenciaCreate,
    update_schema=ContactoAgenciaUpdate,
    get_service=get_contacto_agencia_service,
    id_type=uuid.UUID,
)


@contacto_agencia_router.get("/agencia/{agencia_id}", response_model=Page[ContactoAgenciaRead])
def listar_contactos_por_agencia(
    agencia_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todos, true=activos, false=inactivos"),
    q: str | None = Query(None, description="Búsqueda por nombre de contacto"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ContactoAgenciaService = Depends(get_contacto_agencia_service),
) -> Page[ContactoAgenciaRead]:
    """Contactos de una agencia (para la sección anidada de la pantalla de agencias)."""
    return svc.list_por_agencia(
        agencia_id, ListParams(page=page, size=size, activo=activo, q=q)
    )
