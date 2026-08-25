"""OrdenCliente (F1) — orden de transmisión recibida del anunciante o su agencia.

36 campos de la spec BD v2 ("FASE 1 — Órdenes de Transmisión") + 3 extensiones aditivas
aprobadas:

- **`estatus_orden`** usa el vocabulario de la spec (`recibida ... cancelada`), NO el del
  prototipo HTML aprobado (que usa un vocabulario "v5" distinto, construido para la demo
  de pantallas). El mapeo entre ambos vive en el adaptador del frontend (Tanda 4), no aquí.
- **`porcentaje_comision_*_snap`** (ADR-029): la spec NO los tiene, pero el propio catálogo
  Vendedor describe su `porcentaje_comision_default` como "sobreescribible por orden" — la
  spec contempla el override, solo le faltaba la columna. Se fijan al momento de la venta y
  no cambian si el catálogo cambia después.
- **Campos de cierre** (`odc_cerrada_ref`, `carta_conciliacion_ref`,
  `cierre_sin_odc_cerrada`, `cierre_sin_carta_conciliacion`, `fecha_cierre` — ADR-034): no
  están en la spec. Dos BOOLEAN en vez de un arreglo/JSON de "documentos faltantes" (spec
  BD v2 no usa JSON; F4 necesita reportar sobre esto). Se fijan una sola vez, al cerrar —
  no se recalculan si alguien sube el documento después.
- **`total_dias_campania`, `subtotal`, `iva`, `total`, `anio_venta`, `mes_venta`** son
  Calculado (spec): el SERVICIO los calcula con `Decimal` y los persiste (mismo patrón que
  `TarifaPlaza.tarifa_neta`) — nunca se aceptan del cliente ni se recalculan on-the-fly aquí.

Checklist de Vo.Bo. (transición previa a `capturada`, no está en la spec porque es
posterior): tabla hija `OrdenClienteVoBoItem`, NO JSON (ADR-033) — F4 necesita reportar
por ítem, y una columna BIT por ítem no escala si el checklist cambia.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    Unicode,
    UniqueConstraint,
    or_,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.config import settings
from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.errors import DomainError, NotFoundError, PermissionDeniedError, StateTransitionError
from app.core.security import Area, CurrentUser, requiere_permiso
from app.modules.catalogos.agencia import Agencia
from app.modules.catalogos.anunciante import Anunciante, Marca
from app.modules.catalogos.categoria import Categoria
from app.modules.catalogos.contrato import Contrato
from app.modules.catalogos.empresa_facturadora import EmpresaFacturadora
from app.modules.catalogos.vendedor import Vendedor
from app.modules.usuarios.lookup import resolver_usuario_id
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.enums import DuracionSpot
from app.shared.schemas import ListParams, Page

CENTAVOS = Decimal("0.01")
IVA_RATE = Decimal(str(settings.iva_rate))

CAMPOS_COMISION: tuple[str, ...] = (
    "porcentaje_comision_vendedor_principal_snap",
    "porcentaje_comision_vendedor_secundario_snap",
    "porcentaje_comision_agencia_snap",
)


# ── Estados (spec BD v2, NO el vocabulario "v5" del prototipo — ver docstring) ──────────
class EstatusOrden(StrEnum):
    RECIBIDA = "recibida"
    CAPTURADA = "capturada"
    EN_TRANSMISION = "en_transmision"
    EN_VERIFICACION = "en_verificacion"
    ORDEN_CERRADA = "orden_cerrada"
    FACTURADA = "facturada"
    COBRADA = "cobrada"
    CANCELADA = "cancelada"


class EstatusPago(StrEnum):
    """Compartido por `estatus_pago_afiliado` y `estatus_pago_agencia` (spec)."""

    PENDIENTE = "pendiente"
    EN_REVISION = "en_revision"
    PAGADO = "pagado"


# Estados "congelados" (equivalente en spec de `FROZEN_STATES` del frontend, Tanda 5):
# una vez aquí, `PUT` rechaza cualquier edición — los % de comisión, específicamente,
# solo se ajustan por `PATCH /clientes/{id}/comisiones` (Dirección/Admin, ver docstring
# del servicio) incluso ANTES de llegar a estos estados.
FROZEN_STATES_OC: frozenset[str] = frozenset(
    {EstatusOrden.ORDEN_CERRADA.value, EstatusOrden.FACTURADA.value, EstatusOrden.COBRADA.value}
)


# Los 10 ítems del checklist Vo.Bo. (PO §2) — claves fijas, NO configurables por el usuario.
ITEMS_VOBO: tuple[str, ...] = (
    "razon_social",
    "plaza",
    "emisora",
    "duracion",
    "tarifa",
    "distribucion",
    "horario",
    "importes",
    "audio",
    "odc_firmada",
)


# ── Modelo ──────────────────────────────────────────────────────────────────────
class OrdenCliente(Base):
    __tablename__ = "orden_cliente"
    __table_args__ = (
        CheckConstraint(
            "estatus_orden IN ('recibida', 'capturada', 'en_transmision', "
            "'en_verificacion', 'orden_cerrada', 'facturada', 'cobrada', 'cancelada')",
            name="ck_orden_cliente_estatus_orden",
        ),
        CheckConstraint(
            "estatus_pago_afiliado IN ('pendiente', 'en_revision', 'pagado')",
            name="ck_orden_cliente_estatus_pago_afiliado",
        ),
        CheckConstraint(
            "estatus_pago_agencia IN ('pendiente', 'en_revision', 'pagado')",
            name="ck_orden_cliente_estatus_pago_agencia",
        ),
        CheckConstraint(
            "duracion_spot IN ('20s', '30s', '60s', 'mencion')",
            name="ck_orden_cliente_duracion_spot",
        ),
        CheckConstraint(
            "fecha_fin_campania >= fecha_inicio_campania",
            name="ck_orden_cliente_fechas_campania",
        ),
        CheckConstraint(
            "porcentaje_comision_vendedor_principal_snap IS NULL OR "
            "(porcentaje_comision_vendedor_principal_snap >= 0 AND "
            "porcentaje_comision_vendedor_principal_snap <= 100)",
            name="ck_orden_cliente_comision_vp_snap",
        ),
        CheckConstraint(
            "porcentaje_comision_vendedor_secundario_snap IS NULL OR "
            "(porcentaje_comision_vendedor_secundario_snap >= 0 AND "
            "porcentaje_comision_vendedor_secundario_snap <= 100)",
            name="ck_orden_cliente_comision_vs_snap",
        ),
        CheckConstraint(
            "porcentaje_comision_agencia_snap IS NULL OR "
            "(porcentaje_comision_agencia_snap >= 0 AND porcentaje_comision_agencia_snap <= 100)",
            name="ck_orden_cliente_comision_ag_snap",
        ),
        # Auditoría de migración a RDS (F1, Tanda 4): faltaban CHECK sobre montos y
        # cantidades — inconsistente con `orden_estacion_dia` (spots_* >= 0) y
        # `orden_estacion` (rango del %) en la MISMA migración. Sistema financiero: nada
        # impedía un precio_unitario negativo ni un total en cero/negativo.
        CheckConstraint("precio_unitario >= 0", name="ck_orden_cliente_precio_unitario"),
        CheckConstraint("total_spots > 0", name="ck_orden_cliente_total_spots"),
        CheckConstraint("subtotal >= 0", name="ck_orden_cliente_subtotal"),
        CheckConstraint("iva >= 0", name="ck_orden_cliente_iva"),
        CheckConstraint("total >= 0", name="ck_orden_cliente_total"),
        CheckConstraint("total_dias_campania >= 1", name="ck_orden_cliente_total_dias_campania"),
        CheckConstraint("mes_venta >= 1 AND mes_venta <= 12", name="ck_orden_cliente_mes_venta"),
    )

    orden_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    folio_orden: Mapped[str] = mapped_column(Unicode(20), unique=True, index=True)
    numero_orden_cliente: Mapped[str] = mapped_column(Unicode(50))
    fecha_venta: Mapped[date] = mapped_column(fecha_sql())
    # Calculado (spec) — persistido por el servicio, no por SQL Server/SQLite.
    anio_venta: Mapped[int] = mapped_column()
    mes_venta: Mapped[int] = mapped_column()

    empresa_facturadora_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "empresa_facturadora.empresa_facturadora_id",
            name="fk_orden_cliente_empresa_facturadora",
            ondelete="NO ACTION",
        ),
        index=True,
    )
    vendedor_principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "vendedor.vendedor_id", name="fk_orden_cliente_vendedor_principal", ondelete="NO ACTION"
        ),
        index=True,
    )
    vendedor_secundario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "vendedor.vendedor_id",
            name="fk_orden_cliente_vendedor_secundario",
            ondelete="NO ACTION",
        ),
        default=None,
    )
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "anunciante.anunciante_id", name="fk_orden_cliente_anunciante", ondelete="NO ACTION"
        ),
        index=True,
    )
    # Filtro real de `OrdenClienteRepository._apply_filters` (agencia_id/contrato_id) —
    # indexados por eso, no por integridad referencial (aquí no hay DELETE físico).
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agencia.agencia_id", name="fk_orden_cliente_agencia", ondelete="NO ACTION"),
        default=None,
        index=True,
    )
    contrato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contrato.contrato_id", name="fk_orden_cliente_contrato", ondelete="NO ACTION"),
        default=None,
        index=True,
    )
    marca_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("marca.marca_id", name="fk_orden_cliente_marca", ondelete="NO ACTION"),
        default=None,
    )
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "categoria.categoria_id", name="fk_orden_cliente_categoria", ondelete="NO ACTION"
        ),
        default=None,
    )

    producto: Mapped[str | None] = mapped_column(Unicode(200), default=None)
    direccion_facturacion: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    facturacion_directa_cliente: Mapped[bool] = mapped_column(default=False)
    afiliado_factura_directo_al_cliente: Mapped[bool] = mapped_column(default=False)

    fecha_inicio_campania: Mapped[date] = mapped_column(fecha_sql())
    fecha_fin_campania: Mapped[date] = mapped_column(fecha_sql())
    # Calculado (spec): = DATEDIFF(fin, inicio) + 1. Persistido por el servicio.
    total_dias_campania: Mapped[int] = mapped_column()

    duracion_spot: Mapped[str] = mapped_column(Unicode(10))
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_spots: Mapped[int] = mapped_column()
    # Calculados (spec): subtotal = total_spots * precio_unitario; iva = subtotal * IVA_RATE;
    # total = subtotal + iva. Persistidos por el servicio, nunca aceptados del cliente.
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    observaciones_predefinidas: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    observaciones_libres: Mapped[str | None] = mapped_column(texto_largo(), default=None)

    # Indexado: filtro real de `OrdenClienteRepository._apply_filters` (pantallas de lista).
    estatus_orden: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusOrden.RECIBIDA.value, index=True
    )
    estatus_pago_afiliado: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusPago.PENDIENTE.value
    )
    estatus_pago_agencia: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusPago.PENDIENTE.value
    )

    archivo_orden_original_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_orden_cliente_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )

    # ── Extensión aditiva: comisiones snapshot (ADR-029) ──────────────────────────
    porcentaje_comision_vendedor_principal_snap: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    porcentaje_comision_vendedor_secundario_snap: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    porcentaje_comision_agencia_snap: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )

    # ── Extensión aditiva: campos de cierre (ADR-034) ─────────────────────────────
    odc_cerrada_ref: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    carta_conciliacion_ref: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    # Snapshot de lo que faltaba AL MOMENTO del cierre (no se recalcula si se sube después).
    cierre_sin_odc_cerrada: Mapped[bool] = mapped_column(default=False)
    cierre_sin_carta_conciliacion: Mapped[bool] = mapped_column(default=False)
    fecha_cierre: Mapped[date | None] = mapped_column(fecha_sql(), default=None)


# ── Checklist de Vo.Bo. (ADR-033) ────────────────────────────────────────────────
class OrdenClienteVoBoItem(Base):
    __tablename__ = "orden_cliente_vobo_item"
    __table_args__ = (
        CheckConstraint(
            "item_clave IN ('razon_social', 'plaza', 'emisora', 'duracion', 'tarifa', "
            "'distribucion', 'horario', 'importes', 'audio', 'odc_firmada')",
            name="ck_orden_cliente_vobo_item_clave",
        ),
        UniqueConstraint("orden_id", "item_clave", name="uq_orden_cliente_vobo_item_orden_clave"),
    )

    orden_cliente_vobo_item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # Sin `index=True`: sería redundante con `uq_orden_cliente_vobo_item_orden_clave`
    # (UNIQUE sobre orden_id+item_clave) — SQL Server usa ese índice único como columna
    # líder para consultas por `orden_id` solo. Auditoría de migración a RDS, Tanda 4:
    # costo de escritura sin beneficio de lectura.
    orden_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_cliente.orden_id", name="fk_orden_cliente_vobo_item_orden", ondelete="NO ACTION"
        )
    )
    item_clave: Mapped[str] = mapped_column(Unicode(30))
    completado: Mapped[bool] = mapped_column(default=False)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuario.usuario_id", name="fk_orden_cliente_vobo_item_usuario", ondelete="NO ACTION"
        ),
        default=None,
    )
    fecha_completado: Mapped[datetime | None] = mapped_column(datetime2(), default=None)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas de lectura (Tanda 3 — API de lectura; Create/Update llegan en Tanda 5) ────
class OrdenClienteRead(BaseModel):
    """Espejo de las columnas reales de `OrdenCliente` (sin `CatalogoReadBase`: esta
    entidad no tiene `activo`, usa la máquina de estados `estatus_orden`)."""

    model_config = ConfigDict(from_attributes=True)

    orden_id: uuid.UUID
    folio_orden: str
    numero_orden_cliente: str
    fecha_venta: date
    anio_venta: int
    mes_venta: int
    empresa_facturadora_id: uuid.UUID
    vendedor_principal_id: uuid.UUID
    vendedor_secundario_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID
    agencia_id: uuid.UUID | None = None
    contrato_id: uuid.UUID | None = None
    marca_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    producto: str | None = None
    direccion_facturacion: str | None = None
    facturacion_directa_cliente: bool
    afiliado_factura_directo_al_cliente: bool
    fecha_inicio_campania: date
    fecha_fin_campania: date
    total_dias_campania: int
    duracion_spot: str
    precio_unitario: Decimal
    total_spots: int
    subtotal: Decimal
    iva: Decimal
    total: Decimal
    observaciones_predefinidas: str | None = None
    observaciones_libres: str | None = None
    estatus_orden: EstatusOrden
    estatus_pago_afiliado: EstatusPago
    estatus_pago_agencia: EstatusPago
    archivo_orden_original_path: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    porcentaje_comision_vendedor_principal_snap: Decimal | None = None
    porcentaje_comision_vendedor_secundario_snap: Decimal | None = None
    porcentaje_comision_agencia_snap: Decimal | None = None
    odc_cerrada_ref: str | None = None
    carta_conciliacion_ref: str | None = None
    cierre_sin_odc_cerrada: bool
    cierre_sin_carta_conciliacion: bool
    fecha_cierre: date | None = None

    # Montos/porcentajes como STRING para preservar precisión Decimal (ADR-015 E-4).
    @field_serializer(
        "precio_unitario",
        "subtotal",
        "iva",
        "total",
        "porcentaje_comision_vendedor_principal_snap",
        "porcentaje_comision_vendedor_secundario_snap",
        "porcentaje_comision_agencia_snap",
    )
    def _serializa_decimal(self, valor: Decimal | None) -> str | None:
        return None if valor is None else str(valor)


class OrdenClienteVoBoItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden_cliente_vobo_item_id: uuid.UUID
    orden_id: uuid.UUID
    item_clave: str
    completado: bool
    usuario_id: uuid.UUID | None = None
    fecha_completado: datetime | None = None


class OrdenClienteListParams(ListParams):
    """`ListParams` + filtros propios. Hereda `activo`, pero NUNCA se expone como query
    param (el router no lo declara): `OrdenCliente` no tiene baja lógica, usa la máquina
    de estados `estatus_orden`. Se hereda solo por compatibilidad de tipo con
    `BaseRepository`/`BaseService`. Razonamiento completo — incluyendo el hueco real de
    que `cancelada` hoy no es alcanzable por ningún endpoint — en ADR-035
    (docs/arquitectura.md)."""

    estatus_orden: EstatusOrden | None = None
    anunciante_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    vendedor_principal_id: uuid.UUID | None = None
    contrato_id: uuid.UUID | None = None


# ── Schemas de escritura (Tanda 5) ────────────────────────────────────────────────
class OrdenClienteCreate(BaseModel):
    numero_orden_cliente: str = Field(min_length=1, max_length=50)
    fecha_venta: date
    empresa_facturadora_id: uuid.UUID
    vendedor_principal_id: uuid.UUID
    vendedor_secundario_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID
    agencia_id: uuid.UUID | None = None
    contrato_id: uuid.UUID | None = None
    marca_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    producto: str | None = Field(default=None, max_length=200)
    direccion_facturacion: str | None = Field(default=None, max_length=2000)
    facturacion_directa_cliente: bool = False
    afiliado_factura_directo_al_cliente: bool = False
    # PDF/imagen de la orden original recibida del cliente (spec BD v2) — clave del
    # almacenamiento (ver `app/modules/ordenes/adjuntos.py`), no una ruta de disco pese
    # al nombre heredado de la spec.
    archivo_orden_original_path: str | None = Field(default=None, max_length=500)
    fecha_inicio_campania: date
    fecha_fin_campania: date
    duracion_spot: DuracionSpot
    precio_unitario: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    total_spots: int = Field(gt=0)
    # PARÁMETROS SENSIBLES (snapshot, ADR-029): captura inicial libre por Ventas — no es
    # "cambio" (no requiere motivo); editarlos DESPUÉS sí lo es (ver
    # `OrdenClienteComisionesUpdate`, Dirección/Admin únicamente).
    porcentaje_comision_vendedor_principal_snap: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    porcentaje_comision_vendedor_secundario_snap: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    porcentaje_comision_agencia_snap: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    observaciones_predefinidas: str | None = Field(default=None, max_length=1000)
    observaciones_libres: str | None = Field(default=None, max_length=1000)
    # Checklist de Vo.Bo. (ADR-033): qué ítems ya vienen marcados al capturar (los no
    # listados nacen `completado=False`). `dar_vobo=True` intenta la transición
    # recibida→capturada en el MISMO alta (409 si faltan ítems) — atajo para el caso
    # común de "checklist ya completo al guardar" (mismo flujo que `OrdenClienteForm`).
    revision_checklist: dict[str, bool] | None = None
    dar_vobo: bool = False

    @model_validator(mode="after")
    def _valida_fechas(self) -> OrdenClienteCreate:
        if self.fecha_inicio_campania < date.today():
            raise ValueError("fecha_inicio_campania no puede ser una fecha pasada.")
        if self.fecha_fin_campania < self.fecha_inicio_campania:
            raise ValueError("fecha_fin_campania debe ser mayor o igual que fecha_inicio_campania.")
        return self


class OrdenClienteUpdate(BaseModel):
    """Edición normal (Ventas, `ordenes:editar`) — 409 si la orden está congelada
    (`FROZEN_STATES_OC`). Los 3 % de comisión NO viven aquí (ver Hallazgo 2 del plan de
    la Tanda 5): `extra="forbid"` para RECHAZAR explícitamente si alguien los manda por
    error, en vez de ignorarlos en silencio."""

    model_config = ConfigDict(extra="forbid")

    numero_orden_cliente: str | None = Field(default=None, min_length=1, max_length=50)
    fecha_venta: date | None = None
    empresa_facturadora_id: uuid.UUID | None = None
    vendedor_principal_id: uuid.UUID | None = None
    vendedor_secundario_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
    contrato_id: uuid.UUID | None = None
    marca_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    producto: str | None = Field(default=None, max_length=200)
    direccion_facturacion: str | None = Field(default=None, max_length=2000)
    facturacion_directa_cliente: bool | None = None
    afiliado_factura_directo_al_cliente: bool | None = None
    archivo_orden_original_path: str | None = Field(default=None, max_length=500)
    fecha_inicio_campania: date | None = None
    fecha_fin_campania: date | None = None
    duracion_spot: DuracionSpot | None = None
    precio_unitario: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    total_spots: int | None = Field(default=None, gt=0)
    observaciones_predefinidas: str | None = Field(default=None, max_length=1000)
    observaciones_libres: str | None = Field(default=None, max_length=1000)


class OrdenClienteComisionesUpdate(BaseModel):
    """`PATCH /clientes/{id}/comisiones` — único canal para tocar los 3 % de comisión
    DESPUÉS de la captura inicial (propuesta §9: "el % de comisión de un vendedor puede
    editarse solo por Dirección"). Siempre auditado; `motivo_cambio` requerido si algo
    de verdad cambia (mismo patrón que `ContratoUpdate`)."""

    porcentaje_comision_vendedor_principal_snap: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    porcentaje_comision_vendedor_secundario_snap: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    porcentaje_comision_agencia_snap: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    motivo_cambio: str | None = Field(default=None, max_length=500)


class VoBoToggleIn(BaseModel):
    completado: bool


class OrdenClienteCerrarIn(BaseModel):
    """`POST /clientes/{id}/cerrar`. Los % de comisión NO se mandan aquí: el servicio
    rellena cualquiera que siga `None` con el default vigente del catálogo (Vendedor/
    Agencia) — es completar un vacío, no una edición, así que no se audita ni exige
    `motivo_cambio` (a diferencia de `OrdenClienteComisionesUpdate`)."""

    odc_cerrada_ref: str | None = Field(default=None, max_length=500)
    carta_conciliacion_ref: str | None = Field(default=None, max_length=500)


# ── Repositorio ───────────────────────────────────────────────────────────────
class OrdenClienteRepository(BaseRepository[OrdenCliente]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: filtraría por `model.activo`, columna que
        # OrdenCliente no tiene (usa estatus_orden, no baja lógica) — ver OrdenClienteListParams.
        q = (getattr(params, "q", None) or "").strip()
        if q:
            patron = f"%{q}%"
            stmt = stmt.where(
                or_(
                    OrdenCliente.folio_orden.ilike(patron),
                    OrdenCliente.numero_orden_cliente.ilike(patron),
                )
            )
        estatus = getattr(params, "estatus_orden", None)
        if estatus is not None:
            stmt = stmt.where(OrdenCliente.estatus_orden == EstatusOrden(estatus).value)
        for campo in ("anunciante_id", "agencia_id", "vendedor_principal_id", "contrato_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(OrdenCliente, campo) == valor)
        return stmt

    def listar_vobo(self, orden_id: uuid.UUID) -> Sequence[OrdenClienteVoBoItem]:
        stmt = (
            select(OrdenClienteVoBoItem)
            .where(OrdenClienteVoBoItem.orden_id == orden_id)
            .order_by(OrdenClienteVoBoItem.item_clave)
        )
        return self.db.scalars(stmt).all()


_FOLIO_RE = re.compile(r"^OC-\d{4}-(\d+)$")


# ── Servicio ──────────────────────────────────────────────────────────────────
class OrdenClienteService(
    BaseService[OrdenCliente, OrdenClienteCreate, OrdenClienteUpdate, OrdenClienteRead]
):
    """`create`/`update` cubren la captura y edición normales (Ventas, `ordenes:editar`
    implica también `crear`). Las 4 transiciones de la máquina de estados (Vo.Bo.,
    cierre) y el canal sensible de comisiones son métodos dedicados, no genéricos —
    cada uno con su propia regla de negocio (ver docstring de cada uno)."""

    read_schema = OrdenClienteRead
    entidad = "OrdenCliente"

    def __init__(self, repo: OrdenClienteRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def vobo(self, orden_id: uuid.UUID) -> Sequence[OrdenClienteVoBoItemRead]:
        self._get_or_404(orden_id)
        return [
            OrdenClienteVoBoItemRead.model_validate(item)
            for item in self._repo.listar_vobo(orden_id)
        ]

    def historial_comisiones(self, orden_id: uuid.UUID) -> Sequence[audit.LogCambioParametroRead]:
        """Historial de cambios a los % de comisión snapshot (ADR-029), más reciente
        primero — mismo mecanismo de `LogCambioParametro` que usan los catálogos."""
        return self.historial(orden_id)

    # ── helpers de validación ────────────────────────────────────────────────────
    def _verificar_fk(self, db: Session, modelo: type, id_: uuid.UUID, nombre: str) -> Any:
        obj = db.get(modelo, id_)
        if obj is None:
            raise NotFoundError(f"{nombre} no encontrado.", detalles={"id": str(id_)})
        return obj

    def _siguiente_folio(self, db: Session, anio: int) -> str:
        """Correlativo GLOBAL (no reinicia por año) — mismo criterio que `nextFolioOC`
        del frontend: el número sigue subiendo aunque cambie el año de venta."""
        existentes = db.scalars(select(OrdenCliente.folio_orden)).all()
        maximo = 40
        for folio in existentes:
            m = _FOLIO_RE.match(folio)
            if m:
                maximo = max(maximo, int(m.group(1)))
        return f"OC-{anio}-{maximo + 1:04d}"

    def _validar_fks_y_relaciones(self, db: Session, payload: dict[str, Any]) -> None:
        if "empresa_facturadora_id" in payload:
            self._verificar_fk(
                db, EmpresaFacturadora, payload["empresa_facturadora_id"], "EmpresaFacturadora"
            )
        if "vendedor_principal_id" in payload:
            self._verificar_fk(db, Vendedor, payload["vendedor_principal_id"], "Vendedor")
        if payload.get("vendedor_secundario_id") is not None:
            self._verificar_fk(db, Vendedor, payload["vendedor_secundario_id"], "Vendedor")
        if "anunciante_id" in payload:
            self._verificar_fk(db, Anunciante, payload["anunciante_id"], "Anunciante")
        if payload.get("agencia_id") is not None:
            self._verificar_fk(db, Agencia, payload["agencia_id"], "Agencia")
        if payload.get("categoria_id") is not None:
            self._verificar_fk(db, Categoria, payload["categoria_id"], "Categoria")

    def _validar_contrato_marca(
        self, db: Session, payload: dict[str, Any], anunciante_id: uuid.UUID
    ) -> None:
        if payload.get("contrato_id") is not None:
            contrato = self._verificar_fk(db, Contrato, payload["contrato_id"], "Contrato")
            if contrato.anunciante_id != anunciante_id:
                raise DomainError(
                    "El contrato indicado no pertenece al anunciante de la orden.",
                    detalles={
                        "contrato_id": str(payload["contrato_id"]),
                        "anunciante_id": str(anunciante_id),
                    },
                )
        if payload.get("marca_id") is not None:
            marca = self._verificar_fk(db, Marca, payload["marca_id"], "Marca")
            if marca.anunciante_id != anunciante_id:
                raise DomainError(
                    "La marca indicada no pertenece al anunciante de la orden.",
                    detalles={
                        "marca_id": str(payload["marca_id"]),
                        "anunciante_id": str(anunciante_id),
                    },
                )

    # ── alta ──────────────────────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        db = self._repo.db
        self._validar_fks_y_relaciones(db, payload)
        self._validar_contrato_marca(db, payload, payload["anunciante_id"])

        fecha_venta = payload["fecha_venta"]
        payload["anio_venta"] = fecha_venta.year
        payload["mes_venta"] = fecha_venta.month
        payload["total_dias_campania"] = (
            payload["fecha_fin_campania"] - payload["fecha_inicio_campania"]
        ).days + 1
        subtotal = (Decimal(payload["total_spots"]) * payload["precio_unitario"]).quantize(CENTAVOS)
        iva = (subtotal * IVA_RATE).quantize(CENTAVOS)
        payload["subtotal"] = subtotal
        payload["iva"] = iva
        payload["total"] = subtotal + iva

        payload["orden_id"] = uuid4()
        payload["created_by"] = resolver_usuario_id(db, usuario.username)
        payload["folio_orden"] = self._siguiente_folio(db, fecha_venta.year)
        payload["estatus_pago_afiliado"] = EstatusPago.PENDIENTE.value
        payload["estatus_pago_agencia"] = EstatusPago.PENDIENTE.value

    def create(self, data: OrdenClienteCreate, usuario: CurrentUser) -> OrdenClienteRead:
        payload = data.model_dump()
        checklist = payload.pop("revision_checklist", None) or {}
        dar_vobo = payload.pop("dar_vobo", False)

        self._pre_create(payload, usuario)

        if dar_vobo:
            faltantes = [k for k in ITEMS_VOBO if not checklist.get(k, False)]
            if faltantes:
                raise StateTransitionError(
                    "No se puede dar Vo.Bo. al crear: faltan ítems del checklist.",
                    detalles={"faltantes": faltantes},
                )
            payload["estatus_orden"] = EstatusOrden.CAPTURADA.value
        else:
            payload["estatus_orden"] = EstatusOrden.RECIBIDA.value

        obj = self.repo.create(payload)
        db = self._repo.db

        for item_clave in ITEMS_VOBO:
            completado = bool(checklist.get(item_clave, False))
            db.add(
                OrdenClienteVoBoItem(
                    orden_cliente_vobo_item_id=uuid4(),
                    orden_id=obj.orden_id,
                    item_clave=item_clave,
                    completado=completado,
                    usuario_id=obj.created_by if completado else None,
                    fecha_completado=datetime.now() if completado else None,
                )
            )
        # Comisiones capturadas al vuelo: es ALTA, no "cambio" — sin motivo (mismo
        # espíritu que `Contrato._pre_create` con `porcentaje_comision_contrato`).
        # NOTA: se llama a `audit.log_cambio_parametro` directo, NO a
        # `registrar_cambio_sensible` — esa función exige `field_permissions.verificar`
        # (hoy hardcodeado a "solo Admin", el placeholder de F0), que bloquearía a
        # Ventas. La autorización real de este campo ya la decide el ÁREA del endpoint
        # (`ordenes:crear` = Ventas) y, después de la captura, el chequeo explícito de
        # `actualizar_comisiones` (Dirección/Admin) — no el hook genérico de F0.
        for campo in CAMPOS_COMISION:
            valor = getattr(obj, campo)
            if valor is not None:
                audit.log_cambio_parametro(
                    db=db,
                    entidad=self.entidad,
                    entidad_id=obj.orden_id,
                    campo=campo,
                    anterior=None,
                    nuevo=valor,
                    usuario=usuario,
                    motivo=None,
                )
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── edición normal ────────────────────────────────────────────────────────────
    def _pre_update(self, obj: OrdenCliente, payload: dict[str, Any], usuario: CurrentUser) -> None:
        if obj.estatus_orden in FROZEN_STATES_OC:
            raise StateTransitionError(
                f"No se puede editar una orden en estado '{obj.estatus_orden}'. Los % de "
                "comisión se ajustan por PATCH /clientes/{id}/comisiones.",
                detalles={"estatus_orden": obj.estatus_orden},
            )
        db = self._repo.db
        self._validar_fks_y_relaciones(db, payload)
        anunciante_efectivo = payload.get("anunciante_id", obj.anunciante_id)
        self._validar_contrato_marca(db, payload, anunciante_efectivo)

        if "fecha_inicio_campania" in payload or "fecha_fin_campania" in payload:
            f_ini = payload.get("fecha_inicio_campania", obj.fecha_inicio_campania)
            f_fin = payload.get("fecha_fin_campania", obj.fecha_fin_campania)
            # Solo si el valor REALMENTE cambia respecto al guardado: una orden ya en
            # curso legítimamente tiene su fecha de inicio en el pasado, y editar otro
            # campo (el front siempre reenvía el valor tal cual) no debe bloquearse por
            # eso — pero si alguien la MODIFICA, el nuevo valor sí debe ser hoy o futuro.
            if f_ini != obj.fecha_inicio_campania and f_ini < date.today():
                raise DomainError(
                    "fecha_inicio_campania no puede ser una fecha pasada.",
                    detalles={"fecha_inicio_campania": str(f_ini)},
                )
            if f_fin < f_ini:
                raise DomainError(
                    "fecha_fin_campania debe ser mayor o igual que fecha_inicio_campania.",
                    detalles={"fecha_inicio": str(f_ini), "fecha_fin": str(f_fin)},
                )
            payload["total_dias_campania"] = (f_fin - f_ini).days + 1

        if "fecha_venta" in payload:
            payload["anio_venta"] = payload["fecha_venta"].year
            payload["mes_venta"] = payload["fecha_venta"].month

        if "total_spots" in payload or "precio_unitario" in payload:
            total_spots = payload.get("total_spots", obj.total_spots)
            precio_unitario = payload.get("precio_unitario", obj.precio_unitario)
            subtotal = (Decimal(total_spots) * precio_unitario).quantize(CENTAVOS)
            iva = (subtotal * IVA_RATE).quantize(CENTAVOS)
            payload["subtotal"] = subtotal
            payload["iva"] = iva
            payload["total"] = subtotal + iva

    # ── comisiones (canal sensible dedicado — Hallazgo 2 del plan) ─────────────────
    def actualizar_comisiones(
        self, orden_id: uuid.UUID, payload: OrdenClienteComisionesUpdate, usuario: CurrentUser
    ) -> OrdenClienteRead:
        """Único canal para tocar los 3 % DESPUÉS de la captura inicial. Gateado por
        ÁREA (Dirección/Admin), no por `estatus_orden`: la propuesta dice que Ventas
        captura el resto de la orden pero NUNCA edita comisión — ni antes ni después
        de que la orden se congele."""
        if usuario.area not in (Area.DIRECCION, Area.ADMIN):
            raise PermissionDeniedError(
                f"El área '{usuario.area.value}' no puede modificar comisiones de "
                "OrdenCliente — solo Dirección."
            )
        obj = self._get_or_404(orden_id)
        db = self._repo.db

        cambios_dict = payload.model_dump(exclude_unset=True, exclude={"motivo_cambio"})
        cambios = {k: v for k, v in cambios_dict.items() if v != getattr(obj, k)}
        if not cambios:
            return self._to_read(obj)

        motivo = (payload.motivo_cambio or "").strip()
        if not motivo:
            raise DomainError(
                "Se requiere 'motivo_cambio' para modificar % de comisión.",
                detalles={"campos": list(cambios)},
            )

        # `audit.log_cambio_parametro` directo (no `registrar_cambio_sensible`) — mismo
        # motivo que en `create()`: la autorización ya la decidió el chequeo de área de
        # arriba (Dirección/Admin), no el placeholder genérico "solo Admin" de F0.
        for campo, nuevo in cambios.items():
            anterior = getattr(obj, campo)
            audit.log_cambio_parametro(
                db=db,
                entidad=self.entidad,
                entidad_id=obj.orden_id,
                campo=campo,
                anterior=anterior,
                nuevo=nuevo,
                usuario=usuario,
                motivo=motivo,
            )
            setattr(obj, campo, nuevo)
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── checklist de Vo.Bo. ────────────────────────────────────────────────────────
    def vobo_toggle(
        self, orden_id: uuid.UUID, item_clave: str, completado: bool, usuario: CurrentUser
    ) -> OrdenClienteVoBoItemRead:
        self._get_or_404(orden_id)
        if item_clave not in ITEMS_VOBO:
            raise DomainError(
                f"Ítem de checklist inválido: '{item_clave}'.",
                detalles={"validos": list(ITEMS_VOBO)},
            )
        db = self._repo.db
        item = db.scalar(
            select(OrdenClienteVoBoItem).where(
                OrdenClienteVoBoItem.orden_id == orden_id,
                OrdenClienteVoBoItem.item_clave == item_clave,
            )
        )
        if item is None:  # pragma: no cover — create() siempre siembra las 10 filas
            raise NotFoundError("Ítem de checklist no encontrado.")
        item.completado = completado
        item.usuario_id = resolver_usuario_id(db, usuario.username) if completado else None
        item.fecha_completado = datetime.now() if completado else None
        db.commit()
        db.refresh(item)
        return OrdenClienteVoBoItemRead.model_validate(item)

    def dar_vobo(self, orden_id: uuid.UUID, usuario: CurrentUser) -> OrdenClienteRead:
        obj = self._get_or_404(orden_id)
        if obj.estatus_orden != EstatusOrden.RECIBIDA.value:
            raise StateTransitionError(
                "Solo se puede dar Vo.Bo. a una orden en estatus 'recibida'.",
                detalles={"estatus_orden": obj.estatus_orden},
            )
        items = self._repo.listar_vobo(orden_id)
        faltantes = [i.item_clave for i in items if not i.completado]
        if faltantes:
            raise StateTransitionError(
                "Faltan ítems del checklist de Vo.Bo.", detalles={"faltantes": faltantes}
            )
        obj.estatus_orden = EstatusOrden.CAPTURADA.value
        db = self._repo.db
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── cierre ────────────────────────────────────────────────────────────────────
    def cerrar(
        self, orden_id: uuid.UUID, input_: OrdenClienteCerrarIn, usuario: CurrentUser
    ) -> OrdenClienteRead:
        # Import diferido: evita el ciclo orden_cliente.py ↔ orden_estacion.py (mismo
        # patrón que `BaseService.historial()` con `app.core.audit`).
        from app.modules.ordenes.orden_estacion import EstatusOrdenEstacion, OrdenEstacion

        obj = self._get_or_404(orden_id)
        if obj.estatus_orden not in (
            EstatusOrden.EN_TRANSMISION.value,
            EstatusOrden.EN_VERIFICACION.value,
        ):
            raise StateTransitionError(
                "Solo se puede cerrar una orden en 'en_transmision' o 'en_verificacion'.",
                detalles={"estatus_orden": obj.estatus_orden},
            )
        db = self._repo.db
        oes = db.scalars(select(OrdenEstacion).where(OrdenEstacion.orden_id == orden_id)).all()
        if not oes:
            raise StateTransitionError(
                "No se puede cerrar una orden sin ninguna OrdenEstacion asignada."
            )
        pendientes = [
            oe.folio_orden_estacion
            for oe in oes
            if oe.estatus != EstatusOrdenEstacion.CERRADA.value
        ]
        if pendientes:
            raise StateTransitionError(
                "Todas las OrdenEstacion deben estar 'cerrada' antes de cerrar la orden.",
                detalles={"pendientes": pendientes},
            )

        # Backfill de comisiones NULAS con el default del catálogo — completar un vacío,
        # no una edición: no se audita ni exige motivo (a diferencia de `actualizar_comisiones`).
        if obj.porcentaje_comision_vendedor_principal_snap is None:
            vendedor = db.get(Vendedor, obj.vendedor_principal_id)
            if vendedor is not None:
                obj.porcentaje_comision_vendedor_principal_snap = (
                    vendedor.porcentaje_comision_default
                )
        if (
            obj.vendedor_secundario_id is not None
            and obj.porcentaje_comision_vendedor_secundario_snap is None
        ):
            vendedor_sec = db.get(Vendedor, obj.vendedor_secundario_id)
            if vendedor_sec is not None:
                obj.porcentaje_comision_vendedor_secundario_snap = (
                    vendedor_sec.porcentaje_comision_default
                )
        if obj.agencia_id is not None and obj.porcentaje_comision_agencia_snap is None:
            agencia = db.get(Agencia, obj.agencia_id)
            if agencia is not None:
                obj.porcentaje_comision_agencia_snap = agencia.porcentaje_comision_agencia_default

        obj.odc_cerrada_ref = input_.odc_cerrada_ref
        obj.carta_conciliacion_ref = input_.carta_conciliacion_ref
        obj.cierre_sin_odc_cerrada = input_.odc_cerrada_ref is None
        obj.cierre_sin_carta_conciliacion = input_.carta_conciliacion_ref is None
        obj.fecha_cierre = date.today()
        obj.estatus_orden = EstatusOrden.ORDEN_CERRADA.value

        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── Handoff con F2 (Facturación) ──────────────────────────────────────────
    def marcar_facturada(self, orden_id: uuid.UUID) -> None:
        """`orden_cerrada → facturada`. La DISPARA F2 al timbrar la FacturaCliente.

        Por qué vive aquí y no en F2: `OrdenCliente` es el agregado de F1 y la regla de
        qué estados admiten pasar a `facturada` es suya. F1 ya promueve la OC desde
        `OrdenEstacionService` mutando el ORM directamente, pero eso ocurre DENTRO del
        mismo módulo; hacerlo desde F2 dejaría una regla de la máquina de estados de la
        OC escrita en el módulo equivocado.

        **No hace `commit`, a propósito.** El llamador (`FacturaClienteService.
        transicionar`) la invoca con la MISMA sesión antes de su propio `commit`, así que
        timbrar la factura y facturar la orden son una sola transacción atómica: si esto
        falla, el timbrado también se revierte y no queda una factura timbrada con su
        orden desincronizada.

        Idempotente: si la orden ya está `facturada` no hace nada (permite reintentar el
        timbrado sin romper). Desde `cobrada` tampoco retrocede: `cobrada` es un estado
        POSTERIOR, responsabilidad de F3, y volver a `facturada` sería un retroceso.
        """
        obj = self._get_or_404(orden_id)
        if obj.estatus_orden in (EstatusOrden.FACTURADA.value, EstatusOrden.COBRADA.value):
            return  # ya facturada (o más allá): nada que hacer
        if obj.estatus_orden != EstatusOrden.ORDEN_CERRADA.value:
            raise StateTransitionError(
                "Solo una orden en 'orden_cerrada' puede pasar a 'facturada'.",
                detalles={"orden_id": str(orden_id), "estatus_orden": obj.estatus_orden},
            )
        obj.estatus_orden = EstatusOrden.FACTURADA.value


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_orden_cliente_service(db: Session = Depends(get_db)) -> OrdenClienteService:
    repo = OrdenClienteRepository(
        db,
        OrdenCliente,
        search_columns=[OrdenCliente.folio_orden, OrdenCliente.numero_orden_cliente],
        default_order_by=[OrdenCliente.folio_orden],
    )
    return OrdenClienteService(repo)


router_clientes = APIRouter(prefix="/clientes", tags=["ordenes:clientes"])


@router_clientes.get("", response_model=Page[OrdenClienteRead])
def listar_ordenes_cliente(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Búsqueda por folio o número de orden del cliente"),
    estatus_orden: EstatusOrden | None = Query(None, description="Filtro por estatus_orden"),
    anunciante_id: uuid.UUID | None = Query(None),
    agencia_id: uuid.UUID | None = Query(None),
    vendedor_principal_id: uuid.UUID | None = Query(None),
    contrato_id: uuid.UUID | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> Page[OrdenClienteRead]:
    return svc.list(
        OrdenClienteListParams(
            page=page,
            size=size,
            q=q,
            estatus_orden=estatus_orden,
            anunciante_id=anunciante_id,
            agencia_id=agencia_id,
            vendedor_principal_id=vendedor_principal_id,
            contrato_id=contrato_id,
        )
    )


@router_clientes.get("/{item_id}", response_model=OrdenClienteRead)
def obtener_orden_cliente(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteRead:
    return svc.get(item_id)


@router_clientes.get("/{item_id}/vobo", response_model=list[OrdenClienteVoBoItemRead])
def listar_vobo_orden_cliente(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> Sequence[OrdenClienteVoBoItemRead]:
    """Checklist de Vo.Bo. (los 10 ítems fijos, ADR-033) de una OrdenCliente."""
    return svc.vobo(item_id)


@router_clientes.get(
    "/{item_id}/historial-comisiones", response_model=list[audit.LogCambioParametroRead]
)
def historial_comisiones_orden_cliente(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> Sequence[audit.LogCambioParametroRead]:
    """Historial de cambios a los % de comisión snapshot (ADR-029) de una OrdenCliente."""
    return svc.historial_comisiones(item_id)


# ── Escritura (Tanda 5) ────────────────────────────────────────────────────────
@router_clientes.post("", response_model=OrdenClienteRead, status_code=201)
def crear_orden_cliente(
    payload: OrdenClienteCreate,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:crear")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteRead:
    """Alta de OrdenCliente (Ventas). Nace en `recibida` — o directo en `capturada` si
    `dar_vobo=true` y el checklist ya viene completo (409 si no)."""
    return svc.create(payload, usuario)


@router_clientes.put("/{item_id}", response_model=OrdenClienteRead)
def actualizar_orden_cliente(
    item_id: uuid.UUID,
    payload: OrdenClienteUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteRead:
    """Edición normal (Ventas). 409 si la orden está en un estado congelado
    (`orden_cerrada`/`facturada`/`cobrada`)."""
    return svc.update(item_id, payload, usuario)


@router_clientes.patch("/{item_id}/comisiones", response_model=OrdenClienteRead)
def actualizar_comisiones_orden_cliente(
    item_id: uuid.UUID,
    payload: OrdenClienteComisionesUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteRead:
    """Único canal para editar % de comisión DESPUÉS de la captura inicial — permiso
    de ROUTER deliberadamente `ordenes:leer` (Dirección solo tiene lectura del módulo);
    la autorización real (solo Dirección/Admin) se valida DENTRO del servicio, ver su
    docstring. 403 si el área no es Dirección/Admin; 400 si cambia algo sin
    `motivo_cambio`."""
    return svc.actualizar_comisiones(item_id, payload, usuario)


@router_clientes.patch("/{item_id}/vobo/{item_clave}", response_model=OrdenClienteVoBoItemRead)
def toggle_vobo_orden_cliente(
    item_id: uuid.UUID,
    item_clave: str,
    payload: VoBoToggleIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteVoBoItemRead:
    """Marca/desmarca UN ítem del checklist de Vo.Bo. (422 si `item_clave` no es una de
    las 10 fijas — ver `ITEMS_VOBO`)."""
    return svc.vobo_toggle(item_id, item_clave, payload.completado, usuario)


@router_clientes.post("/{item_id}/dar-vobo", response_model=OrdenClienteRead)
def dar_vobo_orden_cliente(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteRead:
    """Transición `recibida` → `capturada`. 409 si falta algún ítem del checklist o si
    la orden ya no está en `recibida`."""
    return svc.dar_vobo(item_id, usuario)


@router_clientes.post("/{item_id}/cerrar", response_model=OrdenClienteRead)
def cerrar_orden_cliente(
    item_id: uuid.UUID,
    payload: OrdenClienteCerrarIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenClienteService = Depends(get_orden_cliente_service),
) -> OrdenClienteRead:
    """Transición a `orden_cerrada`. 409 si la orden no está en `en_transmision`/
    `en_verificacion`, si no tiene ninguna OrdenEstacion, o si alguna no está `cerrada`.
    Rellena % de comisión que hayan quedado `null` con el default del catálogo."""
    return svc.cerrar(item_id, payload, usuario)
