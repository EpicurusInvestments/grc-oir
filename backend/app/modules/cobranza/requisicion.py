"""Requisicion (F3) — solicitud de pago de CxP a afiliado, agencia o comisiones.

Máquina de estados real (con endpoint dedicado, como F1/F2):
`pendiente → autorizada → pagada`, rama a `cancelada` desde `pendiente`/`autorizada`.

**Autorización**: `pendiente → autorizada` exige **Dirección o Admin** — CxP captura
pero no se autoriza a sí mismo. Mismo canal dedicado que ya usan `FacturaAfiliado`/
`FacturaAgencia` en F2 (ADR-046): el permiso del router en `/autorizar` es `pagos:leer`
(el nivel que Dirección SÍ tiene) y la regla real (`área in (DIRECCION, ADMIN)`) vive
dentro del servicio — `/estatus` (el canal operativo, `pagos:editar`) rechaza con 403 si
alguien intenta pedir `autorizada` por ahí.

ADR-283 (petición del usuario, con captura): `pago_afiliado`/`pago_agencia`/
`comision_vendedor` nacen DIRECTO en `autorizada` (ver `create()`) — ya no pasan por
`pendiente` — porque su factura de origen ya tuvo que pasar por la autorización de
Dirección antes de poder generar la requisición (`_validar_factura_disponible` exige
`autorizada`); pedirle a Dirección que autorice otra vez la requisición sería redundante.
`comision_agencia` (sin factura de origen) es la única excepción: sigue naciendo en
`pendiente` y pasando por el canal de autorización normal.

Cuatro FKs según `tipo_requisicion` (spec): `afiliado_id`+`factura_afiliado_id`
(pago_afiliado), `agencia_id`+`factura_agencia_id` (pago_agencia),
`vendedor_comision_id`+`factura_vendedor_id` (comision_vendedor — ver excepción abajo),
`agencia_id`+`orden_id` (comision_agencia). El servicio valida cuáles son obligatorias
según el tipo — `factura_afiliado_id`/`factura_agencia_id` DEJARON de ser opcionales
(petición del usuario): antes se podía capturar la requisición sin saber todavía a cuál
factura correspondía, ahora es obligatoria desde el alta. `comision_agencia` sigue
existiendo en el modelo/API (no se renombra ni se quita, requisiciones viejas siguen
intactas) pero **ya no aparece en el selector "Tipo de requisición" del alta**
(petición del usuario) — solo queda accesible para listar/filtrar lo ya capturado.

Calculados (spec, sin desviaciones salvo lo anotado):
- `requisicion_comision_agencia  = OrdenCliente.total * porcentaje_comision_agencia_req / 100`
- `diferencia_afiliada = monto_requisicion - FacturaAfiliado.total_factura_afiliado`
  (monitoreo de márgenes, **puede ser negativa** — sin CHECK `>= 0`, a propósito).
- `razon_social_afiliada`: heredado de `Afiliado` al crear (spec: origen "Derivado" — SÍ
  es columna persistida, a diferencia de los importes de `CobranzaFactura`).

Los porcentajes de comisión se SUGIEREN desde el catálogo (`Vendedor.
porcentaje_comision_default` / `Agencia.porcentaje_comision_agencia_default`) si no se
capturan explícitos — mismo criterio que `FacturaAgencia` en F2.

**Excepción — "Pagos vendedor" (petición del usuario, ADR nuevo):** `comision_vendedor`
ya NO captura `orden_id` ni `porcentaje_comision_vendedor` desde el alta (se quita el
combo "Orden de cliente" y el campo "% Comisión" del formulario) — se simplifica al
MISMO patrón que `pago_agencia`: solo Vendedor + `FacturaVendedor` (ahora OBLIGATORIA,
ya no opcional) + monto manual (autollenado desde el total de la factura, editable).
`requisicion_comision_vendedor = OrdenCliente.total * porcentaje_comision_vendedor / 100`
(spec) ya NO se calcula por esta vía — las columnas siguen existiendo (no se renombran
ni se quitan: solo quedan sin capturar), y el cálculo en `create()`/`_pre_update()` se
deja intacto (no-op si no hay `orden_id`) por si algún registro antiguo lo trae.

`monto_requisicion` es SIEMPRE manual (spec): no se fuerza a coincidir con las comisiones
calculadas, que son informativas/de verificación, no una fórmula que sustituya la captura.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, Uuid, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.auth.identity import Area
from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.errors import ConflictError, DomainError, PermissionDeniedError, StateTransitionError
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

#: ADR-282 (petición del usuario): el número de requisición ya NO se captura a mano —
#: se genera en el servidor con el mismo patrón prefijo+año+mes+consecutivo que
#: `OrdenCliente._siguiente_folio()` (ADR-237/254/275). Sin "formato viejo" que migrar:
#: los valores manuales previos (p.ej. "RE-01") simplemente no matchean el regex y no
#: cuentan para el consecutivo, que arranca en 1 la primera vez que se genera uno.
_FOLIO_REQUISICION_RE = re.compile(r"^RQ-\d{4}-\d{2}-(\d+)$")

TRANSICIONES: dict[str, set[str]] = {
    EstatusRequisicion.PENDIENTE.value: {
        EstatusRequisicion.AUTORIZADA.value,  # canal dedicado, ver `autorizar()`
        EstatusRequisicion.CANCELADA.value,
    },
    EstatusRequisicion.AUTORIZADA.value: {
        EstatusRequisicion.PAGADA.value,
        EstatusRequisicion.CANCELADA.value,
    },
    # Fix (petición del usuario): "Cancelar Pago a Proveedor" — una requisición ya
    # PAGADA también se puede cancelar (antes terminal). Exige `motivo` (ver
    # `transicionar()`); revierte en cascada la factura de proveedor relacionada a
    # `recibida`, vacía de órdenes (`_revertir_factura_relacionada`).
    EstatusRequisicion.PAGADA.value: {EstatusRequisicion.CANCELADA.value},
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
    # Petición del usuario: `comision_vendedor` no tenía forma de ligarse a una
    # `FacturaVendedor` concreta (`vendedor_comision_id`+`orden_id` no bastan — relación
    # 1:N sin `UniqueConstraint`, igual que `FacturaAgencia`). Opcional: las requisiciones
    # ya existentes no la tienen.
    factura_vendedor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_vendedor.factura_vendedor_id",
            name="fk_requisicion_factura_vendedor",
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
    # Fix (petición del usuario): obligatorio al cancelar desde `pagada` ("Cancelar
    # Pago a Proveedor") — mismo criterio que `PagoCliente.motivo_cancelacion` (ADR-286).
    # Opcional al cancelar desde `pendiente`/`autorizada` (no cambia ese flujo existente).
    motivo_cancelacion: Mapped[str | None] = mapped_column(Unicode(255), default=None)

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
    factura_vendedor_id: uuid.UUID | None = None
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
    motivo_cancelacion: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    #: Folio de la factura de origen (emisora/agencia/vendedor, según `tipo_requisicion`)
    #: — se resuelve en el servicio, en lote por página (columna "Folio" de la pantalla
    #: de consulta). `None` para `comision_agencia` (no tiene factura ligada).
    folio_factura_origen: str | None = None
    #: Folios de las OrdenCliente/OrdenEstacion relacionadas, separados por coma
    #: (petición del usuario, columna "Órdenes" de la lista) — se resuelve en el
    #: servicio, en lote por página, vía las tablas puente de cada tipo de factura (o
    #: `orden_id` directo para `comision_agencia`). `None` si no se resolvió ninguna.
    ordenes_folios: str | None = None


class RequisicionListParams(ListParams):
    tipo_requisicion: str | None = None
    estatus_requisicion: str | None = None
    afiliado_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    vendedor_comision_id: uuid.UUID | None = None


class RequisicionCreate(BaseModel):
    """`numero_requisicion` NO se acepta (ADR-282): es "Calculado", se genera siempre en
    el servicio (`RequisicionService._siguiente_numero_requisicion`)."""

    model_config = ConfigDict(extra="forbid")

    numero_oc_sap: str | None = Field(default=None, max_length=30)
    tipo_requisicion: TipoRequisicion
    factura_afiliado_id: uuid.UUID | None = None
    factura_agencia_id: uuid.UUID | None = None
    # Opcional incluso para `comision_vendedor`: una requisición de comisión puede
    # capturarse sin saber todavía a cuál `FacturaVendedor` corresponde (se le asigna
    # después, editándola) — no bloquea el alta.
    factura_vendedor_id: uuid.UUID | None = None
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
    #: Fix (petición del usuario): obligatorio al cancelar desde `pagada` ("Cancelar
    #: Pago a Proveedor") — se valida en el servicio, no aquí (depende del estatus
    #: ACTUAL de la requisición, que el schema no conoce). Opcional/ignorado en
    #: cualquier otra transición.
    motivo: str | None = Field(default=None, max_length=255)


# ── Combos "disponibles" del alta (petición del usuario, con captura): una factura ya
# usada por OTRA requisición (de cualquier estatus, no solo `pagada`) no debe volver a
# ofrecerse — antes el combo solo filtraba por `estatus_factura_xxx == "autorizada"`,
# así que una factura ya elegida en una requisición `pendiente`/`autorizada` seguía
# apareciendo para elegirla de nuevo en otra.
class FacturaAfiliadoDisponibleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_afiliado_id: uuid.UUID
    afiliado_id: uuid.UUID
    factura_emisora: str
    total_factura_afiliado: Decimal


class FacturaAgenciaDisponibleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_agencia_id: uuid.UUID
    agencia_id: uuid.UUID
    folio_factura_agencia: str | None = None
    total_factura_agencia: Decimal


class FacturaVendedorDisponibleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_vendedor_id: uuid.UUID
    vendedor_id: uuid.UUID
    folio_factura_vendedor: str | None = None
    total_factura_vendedor: Decimal


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
            # ADR-282: también busca por el folio de la factura de origen (Afiliado/
            # Agencia/Vendedor, según `tipo_requisicion`) — vive en otra tabla, así que
            # se arma como EXISTS correlacionado en vez de un JOIN (una requisición solo
            # trae UNA de las tres FKs, nunca las tres a la vez).
            from app.modules.facturacion.factura_afiliado import FacturaAfiliado
            from app.modules.facturacion.factura_agencia import FacturaAgencia
            from app.modules.facturacion.factura_vendedor import FacturaVendedor

            patron = f"%{params.q.strip()}%"
            folio_afiliado = (
                select(FacturaAfiliado.factura_afiliado_id)
                .where(
                    FacturaAfiliado.factura_afiliado_id == Requisicion.factura_afiliado_id,
                    FacturaAfiliado.factura_emisora.ilike(patron),
                )
                .exists()
            )
            folio_agencia = (
                select(FacturaAgencia.factura_agencia_id)
                .where(
                    FacturaAgencia.factura_agencia_id == Requisicion.factura_agencia_id,
                    FacturaAgencia.folio_factura_agencia.ilike(patron),
                )
                .exists()
            )
            folio_vendedor = (
                select(FacturaVendedor.factura_vendedor_id)
                .where(
                    FacturaVendedor.factura_vendedor_id == Requisicion.factura_vendedor_id,
                    FacturaVendedor.folio_factura_vendedor.ilike(patron),
                )
                .exists()
            )
            # Fix (petición del usuario): la columna "Órdenes" nueva también se puede
            # buscar — igual criterio EXISTS correlacionado, una vía por tipo (vía las
            # 3 tablas puente, u `orden_id` directo para `comision_agencia`).
            from app.modules.facturacion.factura_afiliado import FacturaAfiliadoOrden
            from app.modules.facturacion.factura_agencia import FacturaAgenciaOrden
            from app.modules.facturacion.factura_vendedor import FacturaVendedorOrden
            from app.modules.ordenes.orden_cliente import OrdenCliente
            from app.modules.ordenes.orden_estacion import OrdenEstacion

            orden_agencia = (
                select(FacturaAgenciaOrden.factura_agencia_id)
                .join(OrdenCliente, OrdenCliente.orden_id == FacturaAgenciaOrden.orden_id)
                .where(
                    FacturaAgenciaOrden.factura_agencia_id == Requisicion.factura_agencia_id,
                    OrdenCliente.folio_orden.ilike(patron),
                )
                .exists()
            )
            orden_vendedor = (
                select(FacturaVendedorOrden.factura_vendedor_id)
                .join(OrdenCliente, OrdenCliente.orden_id == FacturaVendedorOrden.orden_id)
                .where(
                    FacturaVendedorOrden.factura_vendedor_id == Requisicion.factura_vendedor_id,
                    OrdenCliente.folio_orden.ilike(patron),
                )
                .exists()
            )
            orden_afiliado = (
                select(FacturaAfiliadoOrden.factura_afiliado_id)
                .join(
                    OrdenEstacion,
                    OrdenEstacion.orden_estacion_id == FacturaAfiliadoOrden.orden_estacion_id,
                )
                .where(
                    FacturaAfiliadoOrden.factura_afiliado_id == Requisicion.factura_afiliado_id,
                    OrdenEstacion.folio_orden_estacion.ilike(patron),
                )
                .exists()
            )
            orden_directa = (
                select(OrdenCliente.orden_id)
                .where(
                    OrdenCliente.orden_id == Requisicion.orden_id,
                    OrdenCliente.folio_orden.ilike(patron),
                )
                .exists()
            )
            stmt = stmt.where(
                Requisicion.numero_requisicion.ilike(patron)
                | Requisicion.numero_oc_sap.ilike(patron)
                | folio_afiliado
                | folio_agencia
                | folio_vendedor
                | orden_agencia
                | orden_vendedor
                | orden_afiliado
                | orden_directa
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

    def _siguiente_numero_requisicion(self, hoy: date) -> str:
        """Mismo patrón que `OrdenClienteService._siguiente_folio()` (ADR-237/254/275):
        consecutivo GLOBAL (no reinicia por año/mes, `AAAA-MM` solo etiqueta el momento
        del alta), sin padding de ceros. Escanea el máximo existente por regex en vez de
        una secuencia de BD — mismo criterio, mismo costo, mismo riesgo de carrera
        (aceptado para este volumen, igual que en Órdenes)."""
        existentes = self._repo.db.scalars(select(Requisicion.numero_requisicion)).all()
        maximo = 0
        for numero in existentes:
            m = _FOLIO_REQUISICION_RE.match(numero)
            if m:
                maximo = max(maximo, int(m.group(1)))
        return f"RQ-{hoy.year}-{hoy.month:02d}-{maximo + 1}"

    def _enriquecer_folios(self, items: list[RequisicionRead]) -> None:
        """Folio de la factura de origen, en lote (columna "Folio" de la pantalla de
        consulta) — mismo patrón por lote que `_conteo_asignaciones` en
        `factura_afiliado.py`: evita N+1 contra las 3 tablas posibles."""
        from app.modules.facturacion.factura_afiliado import FacturaAfiliado
        from app.modules.facturacion.factura_agencia import FacturaAgencia
        from app.modules.facturacion.factura_vendedor import FacturaVendedor

        db = self._repo.db
        ids_af = {i.factura_afiliado_id for i in items if i.factura_afiliado_id is not None}
        ids_ag = {i.factura_agencia_id for i in items if i.factura_agencia_id is not None}
        ids_vd = {i.factura_vendedor_id for i in items if i.factura_vendedor_id is not None}

        folios_af: dict[uuid.UUID, str] = {}
        if ids_af:
            filas = db.execute(
                select(FacturaAfiliado.factura_afiliado_id, FacturaAfiliado.factura_emisora).where(
                    FacturaAfiliado.factura_afiliado_id.in_(ids_af)
                )
            ).all()
            folios_af = dict(filas)

        folios_ag: dict[uuid.UUID, str] = {}
        if ids_ag:
            filas = db.execute(
                select(
                    FacturaAgencia.factura_agencia_id, FacturaAgencia.folio_factura_agencia
                ).where(FacturaAgencia.factura_agencia_id.in_(ids_ag))
            ).all()
            folios_ag = dict(filas)

        folios_vd: dict[uuid.UUID, str] = {}
        if ids_vd:
            filas = db.execute(
                select(
                    FacturaVendedor.factura_vendedor_id, FacturaVendedor.folio_factura_vendedor
                ).where(FacturaVendedor.factura_vendedor_id.in_(ids_vd))
            ).all()
            folios_vd = dict(filas)

        for item in items:
            if item.factura_afiliado_id is not None:
                item.folio_factura_origen = folios_af.get(item.factura_afiliado_id)
            elif item.factura_agencia_id is not None:
                item.folio_factura_origen = folios_ag.get(item.factura_agencia_id)
            elif item.factura_vendedor_id is not None:
                item.folio_factura_origen = folios_vd.get(item.factura_vendedor_id)

    def _enriquecer_ordenes(self, items: list[RequisicionRead]) -> None:
        """Folios de las órdenes relacionadas, separados por coma (petición del
        usuario, columna "Órdenes" de la lista) — en lote, mismo criterio que
        `_enriquecer_folios`. Vía las 3 tablas puente (Agencia/Vendedor → `OrdenCliente`
        directo; Afiliado → `OrdenEstacion`, que ya trae su propio folio) o `orden_id`
        directo para `comision_agencia`."""
        from app.modules.facturacion.factura_afiliado import FacturaAfiliadoOrden
        from app.modules.facturacion.factura_agencia import FacturaAgenciaOrden
        from app.modules.facturacion.factura_vendedor import FacturaVendedorOrden
        from app.modules.ordenes.orden_cliente import OrdenCliente
        from app.modules.ordenes.orden_estacion import OrdenEstacion

        db = self._repo.db
        folios: dict[uuid.UUID, list[str]] = {i.requisicion_id: [] for i in items}

        ids_ag = {i.requisicion_id: i.factura_agencia_id for i in items if i.factura_agencia_id}
        if ids_ag:
            filas = db.execute(
                select(FacturaAgenciaOrden.factura_agencia_id, OrdenCliente.folio_orden)
                .join(OrdenCliente, OrdenCliente.orden_id == FacturaAgenciaOrden.orden_id)
                .where(FacturaAgenciaOrden.factura_agencia_id.in_(ids_ag.values()))
            ).all()
            por_factura: dict[uuid.UUID, list[str]] = {}
            for fid, folio in filas:
                por_factura.setdefault(fid, []).append(folio)
            for req_id, fid in ids_ag.items():
                folios[req_id] = por_factura.get(fid, [])

        ids_vd = {i.requisicion_id: i.factura_vendedor_id for i in items if i.factura_vendedor_id}
        if ids_vd:
            filas = db.execute(
                select(FacturaVendedorOrden.factura_vendedor_id, OrdenCliente.folio_orden)
                .join(OrdenCliente, OrdenCliente.orden_id == FacturaVendedorOrden.orden_id)
                .where(FacturaVendedorOrden.factura_vendedor_id.in_(ids_vd.values()))
            ).all()
            por_factura = {}
            for fid, folio in filas:
                por_factura.setdefault(fid, []).append(folio)
            for req_id, fid in ids_vd.items():
                folios[req_id] = por_factura.get(fid, [])

        ids_af = {i.requisicion_id: i.factura_afiliado_id for i in items if i.factura_afiliado_id}
        if ids_af:
            filas = db.execute(
                select(FacturaAfiliadoOrden.factura_afiliado_id, OrdenEstacion.folio_orden_estacion)
                .join(
                    OrdenEstacion,
                    OrdenEstacion.orden_estacion_id == FacturaAfiliadoOrden.orden_estacion_id,
                )
                .where(FacturaAfiliadoOrden.factura_afiliado_id.in_(ids_af.values()))
            ).all()
            por_factura = {}
            for fid, folio in filas:
                por_factura.setdefault(fid, []).append(folio)
            for req_id, fid in ids_af.items():
                folios[req_id] = por_factura.get(fid, [])

        ids_oc = {i.requisicion_id: i.orden_id for i in items if i.orden_id}
        if ids_oc:
            filas = db.execute(
                select(OrdenCliente.orden_id, OrdenCliente.folio_orden).where(
                    OrdenCliente.orden_id.in_(ids_oc.values())
                )
            ).all()
            folio_por_orden: dict[uuid.UUID, str] = dict(filas)
            for req_id, oid in ids_oc.items():
                if oid in folio_por_orden:
                    folios[req_id] = [folio_por_orden[oid]]

        for item in items:
            lista = folios.get(item.requisicion_id) or []
            item.ordenes_folios = ", ".join(lista) if lista else None

    def list(self, params: ListParams) -> Page[RequisicionRead]:
        pagina = super().list(params)
        self._enriquecer_folios(pagina.items)
        self._enriquecer_ordenes(pagina.items)
        return pagina

    def get(self, id_: Any) -> RequisicionRead:
        leida = super().get(id_)
        self._enriquecer_folios([leida])
        self._enriquecer_ordenes([leida])
        return leida

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

    def _validar_factura_disponible(
        self,
        estatus_actual: str,
        estatus_requerido: str,
        nombre: str,
        columna_fk: Any,
        factura_id: uuid.UUID,
    ) -> None:
        """Mismo criterio que antes solo aplicaban los combos `facturas_*_disponibles`:
        la factura debe estar `autorizada` y no tener ya otra Requisicion ligada (de
        cualquier estatus) — reforzado aquí porque el formulario embebido ya no pasa por
        esos combos."""
        if estatus_actual != estatus_requerido:
            raise DomainError(
                f"Solo se puede generar una requisición de una {nombre} '{estatus_requerido}'.",
                detalles={"estatus_actual": estatus_actual},
            )
        ya_usada = self._repo.db.scalar(
            select(Requisicion.requisicion_id).where(columna_fk == factura_id).limit(1)
        )
        if ya_usada is not None:
            raise ConflictError(
                f"Esa {nombre} ya tiene una requisición registrada.",
                detalles={"factura_id": str(factura_id)},
            )

    def create(self, data: RequisicionCreate, usuario: CurrentUser) -> RequisicionRead:
        from app.modules.catalogos.afiliado import Afiliado
        from app.modules.catalogos.agencia import Agencia
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import OrdenCliente
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        tipo = data.tipo_requisicion

        # ── Validación de las FKs obligatorias según el tipo (spec) ──
        # Petición del usuario: `factura_afiliado_id`/`factura_agencia_id` dejan de ser
        # opcionales para sus respectivos tipos (antes se podía capturar la requisición
        # sin saber todavía a cuál factura correspondía).
        if tipo == TipoRequisicion.PAGO_AFILIADO and (
            data.afiliado_id is None or data.factura_afiliado_id is None
        ):
            raise DomainError(
                "`pago_afiliado` requiere `afiliado_id` y `factura_afiliado_id`."
            )
        if tipo == TipoRequisicion.PAGO_AGENCIA and (
            data.agencia_id is None or data.factura_agencia_id is None
        ):
            raise DomainError(
                "`pago_agencia` requiere `agencia_id` y `factura_agencia_id`."
            )
        if tipo == TipoRequisicion.COMISION_VENDEDOR and (
            data.vendedor_comision_id is None or data.factura_vendedor_id is None
        ):
            raise DomainError(
                "`comision_vendedor` requiere `vendedor_comision_id` y `factura_vendedor_id`."
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

        # ── Elegibilidad + diferencia de márgenes con el afiliado (puede ser negativa) ──
        # ADR-282: antes solo el combo "disponibles" filtraba "autorizada + sin
        # requisición previa"; ahora el formulario embebido en cada pantalla de Factura
        # (Afiliado/Agencia/Vendedor) ya NO pasa por ese combo, así que la regla se
        # refuerza aquí, en el servicio — nunca confiar solo en lo que ya filtró el front.
        diferencia_afiliada = None
        if data.factura_afiliado_id is not None:
            from app.modules.facturacion.factura_afiliado import (
                EstatusFacturaProveedor,
                FacturaAfiliado,
            )

            factura_af = db.get(FacturaAfiliado, data.factura_afiliado_id)
            if factura_af is None:
                raise DomainError(
                    "La FacturaAfiliado indicada no existe.",
                    detalles={"factura_afiliado_id": str(data.factura_afiliado_id)},
                )
            self._validar_factura_disponible(
                factura_af.estatus_factura_afiliado,
                EstatusFacturaProveedor.AUTORIZADA.value,
                "FacturaAfiliado",
                Requisicion.factura_afiliado_id,
                data.factura_afiliado_id,
            )
            diferencia_afiliada = (
                data.monto_requisicion - Decimal(factura_af.total_factura_afiliado)
            ).quantize(CENTAVOS)

        if data.factura_agencia_id is not None:
            from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor
            from app.modules.facturacion.factura_agencia import FacturaAgencia

            factura_ag = db.get(FacturaAgencia, data.factura_agencia_id)
            if factura_ag is None:
                raise DomainError(
                    "La FacturaAgencia indicada no existe.",
                    detalles={"factura_agencia_id": str(data.factura_agencia_id)},
                )
            self._validar_factura_disponible(
                factura_ag.estatus_factura_agencia,
                EstatusFacturaProveedor.AUTORIZADA.value,
                "FacturaAgencia",
                Requisicion.factura_agencia_id,
                data.factura_agencia_id,
            )

        # Petición del usuario: valida que la FacturaVendedor exista, si se capturó —
        # mismo criterio que `factura_afiliado_id` arriba.
        if data.factura_vendedor_id is not None:
            from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor
            from app.modules.facturacion.factura_vendedor import FacturaVendedor

            factura_vd = db.get(FacturaVendedor, data.factura_vendedor_id)
            if factura_vd is None:
                raise DomainError(
                    "La FacturaVendedor indicada no existe.",
                    detalles={"factura_vendedor_id": str(data.factura_vendedor_id)},
                )
            self._validar_factura_disponible(
                factura_vd.estatus_factura_vendedor,
                EstatusFacturaProveedor.AUTORIZADA.value,
                "FacturaVendedor",
                Requisicion.factura_vendedor_id,
                data.factura_vendedor_id,
            )

        # ADR-283 (petición del usuario, con captura): una requisición que viene de una
        # factura de proveedor (pago_afiliado/pago_agencia/comision_vendedor) ya pasó por
        # la autorización de Dirección EN LA FACTURA (`_validar_factura_disponible` arriba
        # exige que esté `autorizada`) — pedirle a Dirección que la autorice OTRA VEZ aquí
        # es un paso redundante. Nace directo en `autorizada`, solo falta "Marcar pagada".
        # `comision_agencia` no tiene factura de origen (nada la autorizó antes): sigue
        # naciendo en `pendiente`, como siempre.
        tiene_factura_origen = (
            data.factura_afiliado_id is not None
            or data.factura_agencia_id is not None
            or data.factura_vendedor_id is not None
        )
        estatus_inicial = (
            EstatusRequisicion.AUTORIZADA.value
            if tiene_factura_origen
            else EstatusRequisicion.PENDIENTE.value
        )

        obj = Requisicion(
            requisicion_id=uuid4(),
            numero_requisicion=self._siguiente_numero_requisicion(date.today()),
            numero_oc_sap=data.numero_oc_sap,
            tipo_requisicion=tipo.value,
            estatus_requisicion=estatus_inicial,
            factura_afiliado_id=data.factura_afiliado_id,
            factura_agencia_id=data.factura_agencia_id,
            factura_vendedor_id=data.factura_vendedor_id,
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
        leida = self._to_read(obj)
        self._enriquecer_folios([leida])
        return leida

    # ── Combos "disponibles" del alta ─────────────────────────────────────────────
    def facturas_afiliado_disponibles(self) -> list[FacturaAfiliadoDisponibleRead]:
        """`FacturaAfiliado` `autorizada` que NINGUNA `Requisicion` (de cualquier
        estatus) tiene ligada todavía — petición del usuario: una factura ya usada en
        una requisición no debe volver a ofrecerse para otra nueva."""
        from app.modules.facturacion.factura_afiliado import (
            EstatusFacturaProveedor,
            FacturaAfiliado,
        )

        db = self._repo.db
        ya_usadas = select(Requisicion.factura_afiliado_id).where(
            Requisicion.factura_afiliado_id.is_not(None)
        )
        autorizada = EstatusFacturaProveedor.AUTORIZADA.value
        filas = db.scalars(
            select(FacturaAfiliado)
            .where(
                FacturaAfiliado.estatus_factura_afiliado == autorizada,
                FacturaAfiliado.factura_afiliado_id.not_in(ya_usadas),
            )
            .order_by(FacturaAfiliado.factura_emisora)
        ).all()
        return [FacturaAfiliadoDisponibleRead.model_validate(f) for f in filas]

    def facturas_agencia_disponibles(self) -> list[FacturaAgenciaDisponibleRead]:
        """Mismo criterio que `facturas_afiliado_disponibles`, para `FacturaAgencia`."""
        from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor
        from app.modules.facturacion.factura_agencia import FacturaAgencia

        db = self._repo.db
        ya_usadas = select(Requisicion.factura_agencia_id).where(
            Requisicion.factura_agencia_id.is_not(None)
        )
        filas = db.scalars(
            select(FacturaAgencia)
            .where(
                FacturaAgencia.estatus_factura_agencia == EstatusFacturaProveedor.AUTORIZADA.value,
                FacturaAgencia.factura_agencia_id.not_in(ya_usadas),
            )
            .order_by(FacturaAgencia.folio_factura_agencia)
        ).all()
        return [FacturaAgenciaDisponibleRead.model_validate(f) for f in filas]

    def facturas_vendedor_disponibles(self) -> list[FacturaVendedorDisponibleRead]:
        """Mismo criterio que `facturas_afiliado_disponibles`, para `FacturaVendedor`."""
        from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor
        from app.modules.facturacion.factura_vendedor import FacturaVendedor

        db = self._repo.db
        ya_usadas = select(Requisicion.factura_vendedor_id).where(
            Requisicion.factura_vendedor_id.is_not(None)
        )
        autorizada = EstatusFacturaProveedor.AUTORIZADA.value
        filas = db.scalars(
            select(FacturaVendedor)
            .where(
                FacturaVendedor.estatus_factura_vendedor == autorizada,
                FacturaVendedor.factura_vendedor_id.not_in(ya_usadas),
            )
            .order_by(FacturaVendedor.folio_factura_vendedor)
        ).all()
        return [FacturaVendedorDisponibleRead.model_validate(f) for f in filas]

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
        if (
            destino == EstatusRequisicion.CANCELADA.value
            and obj.estatus_requisicion == EstatusRequisicion.PAGADA.value
            and not (input_.motivo or "").strip()
        ):
            # Fix (petición del usuario): "Cancelar Pago a Proveedor" exige motivo —
            # cancelar desde pendiente/autorizada sigue sin pedirlo (flujo existente).
            raise DomainError(
                "El motivo de cancelación no puede estar vacío al cancelar una "
                "requisición ya pagada."
            )
        obj.estatus_requisicion = destino
        if destino == EstatusRequisicion.PAGADA.value:
            obj.fecha_pago_requisicion = input_.fecha_pago_requisicion or date.today()
            self._cerrar_factura_relacionada(obj, usuario)
        elif destino == EstatusRequisicion.CANCELADA.value:
            if input_.motivo:
                obj.motivo_cancelacion = input_.motivo
            # Fix (petición del usuario): cubre AMBOS orígenes con un solo mecanismo —
            # el botón "Cancelar" que ya existía para `autorizada` (ganaba la reversa
            # que le faltaba, gratis) y el nuevo "Cancelar Pago a Proveedor" desde
            # `pagada`. Revierte la factura de proveedor relacionada (si tiene) a
            # `recibida` y la vacía de órdenes — ver `_revertir_factura_relacionada`.
            self._revertir_factura_relacionada(obj)
        self._repo.db.commit()
        self._repo.db.refresh(obj)
        return self._to_read(obj)

    def _revertir_factura_relacionada(self, obj: Requisicion) -> None:
        """Al cancelar la Requisicion (desde `autorizada` O desde `pagada`): su factura
        de proveedor relacionada (`pago_afiliado`/`pago_agencia`/`comision_vendedor`;
        `comision_agencia` no tiene ninguna) vuelve a `recibida` y se vacía de órdenes —
        petición del usuario, decisión explícita: así ninguna orden puede quedar
        asignada a la vez a esta factura (reactivada) Y a una factura nueva.

        "Tonta" — no valida nada, reusa el método `revertir_a_recibida` de cada
        servicio F2 (mismo criterio que `revertir_facturacion`/`revertir_cobro` en
        F1/F2: la máquina de estados hacia atrás no pasa por `.transicionar()`, que solo
        conoce transiciones hacia ADELANTE). Sin `commit` propio — misma sesión que
        `transicionar()`.
        """
        if obj.factura_afiliado_id is not None:
            from app.modules.facturacion.factura_afiliado import (
                FacturaAfiliado,
                FacturaAfiliadoRepository,
                FacturaAfiliadoService,
            )

            FacturaAfiliadoService(
                FacturaAfiliadoRepository(self._repo.db, FacturaAfiliado)
            ).revertir_a_recibida(obj.factura_afiliado_id)
        elif obj.factura_agencia_id is not None:
            from app.modules.facturacion.factura_agencia import (
                FacturaAgencia,
                FacturaAgenciaRepository,
                FacturaAgenciaService,
            )

            FacturaAgenciaService(
                FacturaAgenciaRepository(self._repo.db, FacturaAgencia)
            ).revertir_a_recibida(obj.factura_agencia_id)
        elif obj.factura_vendedor_id is not None:
            from app.modules.facturacion.factura_vendedor import (
                FacturaVendedor,
                FacturaVendedorRepository,
                FacturaVendedorService,
            )

            FacturaVendedorService(
                FacturaVendedorRepository(self._repo.db, FacturaVendedor)
            ).revertir_a_recibida(obj.factura_vendedor_id)

    def _cerrar_factura_relacionada(self, obj: Requisicion, usuario: CurrentUser) -> None:
        """Petición del usuario: al pagar la requisición, su factura de proveedor
        relacionada pasa a "pagada" también — `pago_afiliado`/`pago_agencia`/
        `comision_vendedor` (si trae `factura_vendedor_id`). `comision_agencia` no tiene
        ninguna factura que cerrar (es un pago puro, sin ese enlace).

        Reusa el `.transicionar(..., "pagada", ...)` de cada módulo de facturación en vez
        de poner el estatus a mano: ya valida la transición (`autorizada → pagada`) y es
        idempotente — si por alguna razón la factura ya estuviera "pagada" (p.ej. cerrada
        por otro canal), no hace nada ni truena. Comparten LA MISMA sesión de BD
        (`self._repo.db`), así que el `commit()` de cada una de ellas también deja listo
        el cambio de `obj.estatus_requisicion` de arriba — si la factura NO estuviera en
        un estado del que se pueda pasar a "pagada" (`StateTransitionError`), esto corre
        ANTES de cualquier commit, así que nada queda a medias: ni la requisición ni la
        factura se marcan pagadas.
        """
        if obj.factura_afiliado_id is not None:
            from app.modules.facturacion.factura_afiliado import (
                EstatusFacturaProveedor,
                FacturaAfiliado,
                FacturaAfiliadoRepository,
                FacturaAfiliadoService,
            )

            repo_af = FacturaAfiliadoRepository(self._repo.db, FacturaAfiliado)
            FacturaAfiliadoService(repo_af).transicionar(
                obj.factura_afiliado_id, EstatusFacturaProveedor.PAGADA.value, usuario
            )
        elif obj.factura_agencia_id is not None:
            from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor
            from app.modules.facturacion.factura_agencia import (
                FacturaAgencia,
                FacturaAgenciaRepository,
                FacturaAgenciaService,
            )

            repo_ag = FacturaAgenciaRepository(self._repo.db, FacturaAgencia)
            FacturaAgenciaService(repo_ag).transicionar(
                obj.factura_agencia_id, EstatusFacturaProveedor.PAGADA.value, usuario
            )
        elif obj.factura_vendedor_id is not None:
            from app.modules.facturacion.factura_afiliado import EstatusFacturaProveedor
            from app.modules.facturacion.factura_vendedor import (
                FacturaVendedor,
                FacturaVendedorRepository,
                FacturaVendedorService,
            )

            repo_vd = FacturaVendedorRepository(self._repo.db, FacturaVendedor)
            FacturaVendedorService(repo_vd).transicionar(
                obj.factura_vendedor_id, EstatusFacturaProveedor.PAGADA.value, usuario
            )

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
    q: str | None = Query(
        None,
        description=(
            "Busca en número de requisición, OC de SAP, o el folio de la factura "
            "de origen (Afiliado/Agencia/Vendedor)"
        ),
    ),
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


@router.get("/facturas-afiliado-disponibles", response_model=list[FacturaAfiliadoDisponibleRead])
def listar_facturas_afiliado_disponibles(
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> list[FacturaAfiliadoDisponibleRead]:
    return svc.facturas_afiliado_disponibles()


@router.get("/facturas-agencia-disponibles", response_model=list[FacturaAgenciaDisponibleRead])
def listar_facturas_agencia_disponibles(
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> list[FacturaAgenciaDisponibleRead]:
    return svc.facturas_agencia_disponibles()


@router.get("/facturas-vendedor-disponibles", response_model=list[FacturaVendedorDisponibleRead])
def listar_facturas_vendedor_disponibles(
    usuario: CurrentUser = Depends(requiere_permiso("pagos:leer")),
    svc: RequisicionService = Depends(get_requisicion_service),
) -> list[FacturaVendedorDisponibleRead]:
    return svc.facturas_vendedor_disponibles()


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
