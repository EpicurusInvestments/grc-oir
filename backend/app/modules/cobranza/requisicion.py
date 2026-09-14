"""Requisicion (F3) — solicitud de pago de CxP a afiliado, agencia o comisiones.

Máquina de estados real (con endpoint dedicado, como F1/F2):
`pendiente → autorizada → pagada`, rama a `cancelada` desde `pendiente`/`autorizada`.

**Autorización**: `pendiente → autorizada` exige **Dirección o Admin** — CxP captura
pero no se autoriza a sí mismo. Mismo canal dedicado que ya usan `FacturaAfiliado`/
`FacturaAgencia` en F2 (ADR-046): el permiso del router en `/autorizar` es `pagos:leer`
(el nivel que Dirección SÍ tiene) y la regla real (`área in (DIRECCION, ADMIN)`) vive
dentro del servicio — `/estatus` (el canal operativo, `pagos:editar`) rechaza con 403 si
alguien intenta pedir `autorizada` por ahí.

Cuatro FKs opcionales, según `tipo_requisicion` (spec): `factura_afiliado_id`/
`afiliado_id` (pago_afiliado), `factura_agencia_id`/`agencia_id` (pago_agencia),
`vendedor_comision_id`+`orden_id` (comision_vendedor), `agencia_id`+`orden_id`
(comision_agencia). El servicio valida cuáles son obligatorias según el tipo.

Calculados (spec, sin desviaciones):
- `requisicion_comision_vendedor = OrdenCliente.total * porcentaje_comision_vendedor / 100`
- `requisicion_comision_agencia  = OrdenCliente.total * porcentaje_comision_agencia_req / 100`
- `diferencia_afiliada = monto_requisicion - FacturaAfiliado.total_factura_afiliado`
  (monitoreo de márgenes, **puede ser negativa** — sin CHECK `>= 0`, a propósito).
- `razon_social_afiliada`: heredado de `Afiliado` al crear (spec: origen "Derivado" — SÍ
  es columna persistida, a diferencia de los importes de `CobranzaFactura`).

Los porcentajes de comisión se SUGIEREN desde el catálogo (`Vendedor.
porcentaje_comision_default` / `Agencia.porcentaje_comision_agencia_default`) si no se
capturan explícitos — mismo criterio que `FacturaAgencia` en F2.

`monto_requisicion` es SIEMPRE manual (spec): no se fuerza a coincidir con las comisiones
calculadas, que son informativas/de verificación, no una fórmula que sustituya la captura.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, Uuid
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.auth.identity import Area
from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.errors import DomainError, PermissionDeniedError, StateTransitionError
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page

CENTAVOS = Decimal("0.01")


class TipoRequisicion(StrEnum):
    PAGO_AFILIADO = "pago_afiliado"
    PAGO_AGENCIA = "pago_agencia"
    COMISION_VENDEDOR = "comision_vendedor"
    COMISION_AGENCIA = "comision_agencia"


class EstatusRequisicion(StrEnum):
    PENDIENTE = "pendiente"
    AUTORIZADA = "autorizada"
    PAGADA = "pagada"
    CANCELADA = "cancelada"


_TIPOS_SQL = ", ".join(f"'{t.value}'" for t in TipoRequisicion)
_ESTADOS_SQL = ", ".join(f"'{e.value}'" for e in EstatusRequisicion)

TRANSICIONES: dict[str, set[str]] = {
    EstatusRequisicion.PENDIENTE.value: {
        EstatusRequisicion.AUTORIZADA.value,  # canal dedicado, ver `autorizar()`
        EstatusRequisicion.CANCELADA.value,
    },
    EstatusRequisicion.AUTORIZADA.value: {
        EstatusRequisicion.PAGADA.value,
        EstatusRequisicion.CANCELADA.value,
    },
    EstatusRequisicion.PAGADA.value: set(),  # terminal
    EstatusRequisicion.CANCELADA.value: set(),  # terminal
}


# ── Modelo ────────────────────────────────────────────────────────────────────
class Requisicion(Base):
    __tablename__ = "requisicion"
    __table_args__ = (
        CheckConstraint(f"tipo_requisicion IN ({_TIPOS_SQL})", name="ck_requisicion_tipo"),
        CheckConstraint(
            f"estatus_requisicion IN ({_ESTADOS_SQL})", name="ck_requisicion_estatus"
        ),
        CheckConstraint("monto_requisicion >= 0", name="ck_requisicion_monto"),
        # `diferencia_afiliada` NO lleva CHECK >= 0: es monitoreo de márgenes, negativa
        # es un dato legítimo (se pagó menos de lo que facturó el afiliado).
    )

    requisicion_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    numero_requisicion: Mapped[str] = mapped_column(Unicode(30))
    numero_oc_sap: Mapped[str | None] = mapped_column(Unicode(30), default=None)
    tipo_requisicion: Mapped[str] = mapped_column(Unicode(20))

    # ── FKs opcionales según `tipo_requisicion` (spec) ──
    factura_afiliado_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_afiliado.factura_afiliado_id",
            name="fk_requisicion_factura_afiliado",
            ondelete="NO ACTION",
        ),
        default=None,
    )
    factura_agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_agencia.factura_agencia_id",
            name="fk_requisicion_factura_agencia",
            ondelete="NO ACTION",
        ),
        default=None,
    )
    orden_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("orden_cliente.orden_id", name="fk_requisicion_orden", ondelete="NO ACTION"),
        default=None,
    )
    afiliado_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("afiliado.afiliado_id", name="fk_requisicion_afiliado", ondelete="NO ACTION"),
        default=None,
    )
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("agencia.agencia_id", name="fk_requisicion_agencia", ondelete="NO ACTION"),
        default=None,
    )
    vendedor_comision_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey(
            "vendedor.vendedor_id", name="fk_requisicion_vendedor", ondelete="NO ACTION"
        ),
        default=None,
    )

    # Derivado (spec): heredado de Afiliado al crear, columna persistida.
    razon_social_afiliada: Mapped[str | None] = mapped_column(Unicode(200), default=None)

    monto_requisicion: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    porcentaje_comision_vendedor: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    requisicion_comision_vendedor: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), default=None
    )
    porcentaje_comision_agencia_req: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    requisicion_comision_agencia: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), default=None
    )
    diferencia_afiliada: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)

    estatus_requisicion: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusRequisicion.PENDIENTE.value
    )
    fecha_pago_requisicion: Mapped[date | None] = mapped_column(fecha_sql(), default=None)
    observaciones_cuentas_por_pagar: Mapped[str | None] = mapped_column(
        texto_largo(), default=None
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("usuario.usuario_id", name="fk_requisicion_created_by", ondelete="NO ACTION"),
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class RequisicionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requisicion_id: uuid.UUID
    numero_requisicion: str
    numero_oc_sap: str | None = None
    tipo_requisicion: TipoRequisicion
    factura_afiliado_id: uuid.UUID | None = None
    factura_agencia_id: uuid.UUID | None = None
    orden_id: uuid.UUID | None = None
    afiliado_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    razon_social_afiliada: str | None = None
    monto_requisicion: Decimal
    vendedor_comision_id: uuid.UUID | None = None
    porcentaje_comision_vendedor: Decimal | None = None
    requisicion_comision_vendedor: Decimal | None = None
    porcentaje_comision_agencia_req: Decimal | None = None
    requisicion_comision_agencia: Decimal | None = None
    diferencia_afiliada: Decimal | None = None
    estatus_requisicion: EstatusRequisicion
    fecha_pago_requisicion: date | None = None
    observaciones_cuentas_por_pagar: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class RequisicionListParams(ListParams):
    tipo_requisicion: str | None = None
    estatus_requisicion: str | None = None
    afiliado_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    vendedor_comision_id: uuid.UUID | None = None


class RequisicionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    numero_requisicion: str = Field(min_length=1, max_length=30)
    numero_oc_sap: str | None = Field(default=None, max_length=30)
    tipo_requisicion: TipoRequisicion
    factura_afiliado_id: uuid.UUID | None = None
    factura_agencia_id: uuid.UUID | None = None
    orden_id: uuid.UUID | None = None
    afiliado_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    monto_requisicion: Decimal = Field(ge=0)
    vendedor_comision_id: uuid.UUID | None = None
    # Si se omiten, el servicio los sugiere desde el catálogo (Vendedor/Agencia).
    porcentaje_comision_vendedor: Decimal | None = Field(default=None, ge=0, le=100)
    porcentaje_comision_agencia_req: Decimal | None = Field(default=None, ge=0, le=100)
    observaciones_cuentas_por_pagar: str | None = None


class RequisicionUpdate(BaseModel):
    """Edición de los campos capturables, mientras siga `pendiente`. Ninguno de los
    calculados/de estado está aquí: se recalculan solo al re-capturar los insumos."""

    model_config = ConfigDict(extra="forbid")

    numero_oc_sap: str | None = Field(default=None, max_length=30)
    monto_requisicion: Decimal | None = Field(default=None, ge=0)
    porcentaje_comision_vendedor: Decimal | None = Field(default=None, ge=0, le=100)
    porcentaje_comision_agencia_req: Decimal | None = Field(default=None, ge=0, le=100)
    observaciones_cuentas_por_pagar: str | None = None


class TransicionRequisicionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estatus: str
    #: Solo se usa al pasar a `pagada`; se ignora en cualquier otra transición.
    fecha_pago_requisicion: date | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class RequisicionRepository(BaseRepository[Requisicion]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        campos = (
            "tipo_requisicion",
            "estatus_requisicion",
            "afiliado_id",
            "agencia_id",
            "vendedor_comision_id",
        )
        for campo in campos:
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(Requisicion, campo) == valor)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(
                Requisicion.numero_requisicion.ilike(patron)
                | Requisicion.numero_oc_sap.ilike(patron)
            )
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class RequisicionService(
    BaseService[Requisicion, RequisicionCreate, RequisicionUpdate, RequisicionRead]
):
    read_schema = RequisicionRead
    entidad = "Requisicion"

    def __init__(self, repo: RequisicionRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def _pre_update(
        self, obj: Requisicion, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        """Solo editable en `pendiente` — una vez autorizada, cambiar el monto o el %
        de comisión a espaldas de quien autorizó sería alterar lo ya aprobado. Si el
        payload trae `monto_requisicion` o un porcentaje, recalcula los campos
        derivados que dependen de ellos (mismas fórmulas que `create`)."""
        if obj.estatus_requisicion != EstatusRequisicion.PENDIENTE.value:
            raise DomainError(
                "Solo se puede editar una requisición en 'pendiente'.",
                detalles={"estatus_requisicion": obj.estatus_requisicion},
            )
        if obj.orden_id is not None and (
            "porcentaje_comision_vendedor" in payload
            or "porcentaje_comision_agencia_req" in payload
        ):
            from app.modules.ordenes.orden_cliente import OrdenCliente

            orden = self._repo.db.get(OrdenCliente, obj.orden_id)
            if orden is not None:
                if "porcentaje_comision_vendedor" in payload and obj.vendedor_comision_id:
                    payload["requisicion_comision_vendedor"] = (
                        Decimal(orden.total)
                        * payload["porcentaje_comision_vendedor"]
                        / Decimal(100)
                    ).quantize(CENTAVOS)
                if (
                    "porcentaje_comision_agencia_req" in payload
                    and obj.tipo_requisicion == TipoRequisicion.COMISION_AGENCIA.value
                ):
                    payload["requisicion_comision_agencia"] = (
                        Decimal(orden.total)
                        * payload["porcentaje_comision_agencia_req"]
                        / Decimal(100)
                    ).quantize(CENTAVOS)
        if "monto_requisicion" in payload and obj.factura_afiliado_id is not None:
            from app.modules.facturacion.factura_afiliado import FacturaAfiliado

            factura_af = self._repo.db.get(FacturaAfiliado, obj.factura_afiliado_id)
            if factura_af is not None:
                payload["diferencia_afiliada"] = (
                    payload["monto_requisicion"] - Decimal(factura_af.total_factura_afiliado)
                ).quantize(CENTAVOS)

    def create(self, data: RequisicionCreate, usuario: CurrentUser) -> RequisicionRead:
        from app.modules.catalogos.afiliado import Afiliado
        from app.modules.catalogos.agencia import Agencia
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import OrdenCliente
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        tipo = data.tipo_requisicion

        # ── Validación de las FKs obligatorias según el tipo (spec) ──
        if tipo == TipoRequisicion.PAGO_AFILIADO and data.afiliado_id is None:
            raise DomainError("`pago_afiliado` requiere `afiliado_id`.")
        if tipo == TipoRequisicion.PAGO_AGENCIA and data.agencia_id is None:
            raise DomainError("`pago_agencia` requiere `agencia_id`.")
        if tipo == TipoRequisicion.COMISION_VENDEDOR and (
            data.vendedor_comision_id is None or data.orden_id is None
        ):
            raise DomainError(
                "`comision_vendedor` requiere `vendedor_comision_id` y `orden_id`."
            )
        if tipo == TipoRequisicion.COMISION_AGENCIA and (
            data.agencia_id is None or data.orden_id is None
        ):
            raise DomainError("`comision_agencia` requiere `agencia_id` y `orden_id`.")

        razon_social_afiliada = None
        if data.afiliado_id is not None:
            afiliado = db.get(Afiliado, data.afiliado_id)
            if afiliado is None:
                raise DomainError(
                    "El afiliado indicado no existe.",
                    detalles={"afiliado_id": str(data.afiliado_id)},
                )
            razon_social_afiliada = afiliado.razon_social_afiliado

        if data.agencia_id is not None and db.get(Agencia, data.agencia_id) is None:
            raise DomainError(
                "La agencia indicada no existe.", detalles={"agencia_id": str(data.agencia_id)}
            )

        orden = db.get(OrdenCliente, data.orden_id) if data.orden_id is not None else None
        if data.orden_id is not None and orden is None:
            raise DomainError(
                "La OrdenCliente indicada no existe.", detalles={"orden_id": str(data.orden_id)}
            )

        # ── Comisión de vendedor: sugerida del catálogo si no viene explícita ──
        pct_vendedor = data.porcentaje_comision_vendedor
        comision_vendedor = None
        if data.vendedor_comision_id is not None:
            vendedor = db.get(Vendedor, data.vendedor_comision_id)
            if vendedor is None:
                raise DomainError(
                    "El vendedor indicado no existe.",
                    detalles={"vendedor_comision_id": str(data.vendedor_comision_id)},
                )
            if pct_vendedor is None:
                pct_vendedor = vendedor.porcentaje_comision_default
            if orden is not None:
                comision_vendedor = (
                    Decimal(orden.total) * pct_vendedor / Decimal(100)
                ).quantize(CENTAVOS)

        # ── Comisión de agencia: sugerida del catálogo si no viene explícita ──
        pct_agencia = data.porcentaje_comision_agencia_req
        comision_agencia = None
        if tipo == TipoRequisicion.COMISION_AGENCIA and data.agencia_id is not None:
            agencia = db.get(Agencia, data.agencia_id)
            if pct_agencia is None and agencia is not None:
                pct_agencia = agencia.porcentaje_comision_agencia_default
            if orden is not None and pct_agencia is not None:
                comision_agencia = (
                    Decimal(orden.total) * pct_agencia / Decimal(100)
                ).quantize(CENTAVOS)

        # ── Diferencia de márgenes con el afiliado (puede ser negativa) ──
        diferencia_afiliada = None
        if data.factura_afiliado_id is not None:
            from app.modules.facturacion.factura_afiliado import FacturaAfiliado

            factura_af = db.get(FacturaAfiliado, data.factura_afiliado_id)
            if factura_af is None:
                raise DomainError(
                    "La FacturaAfiliado indicada no existe.",
                    detalles={"factura_afiliado_id": str(data.factura_afiliado_id)},
                )
            diferencia_afiliada = (
                data.monto_requisicion - Decimal(factura_af.total_factura_afiliado)
            ).quantize(CENTAVOS)

        obj = Requisicion(
            requisicion_id=uuid4(),
            numero_requisicion=data.numero_requisicion,
            numero_oc_sap=data.numero_oc_sap,
            tipo_requisicion=tipo.value,
            factura_afiliado_id=data.factura_afiliado_id,
            factura_agencia_id=data.factura_agencia_id,
            orden_id=data.orden_id,
            afiliado_id=data.afiliado_id,
            agencia_id=data.agencia_id,
            razon_social_afiliada=razon_social_afiliada,
            monto_requisicion=data.monto_requisicion,
            vendedor_comision_id=data.vendedor_comision_id,
            porcentaje_comision_vendedor=pct_vendedor,
            requisicion_comision_vendedor=comision_vendedor,
            porcentaje_comision_agencia_req=pct_agencia,
            requisicion_comision_agencia=comision_agencia,
            diferencia_afiliada=diferencia_afiliada,
            observaciones_cuentas_por_pagar=data.observaciones_cuentas_por_pagar,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── Máquina de estados (idéntica en forma a FacturaAfiliado/FacturaAgencia, F2) ──
    def transicionar(
        self,
        requisicion_id: uuid.UUID,
        destino: str,
        input_: TransicionRequisicionIn,
        usuario: CurrentUser,
        *,
        autorizando: bool = False,
    ) -> RequisicionRead:
        obj = self._get_or_404(requisicion_id)
        if destino not in {e.value for e in EstatusRequisicion}:
            raise DomainError(f"Estatus desconocido: '{destino}'.")
        if obj.estatus_requisicion == destino:
            return self._to_read(obj)  # idempotente
        if destino not in TRANSICIONES.get(obj.estatus_requisicion, set()):
            raise StateTransitionError(
                f"No se puede pasar de '{obj.estatus_requisicion}' a '{destino}'.",
                detalles={"estatus": obj.estatus_requisicion, "destino": destino},
            )
        if destino == EstatusRequisicion.AUTORIZADA.value and not autorizando:
            # Llegó por el canal operativo (`/estatus`, `pagos:editar`) — CxP no se
            # autoriza a sí mismo. Autorizar va por `/autorizar` (canal dedicado).
            raise PermissionDeniedError(
                "Autorizar va por el canal dedicado POST /{id}/autorizar "
                "(solo Dirección/Admin), no por el cambio de estatus operativo."
            )
        obj.estatus_requisicion = destino
        if destino == EstatusRequisicion.PAGADA.value:
            obj.fecha_pago_requisicion = input_.fecha_pago_requisicion or date.today()
        self._repo.db.commit()
        self._repo.db.refresh(obj)
        return self._to_read(obj)

    def autorizar(self, requisicion_id: uuid.UUID, usuario: CurrentUser) -> RequisicionRead:
        """CANAL DEDICADO para `pendiente → autorizada`. Solo Dirección/Admin.

        Mismo diseño que `FacturaAfiliado.autorizar` (ADR-046): el permiso del ROUTER es
        `pagos:leer` a propósito, porque Dirección NO tiene `pagos:editar` en la matriz
        (captura es de CxP) — la autorización REAL se valida aquí, por área.
        """
        if usuario.area not in (Area.DIRECCION, Area.ADMIN):
            raise PermissionDeniedError(
                f"El área '{usuario.area.value}' no puede autorizar requisiciones "
                "— solo Dirección."
            )
        return self.transicionar(
            requisicion_id,
            EstatusRequisicion.AUTORIZADA.value,
            TransicionRequisicionIn(estatus=EstatusRequisicion.AUTORIZADA.value),
            usuario,
            autorizando=True,
        )


def get_requisicion_service(db: Session = Depends(get_db)) -> RequisicionService:
    return RequisicionService(
        RequisicionRepository(db, Requisicion, default_order_by=[Requisicion.numero_requisicion])
    )


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/requisiciones", tags=["pagos:requisiciones"])


@router.get("", response_model=Page[RequisicionRead])
def listar_requisiciones(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en número de requisición u OC de SAP"),
    tipo_requisicion: str | None = Query(None),
    estatus_requisicion: str | None = Query(None),
    afiliado_id: uuid.UUID | None = Query(None),
    agencia_id: uuid.UUID | None = Query(None),
    vendedor_comision_id: uuid.UUID | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> Page[RequisicionRead]:
    return svc.list(
        RequisicionListParams(
            page=page,
            size=size,
            q=q,
            tipo_requisicion=tipo_requisicion,
            estatus_requisicion=estatus_requisicion,
            afiliado_id=afiliado_id,
            agencia_id=agencia_id,
            vendedor_comision_id=vendedor_comision_id,
        )
    )


@router.get("/{item_id}", response_model=RequisicionRead)
def obtener_requisicion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> RequisicionRead:
    return svc.get(item_id)


@router.post("", response_model=RequisicionRead, status_code=201)
def crear_requisicion(
    payload: RequisicionCreate,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:crear")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> RequisicionRead:
    return svc.create(payload, usuario)


@router.put("/{item_id}", response_model=RequisicionRead)
def actualizar_requisicion(
    item_id: uuid.UUID,
    payload: RequisicionUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:editar")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> RequisicionRead:
    return svc.update(item_id, payload, usuario)


@router.post("/{item_id}/estatus", response_model=RequisicionRead)
def cambiar_estatus_requisicion(
    item_id: uuid.UUID,
    payload: TransicionRequisicionIn,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:editar")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> RequisicionRead:
    """Transiciones OPERATIVAS: `pendiente→cancelada`, `autorizada→pagada`,
    `autorizada→cancelada`. Pedir `autorizada` por aquí devuelve 403."""
    return svc.transicionar(item_id, payload.estatus, payload, usuario)


@router.post("/{item_id}/autorizar", response_model=RequisicionRead)
def autorizar_requisicion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> RequisicionRead:
    """Canal dedicado `pendiente → autorizada`, solo Dirección/Admin (ADR-046)."""
    return svc.autorizar(item_id, usuario)
