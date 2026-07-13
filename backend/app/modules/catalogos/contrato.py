"""Catálogo Contrato (F0-03).

Contrato comercial de un anunciante. Reglas propias en la capa de servicio:

- **Máquina de estados `estado_contrato`** (vigente/suspendido/finalizado/cancelado),
  validada con un mapa de transiciones explícito. Se cambia por un endpoint DEDICADO
  `POST /catalogos/contratos/{id}/estado-contrato`, no por el `PUT` genérico. Es una
  dimensión **independiente** de `activo` (baja lógica).
- **`porcentaje_comision_contrato` es PARÁMETRO SENSIBLE** (sobreescribe el default de la
  agencia cuando existe): alta y edición pasan por `audit.registrar_cambio_sensible`.
- **`fecha_fin_contrato >= fecha_inicio_contrato`** (schema y servicio, con valores
  efectivos en edición parcial).
- **`created_by`**: username del capturista (texto, no FK; la tabla Usuario llega en F0-04).
- **Adjuntos (S3):** `archivo_contrato_path` guarda el PREFIJO del contrato en el bucket
  (`contratos/<numero_contrato>/`), resuelto por el puerto de almacenamiento. La subida
  real a S3 está DIFERIDA (adaptador local; ver `integrations/almacenamiento`).

Montos/porcentajes con `Decimal`, serializados como string (ADR-015 E-4). Portabilidad
SQL Server (ADR-014): comparaciones booleanas con `== True`; fechas contra parámetros.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.errors import DomainError, NotFoundError, StateTransitionError
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.port import AlmacenamientoPort
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.schemas import CatalogoReadBase, ListParams, Page

# Campo sensible de la entidad (spec BD v2). Auditado + permiso por campo.
CAMPO_COMISION = "porcentaje_comision_contrato"


class EstadoContrato(StrEnum):
    VIGENTE = "vigente"
    SUSPENDIDO = "suspendido"
    FINALIZADO = "finalizado"
    CANCELADO = "cancelado"


# Transiciones permitidas (confirmadas E-1): vigente↔suspendido, vigente→finalizado,
# finalizado→cancelado y cualquiera→cancelado. Estados terminales: cancelado (y finalizado
# salvo cancelación).
TRANSICIONES: dict[EstadoContrato, set[EstadoContrato]] = {
    EstadoContrato.VIGENTE: {
        EstadoContrato.SUSPENDIDO,
        EstadoContrato.FINALIZADO,
        EstadoContrato.CANCELADO,
    },
    EstadoContrato.SUSPENDIDO: {EstadoContrato.VIGENTE, EstadoContrato.CANCELADO},
    EstadoContrato.FINALIZADO: {EstadoContrato.CANCELADO},
    EstadoContrato.CANCELADO: set(),
}


# ── Modelo ──────────────────────────────────────────────────────────────────────
class Contrato(Base):
    __tablename__ = "contrato"
    __table_args__ = (
        CheckConstraint(
            "estado_contrato IN ('vigente', 'suspendido', 'finalizado', 'cancelado')",
            name="ck_contrato_estado",
        ),
        CheckConstraint(
            "fecha_fin_contrato >= fecha_inicio_contrato", name="ck_contrato_fechas"
        ),
        CheckConstraint(
            "porcentaje_comision_contrato IS NULL OR "
            "(porcentaje_comision_contrato >= 0 AND porcentaje_comision_contrato <= 100)",
            name="ck_contrato_comision",
        ),
    )

    contrato_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("anunciante.anunciante_id"), index=True
    )
    numero_contrato: Mapped[str] = mapped_column(Unicode(60), index=True)
    nombre_contrato: Mapped[str] = mapped_column(Unicode(200))
    fecha_inicio_contrato: Mapped[date] = mapped_column()
    fecha_fin_contrato: Mapped[date] = mapped_column()
    monto_contrato: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    # PARÁMETRO SENSIBLE: % de comisión del contrato (sobreescribe el default de la agencia).
    porcentaje_comision_contrato: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    condiciones_comerciales: Mapped[str | None] = mapped_column(Unicode(4000), default=None)
    estado_contrato: Mapped[str] = mapped_column(
        Unicode(20), default=EstadoContrato.VIGENTE.value
    )
    # Prefijo del contrato en S3 (contratos/<numero>/). Subida diferida.
    archivo_contrato_path: Mapped[str | None] = mapped_column(Unicode(400), default=None)
    observaciones_contrato: Mapped[str | None] = mapped_column(Unicode(1000), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    # Username del capturista (texto, no FK: no hay tabla Usuario hasta F0-04). Ver E-2 (F0-02).
    created_by: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class ContratoCreate(BaseModel):
    anunciante_id: uuid.UUID
    numero_contrato: str = Field(min_length=1, max_length=60)
    nombre_contrato: str = Field(min_length=1, max_length=200)
    fecha_inicio_contrato: date
    fecha_fin_contrato: date
    monto_contrato: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    porcentaje_comision_contrato: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    condiciones_comerciales: str | None = Field(default=None, max_length=4000)
    observaciones_contrato: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _valida_fechas(self) -> ContratoCreate:
        if self.fecha_fin_contrato < self.fecha_inicio_contrato:
            raise ValueError(
                "fecha_fin_contrato debe ser mayor o igual que fecha_inicio_contrato."
            )
        return self


class ContratoUpdate(BaseModel):
    anunciante_id: uuid.UUID | None = None
    numero_contrato: str | None = Field(default=None, min_length=1, max_length=60)
    nombre_contrato: str | None = Field(default=None, min_length=1, max_length=200)
    fecha_inicio_contrato: date | None = None
    fecha_fin_contrato: date | None = None
    monto_contrato: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    porcentaje_comision_contrato: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    condiciones_comerciales: str | None = Field(default=None, max_length=4000)
    observaciones_contrato: str | None = Field(default=None, max_length=1000)
    # Transitorio (NO es columna): requerido si se modifica el % sensible.
    motivo_cambio: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _valida_fechas(self) -> ContratoUpdate:
        if (
            self.fecha_inicio_contrato is not None
            and self.fecha_fin_contrato is not None
            and self.fecha_fin_contrato < self.fecha_inicio_contrato
        ):
            raise ValueError(
                "fecha_fin_contrato debe ser mayor o igual que fecha_inicio_contrato."
            )
        return self


class ContratoRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    contrato_id: uuid.UUID
    anunciante_id: uuid.UUID
    numero_contrato: str
    nombre_contrato: str
    fecha_inicio_contrato: date
    fecha_fin_contrato: date
    monto_contrato: Decimal | None = None
    porcentaje_comision_contrato: Decimal | None = None
    condiciones_comerciales: str | None = None
    estado_contrato: EstadoContrato
    archivo_contrato_path: str | None = None
    observaciones_contrato: str | None = None
    created_by: str | None = None
    # Derivados (solo lectura; NO se aceptan en Create/Update):
    anunciante_nombre: str | None = None  # nombre_comercial del anunciante
    anunciante_rfc: str | None = None  # rfc_anunciante del anunciante

    # Montos como STRING para preservar la precisión Decimal (ADR-015 E-4).
    @field_serializer("monto_contrato", "porcentaje_comision_contrato")
    def _serializa_decimal(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class TransicionEstadoIn(BaseModel):
    """Cuerpo de la transición de `estado_contrato`."""

    estado: EstadoContrato


class ContratoListParams(ListParams):
    """`ListParams` + acotar a un anunciante + filtrar por estado del contrato."""

    anunciante_id: uuid.UUID | None = None
    estado: EstadoContrato | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class ContratoRepository(BaseRepository[Contrato]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        stmt = super()._apply_filters(stmt, params)  # activo + q sobre search_columns
        anunciante_id = getattr(params, "anunciante_id", None)
        if anunciante_id is not None:
            stmt = stmt.where(Contrato.anunciante_id == anunciante_id)
        estado = getattr(params, "estado", None)
        if estado is not None:
            # `estado` es un StrEnum; se compara por su valor textual (columna VARCHAR).
            stmt = stmt.where(Contrato.estado_contrato == EstadoContrato(estado).value)
        return stmt

    def contar_activos_por_anunciante(self, anunciante_id: uuid.UUID) -> int:
        total = self.db.scalar(
            select(func.count())
            .select_from(Contrato)
            .where(Contrato.anunciante_id == anunciante_id, Contrato.activo == True)  # noqa: E712
        )
        return int(total or 0)

    def datos_de_anunciantes(
        self, anunciante_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[str, str]]:
        """(nombre_comercial, rfc) por anunciante, en UNA consulta (evita N+1)."""
        if not anunciante_ids:
            return {}
        rows = self.db.execute(
            select(
                Anunciante.anunciante_id,
                Anunciante.nombre_comercial,
                Anunciante.rfc_anunciante,
            ).where(Anunciante.anunciante_id.in_(set(anunciante_ids)))
        ).all()
        return {row[0]: (row[1], row[2]) for row in rows}


# ── Servicio ──────────────────────────────────────────────────────────────────
class ContratoService(BaseService[Contrato, ContratoCreate, ContratoUpdate, ContratoRead]):
    read_schema = ContratoRead
    entidad = "Contrato"

    def __init__(
        self,
        repo: ContratoRepository,
        *,
        anunciante_repo: BaseRepository[Anunciante],
        almacenamiento: AlmacenamientoPort,
    ) -> None:
        super().__init__(repo)
        self._contrato_repo = repo
        self._anunciante_repo = anunciante_repo
        self._almacenamiento = almacenamiento

    # ── enriquecimiento (anunciante_nombre + anunciante_rfc) ────────────────────
    def _read(
        self, obj: Contrato, datos: tuple[str, str] | None
    ) -> ContratoRead:
        nombre, rfc = datos if datos else (None, None)
        return ContratoRead.model_validate(obj).model_copy(
            update={"anunciante_nombre": nombre, "anunciante_rfc": rfc}
        )

    def _to_read(self, obj: Contrato) -> ContratoRead:
        datos = self._contrato_repo.datos_de_anunciantes([obj.anunciante_id]).get(
            obj.anunciante_id
        )
        return self._read(obj, datos)

    def list(self, params: ListParams) -> Page[ContratoRead]:
        items, total = self.repo.list(params)
        datos = self._contrato_repo.datos_de_anunciantes([c.anunciante_id for c in items])
        return Page[ContratoRead](
            items=[self._read(c, datos.get(c.anunciante_id)) for c in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    # ── reglas ──────────────────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_anunciante(payload["anunciante_id"])
        payload["created_by"] = usuario.username
        payload["estado_contrato"] = EstadoContrato.VIGENTE.value
        payload["archivo_contrato_path"] = self._almacenamiento.prefijo_contrato(
            payload["numero_contrato"]
        )
        # PK explícita para poder auditar el ALTA del % con el id real.
        payload["contrato_id"] = uuid4()
        # El % es opcional: solo se audita si se captura un valor (override de la agencia).
        if payload.get(CAMPO_COMISION) is not None:
            audit.registrar_cambio_sensible(
                db=self._contrato_repo.db,
                entidad=self.entidad,
                entidad_id=payload["contrato_id"],
                campo=CAMPO_COMISION,
                anterior=None,
                nuevo=payload[CAMPO_COMISION],
                usuario=usuario,
                motivo=None,
                requiere_motivo=False,
            )

    def _pre_update(
        self, obj: Contrato, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        motivo = payload.pop("motivo_cambio", None)  # transitorio: nunca llega a la BD

        if "anunciante_id" in payload:
            self._verificar_anunciante(payload["anunciante_id"])

        # Validación de fechas con valores EFECTIVOS (payload o valor actual).
        desde = payload.get("fecha_inicio_contrato", obj.fecha_inicio_contrato)
        hasta = payload.get("fecha_fin_contrato", obj.fecha_fin_contrato)
        if hasta < desde:
            raise DomainError(
                "fecha_fin_contrato debe ser mayor o igual que fecha_inicio_contrato.",
                detalles={"fecha_inicio": str(desde), "fecha_fin": str(hasta)},
            )

        # Si cambia el número, se recalcula el prefijo del contrato en S3.
        if "numero_contrato" in payload:
            payload["archivo_contrato_path"] = self._almacenamiento.prefijo_contrato(
                payload["numero_contrato"]
            )

        if (
            CAMPO_COMISION in payload
            and payload[CAMPO_COMISION] != obj.porcentaje_comision_contrato
        ):
            audit.registrar_cambio_sensible(
                db=self._contrato_repo.db,
                entidad=self.entidad,
                entidad_id=obj.contrato_id,
                campo=CAMPO_COMISION,
                anterior=obj.porcentaje_comision_contrato,
                nuevo=payload[CAMPO_COMISION],
                usuario=usuario,
                motivo=motivo,
                requiere_motivo=True,
            )

    # ── máquina de estados ────────────────────────────────────────────────────────
    def transicionar_estado(
        self, id_: Any, nuevo: EstadoContrato, usuario: CurrentUser
    ) -> ContratoRead:
        obj = self._get_or_404(id_)
        actual = EstadoContrato(obj.estado_contrato)
        if nuevo == actual:
            return self._to_read(obj)  # idempotente: mismo estado, sin cambio
        if nuevo not in TRANSICIONES[actual]:
            raise StateTransitionError(
                f"Transición de contrato no permitida: {actual.value} → {nuevo.value}.",
                detalles={
                    "estado_actual": actual.value,
                    "estado_solicitado": nuevo.value,
                    "permitidas": sorted(e.value for e in TRANSICIONES[actual]),
                },
            )
        return self._to_read(self.repo.update(obj, {"estado_contrato": nuevo.value}))

    def _verificar_anunciante(self, anunciante_id: uuid.UUID) -> None:
        if self._anunciante_repo.get(anunciante_id) is None:
            raise NotFoundError(
                "Anunciante no encontrado para el contrato.",
                detalles={"anunciante_id": str(anunciante_id)},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_contrato_service(db: Session = Depends(get_db)) -> ContratoService:
    repo = ContratoRepository(
        db, Contrato, search_columns=[Contrato.numero_contrato, Contrato.nombre_contrato]
    )
    return ContratoService(
        repo,
        anunciante_repo=BaseRepository(db, Anunciante),
        almacenamiento=AlmacenamientoLocal(),
    )


router = build_crud_router(
    prefix="/contratos",
    tags=["catalogos:contratos"],
    permiso_base="catalogos",
    read_schema=ContratoRead,
    create_schema=ContratoCreate,
    update_schema=ContratoUpdate,
    get_service=get_contrato_service,
    id_type=uuid.UUID,
)

# La factory arma un `listar` genérico; el contrato necesita ADEMÁS el filtro por estado
# (Vigentes/Finalizados…). Se retira SOLO esa ruta y se registra una equivalente con
# `?estado`, sin tocar `crud_router.py` (mismo patrón que TarifaPlaza/Anunciante).
router.routes = [r for r in router.routes if getattr(r, "name", None) != "listar"]


@router.get("", response_model=Page[ContratoRead])
def listar_contratos(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todos, true=activos, false=inactivos"),
    q: str | None = Query(None, description="Búsqueda por número o nombre de contrato"),
    estado: EstadoContrato | None = Query(
        None, description="Filtro por estado del contrato (vigente/suspendido/finalizado/cancelado)"
    ),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ContratoService = Depends(get_contrato_service),
) -> Page[ContratoRead]:
    return svc.list(
        ContratoListParams(page=page, size=size, activo=activo, q=q, estado=estado)
    )


@router.get("/{item_id}/historial", response_model=list[audit.LogCambioParametroRead])
def historial_contrato(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ContratoService = Depends(get_contrato_service),
) -> list[audit.LogCambioParametroRead]:
    """Historial de cambios de `porcentaje_comision_contrato` de UN contrato, más reciente
    primero. Lectura acotada; la administración completa es de F5 (ADR-021)."""
    return list(svc.historial(item_id))


@router.get("/anunciante/{anunciante_id}", response_model=Page[ContratoRead])
def listar_contratos_por_anunciante(
    anunciante_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todos, true=activos, false=inactivos"),
    q: str | None = Query(None, description="Búsqueda por número o nombre de contrato"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ContratoService = Depends(get_contrato_service),
) -> Page[ContratoRead]:
    """Contratos de un anunciante (para la sección 'Contratos' del panel de anunciante)."""
    return svc.list(
        ContratoListParams(anunciante_id=anunciante_id, page=page, size=size, activo=activo, q=q)
    )


@router.post("/{item_id}/estado-contrato", response_model=ContratoRead)
def transicionar_estado_contrato(
    item_id: uuid.UUID,
    payload: TransicionEstadoIn,
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:editar")),
    svc: ContratoService = Depends(get_contrato_service),
) -> ContratoRead:
    """Cambia `estado_contrato` validando la máquina de estados (409 si no es permitida).

    Es independiente de `activo` (baja lógica), que se gestiona en `POST /{id}/estado`.
    """
    return svc.transicionar_estado(item_id, payload.estado, usuario)
