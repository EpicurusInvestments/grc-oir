"""FacturaAgencia (F2) — factura que OIR RECIBE de la agencia por su comisión.

Igual que `FacturaAfiliado`, es un COSTO y lo captura **CxP** (permiso `costos:*`).

Diferencia clave con `FacturaCliente`: la relación con `OrdenCliente` es **1:N** — una
misma OC puede tener varias facturas de agencia. Por eso `orden_id` NO lleva `UNIQUE`
aquí, a diferencia de `factura_cliente.orden_id`.

`comision_agencia = OrdenCliente.total * porcentaje_comision_agencia / 100` (spec). El
porcentaje se SUGIERE desde el catálogo Agencia pero es editable por operación, así que
se persiste en la factura: si el catálogo cambia después, esta factura conserva el que
se pactó. No lleva CHECK de igualdad contra la OC porque un CHECK no puede leer otra
tabla; la fórmula se valida en el servicio (Tanda 2) y en las pruebas.

`updated_at` es ADITIVO (la spec solo pide `created_at`) — ver `factura_afiliado.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db
from app.core.errors import ConflictError, DomainError, PermissionDeniedError, StateTransitionError
from app.core.security import Area, CurrentUser, requiere_permiso
from app.modules.facturacion.factura_afiliado import (
    _ESTATUS_PROVEEDOR_SQL,
    CENTAVOS,
    TRANSICIONES_PROVEEDOR,
    EstatusFacturaProveedor,
    TransicionProveedorIn,
)
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaAgencia(Base):
    __tablename__ = "factura_agencia"
    __table_args__ = (
        CheckConstraint(
            f"estatus_factura_agencia IN ({_ESTATUS_PROVEEDOR_SQL})",
            name="ck_factura_agencia_estatus",
        ),
        CheckConstraint("monto_factura_agencia >= 0", name="ck_factura_agencia_monto"),
        CheckConstraint("iva_factura_agencia >= 0", name="ck_factura_agencia_iva"),
        CheckConstraint("total_factura_agencia >= 0", name="ck_factura_agencia_total"),
        CheckConstraint("comision_agencia >= 0", name="ck_factura_agencia_comision"),
        CheckConstraint(
            "porcentaje_comision_agencia >= 0 AND porcentaje_comision_agencia <= 100",
            name="ck_factura_agencia_pct_comision",
        ),
        # Invariante de suma exacta con `ROUND(x, 2)` en ambos lados (ADR-039): ver la
        # explicación completa en `factura_cliente.py`. Como en FacturaAfiliado, el IVA
        # es CAPTURADO (spec: "Manual"), así que no se le impone la tasa del 16%.
        CheckConstraint(
            "ROUND(total_factura_agencia, 2) = "
            "ROUND(monto_factura_agencia + iva_factura_agencia, 2)",
            name="ck_factura_agencia_total_suma",
        ),
    )

    factura_agencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    agencia_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agencia.agencia_id", name="fk_factura_agencia_agencia", ondelete="NO ACTION")
    )
    # 1:N (a diferencia de FacturaCliente): SIN UniqueConstraint sobre orden_id.
    orden_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orden_cliente.orden_id", name="fk_factura_agencia_orden", ondelete="NO ACTION")
    )
    folio_factura_agencia: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    fecha_factura_agencia: Mapped[date] = mapped_column(fecha_sql())

    monto_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Calculado en el servicio: monto + iva.
    total_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    # Sugerido desde el catálogo Agencia, editable por operación (spec: "Cat/Manual").
    porcentaje_comision_agencia: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    # Calculado en el servicio: OrdenCliente.total * porcentaje / 100.
    comision_agencia: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)

    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    # CLAVE del almacenamiento (S3/local), no una ruta de disco (ADR-042).
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    estatus_factura_agencia: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusFacturaProveedor.RECIBIDA.value
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_factura_agencia_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # ADITIVO (la spec no lo pide) — ver `factura_afiliado.py`.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaAgenciaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_agencia_id: uuid.UUID
    agencia_id: uuid.UUID
    orden_id: uuid.UUID
    folio_factura_agencia: str | None = None
    fecha_factura_agencia: date
    monto_factura_agencia: Decimal
    iva_factura_agencia: Decimal
    total_factura_agencia: Decimal
    porcentaje_comision_agencia: Decimal | None = None
    comision_agencia: Decimal | None = None
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    estatus_factura_agencia: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class FacturaAgenciaListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    agencia_id: uuid.UUID | None = None
    orden_id: uuid.UUID | None = None
    estatus_factura_agencia: str | None = None


# ── Schemas de escritura (Tanda 2) ───────────────────────────────────────────────
class FacturaAgenciaCreate(BaseModel):
    """Captura de CxP. `total_factura_agencia` y `comision_agencia` se calculan; el
    `porcentaje_comision_agencia` se SUGIERE desde el catálogo Agencia si no viene."""

    model_config = ConfigDict(extra="forbid")

    agencia_id: uuid.UUID
    orden_id: uuid.UUID
    folio_factura_agencia: str | None = Field(default=None, max_length=50)
    fecha_factura_agencia: date
    monto_factura_agencia: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    # IVA capturado, igual que en FacturaAfiliado (spec: "Manual").
    iva_factura_agencia: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    # Si viene NULL, se toma el default del catálogo Agencia (editable por operación).
    porcentaje_comision_agencia: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    archivo_nombre: str | None = Field(default=None, max_length=255)
    archivo_path: str | None = Field(default=None, max_length=500)


class FacturaAgenciaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folio_factura_agencia: str | None = Field(default=None, max_length=50)
    fecha_factura_agencia: date | None = None
    monto_factura_agencia: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    iva_factura_agencia: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    porcentaje_comision_agencia: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    archivo_nombre: str | None = Field(default=None, max_length=255)
    archivo_path: str | None = Field(default=None, max_length=500)


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaAgenciaRepository(BaseRepository[FacturaAgencia]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        for campo in ("agencia_id", "orden_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(FacturaAgencia, campo) == valor)
        estatus = getattr(params, "estatus_factura_agencia", None)
        if estatus is not None:
            stmt = stmt.where(FacturaAgencia.estatus_factura_agencia == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(FacturaAgencia.folio_factura_agencia.ilike(patron))
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaAgenciaService(
    BaseService[FacturaAgencia, FacturaAgenciaCreate, FacturaAgenciaUpdate, FacturaAgenciaRead]
):
    """Captura de CxP, cálculo de la comisión sobre el total de la OC, y la misma máquina
    de estados que `FacturaAfiliado` (autorizar exige Dirección/Admin)."""

    read_schema = FacturaAgenciaRead
    entidad = "FacturaAgencia"

    def __init__(self, repo: FacturaAgenciaRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def _calcular_comision(
        self, total_orden: Decimal, porcentaje: Decimal | None
    ) -> Decimal | None:
        """`comision_agencia = OrdenCliente.total * porcentaje / 100` (spec).

        Se calcula sobre el **total** de la orden (con IVA), no sobre el subtotal: así lo
        dice la fórmula de la spec, literal. Sin porcentaje no hay comisión que calcular.
        """
        if porcentaje is None:
            return None
        return (Decimal(total_orden) * Decimal(porcentaje) / Decimal(100)).quantize(CENTAVOS)

    def create(self, data: FacturaAgenciaCreate, usuario: CurrentUser) -> FacturaAgenciaRead:
        from app.modules.catalogos.agencia import Agencia
        from app.modules.ordenes.orden_cliente import OrdenCliente
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        agencia = db.get(Agencia, data.agencia_id)
        if agencia is None:
            raise DomainError(
                "La agencia indicada no existe.", detalles={"agencia_id": str(data.agencia_id)}
            )
        oc = db.get(OrdenCliente, data.orden_id)
        if oc is None:
            raise DomainError(
                "La OrdenCliente indicada no existe.", detalles={"orden_id": str(data.orden_id)}
            )
        # A diferencia de FacturaCliente, aquí NO se exige `orden_cerrada`: la agencia
        # puede facturar su comisión con otro calendario, y la ficha no pone esa
        # precondición (solo la pone para la factura AL cliente).

        # El porcentaje se sugiere del catálogo si no viene capturado, y se PERSISTE:
        # si el catálogo cambia después, esta factura conserva el pactado.
        porcentaje = data.porcentaje_comision_agencia
        if porcentaje is None:
            porcentaje = agencia.porcentaje_comision_agencia_default

        monto = Decimal(data.monto_factura_agencia).quantize(CENTAVOS)
        iva = Decimal(data.iva_factura_agencia).quantize(CENTAVOS)
        obj = FacturaAgencia(
            factura_agencia_id=uuid4(),
            **data.model_dump(
                exclude={
                    "monto_factura_agencia",
                    "iva_factura_agencia",
                    "porcentaje_comision_agencia",
                }
            ),
            monto_factura_agencia=monto,
            iva_factura_agencia=iva,
            total_factura_agencia=(monto + iva).quantize(CENTAVOS),
            porcentaje_comision_agencia=porcentaje,
            comision_agencia=self._calcular_comision(oc.total, porcentaje),
            estatus_factura_agencia=EstatusFacturaProveedor.RECIBIDA.value,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    def update(
        self, id_: Any, data: FacturaAgenciaUpdate, usuario: CurrentUser
    ) -> FacturaAgenciaRead:
        from app.modules.ordenes.orden_cliente import OrdenCliente

        obj = self._get_or_404(id_)
        if obj.estatus_factura_agencia not in (
            EstatusFacturaProveedor.RECIBIDA.value,
            EstatusFacturaProveedor.EN_REVISION.value,
        ):
            raise ConflictError(
                "Una factura autorizada o pagada ya no se edita.",
                detalles={"estatus_factura_agencia": obj.estatus_factura_agencia},
            )
        payload = data.model_dump(exclude_unset=True)
        obj = self._repo.update(obj, payload)
        recalculos: dict[str, Any] = {}
        if "monto_factura_agencia" in payload or "iva_factura_agencia" in payload:
            recalculos["total_factura_agencia"] = (
                Decimal(obj.monto_factura_agencia) + Decimal(obj.iva_factura_agencia)
            ).quantize(CENTAVOS)
        if "porcentaje_comision_agencia" in payload:
            oc = self._repo.db.get(OrdenCliente, obj.orden_id)
            if oc is not None:
                recalculos["comision_agencia"] = self._calcular_comision(
                    oc.total, obj.porcentaje_comision_agencia
                )
        if recalculos:
            obj = self._repo.update(obj, recalculos)
        return self._to_read(obj)

    def transicionar(
        self,
        factura_agencia_id: uuid.UUID,
        destino: str,
        usuario: CurrentUser,
        *,
        autorizando: bool = False,
    ) -> FacturaAgenciaRead:
        """Misma máquina y misma regla de autorización que `FacturaAfiliado`: autorizar es
        de Dirección/Admin, no de quien captura."""
        obj = self._get_or_404(factura_agencia_id)
        if destino not in {e.value for e in EstatusFacturaProveedor}:
            raise DomainError(f"Estatus desconocido: '{destino}'.")
        if obj.estatus_factura_agencia == destino:
            return self._to_read(obj)  # idempotente
        if destino not in TRANSICIONES_PROVEEDOR.get(obj.estatus_factura_agencia, set()):
            raise StateTransitionError(
                f"No se puede pasar de '{obj.estatus_factura_agencia}' a '{destino}'.",
                detalles={"estatus": obj.estatus_factura_agencia, "destino": destino},
            )
        if destino == EstatusFacturaProveedor.AUTORIZADA.value and not autorizando:
            # Ver `factura_afiliado.autorizar`: autorizar va por su canal dedicado,
            # porque Direccion no tiene `costos:editar` en la matriz de modulo.
            raise PermissionDeniedError(
                "Autorizar va por el canal dedicado POST /{id}/autorizar "
                "(solo Direccion/Admin), no por el cambio de estatus operativo."
            )
        obj.estatus_factura_agencia = destino
        self._repo.db.commit()
        self._repo.db.refresh(obj)
        return self._to_read(obj)


    def autorizar(self, factura_agencia_id: uuid.UUID, usuario: CurrentUser) -> FacturaAgenciaRead:
        """Canal dedicado `en_revision -> autorizada`. Solo Direccion/Admin — mismo
        diseno y motivo que en `FacturaAfiliado` (ver su docstring)."""
        if usuario.area not in (Area.DIRECCION, Area.ADMIN):
            raise PermissionDeniedError(
                f"El area '{usuario.area.value}' no puede autorizar facturas de agencia "
                "- solo Direccion."
            )
        return self.transicionar(
            factura_agencia_id,
            EstatusFacturaProveedor.AUTORIZADA.value,
            usuario,
            autorizando=True,
        )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_agencia_service(db: Session = Depends(get_db)) -> FacturaAgenciaService:
    return FacturaAgenciaService(FacturaAgenciaRepository(db, FacturaAgencia))


router_agencias = APIRouter(prefix="/agencias", tags=["facturacion:agencias"])


@router_agencias.get("", response_model=Page[FacturaAgenciaRead])
def listar_facturas_agencia(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en el folio externo de la agencia"),
    agencia_id: uuid.UUID | None = Query(None),
    orden_id: uuid.UUID | None = Query(None),
    estatus_factura_agencia: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> Page[FacturaAgenciaRead]:
    return svc.list(
        FacturaAgenciaListParams(
            page=page,
            size=size,
            q=q,
            agencia_id=agencia_id,
            orden_id=orden_id,
            estatus_factura_agencia=estatus_factura_agencia,
        )
    )


@router_agencias.get("/{item_id}", response_model=FacturaAgenciaRead)
def obtener_factura_agencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    return svc.get(item_id)


# ── Escritura + transiciones (Tanda 2) ────────────────────────────────────────
@router_agencias.post("", response_model=FacturaAgenciaRead, status_code=201)
def crear_factura_agencia(
    payload: FacturaAgenciaCreate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:crear")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    """`comision_agencia` se calcula como `OrdenCliente.total * porcentaje / 100`; si no
    se captura el porcentaje, se toma el default del catálogo Agencia."""
    return svc.create(payload, usuario)


@router_agencias.put("/{item_id}", response_model=FacturaAgenciaRead)
def actualizar_factura_agencia(
    item_id: uuid.UUID,
    payload: FacturaAgenciaUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    return svc.update(item_id, payload, usuario)


@router_agencias.post("/{item_id}/estatus", response_model=FacturaAgenciaRead)
def cambiar_estatus_factura_agencia(
    item_id: uuid.UUID,
    payload: TransicionProveedorIn,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    """**`autorizada` exige área Dirección o Admin** — 403 si lo intenta CxP."""
    return svc.transicionar(item_id, payload.estatus, usuario)


@router_agencias.post("/{item_id}/autorizar", response_model=FacturaAgenciaRead)
def autorizar_factura_agencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    """Canal dedicado `en_revision → autorizada`, solo Dirección/Admin — mismo criterio
    que en facturas de afiliado."""
    return svc.autorizar(item_id, usuario)
