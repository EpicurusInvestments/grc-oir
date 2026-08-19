"""OrdenEstacion (F1) — asignación operativa a una estación, derivada de una OrdenCliente.

La spec BD v2 modela `fecha_transmision`/`hora_inicio`/`hora_fin`/`spots_solicitados`/
`spots_asignados`/`spots_faltantes` como campos PLANOS de OrdenEstacion (una fila = un
día). La spec misma autoriza la alternativa que usamos aquí:

    "Si la orden cubre un rango de fechas, se puede crear una OrdenEstacion por fecha
     o AGRUPAR POR RANGO."

Agrupamos por rango (ADR-030): esos 6 campos se mueven a la tabla hija
`OrdenEstacionDia` (una fila por día), y con ellos se agregan TRES capas de captura que
el prototipo aprobado sí distingue y la spec no (aprobado explícitamente):

    2.1 asignado   → OrdenEstacionDia.spots_asignados (spec, NOT NULL)
    2.2 programado → OrdenEstacionDia.spots_programados (NUEVO, nullable: NULL = todavía
                     no confirmado por el afiliado; al confirmarse se llena con el valor
                     EFECTIVO de ese día, no con un delta)
    2.3 verificado → Verificacion.spots_verificados (spec, una fila por día/reporte)

`spots_faltantes` (Calculado en la spec, a nivel OrdenEstacion) deja de ser una columna
persistida: ahora es un agregado sobre los días de la OE (`SUM(spots_solicitados) -
SUM(spots_asignados)`), lo calcula el servicio al leer, igual que `importe_estacion` y
todo lo que de él depende.

`testigos_url`/`testigos_ubicacion_alterna`/`notas_transmision`/`reporte_programados_ref`/
`reporte_reales_ref` tampoco están en la spec (ADR-030): se capturan UNA VEZ por lote al
avanzar 2.1→2.2 o 2.2→2.3 (no por día), por eso viven en OrdenEstacion, no en
OrdenEstacionDia — coherente con cómo ya los captura la demo de frontend.

`OrdenEstacion.estatus` es un ciclo de vida PROPIO e independiente del de OrdenCliente
(spec, confirmado): cada OE cierra por su cuenta cuando SUS días quedan reconciliados;
`OrdenCliente.estatus_orden = orden_cerrada` es una transición aparte, gatillada cuando
TODAS las OE de esa OC ya están en `cerrada` (se valida en el servicio, no aquí).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time
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
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.core.db import Base, datetime2, fecha_sql, get_db, hora_sql, texto_largo
from app.core.errors import DomainError, NotFoundError, StateTransitionError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.estacion import Estacion
from app.modules.usuarios.lookup import resolver_usuario_id
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.enums import DuracionSpot  # noqa: F401 — reexportado para quien importe desde aquí
from app.shared.schemas import ListParams, Page

CENTAVOS = Decimal("0.01")
IVA_RATE = Decimal(str(settings.iva_rate))


class EstatusOrdenEstacion(StrEnum):
    BORRADOR = "borrador"
    ASIGNADA = "asignada"
    EN_TRANSMISION = "en_transmision"
    EN_REVISION = "en_revision"
    CERRADA = "cerrada"
    CANCELADA = "cancelada"


# ── Modelo ──────────────────────────────────────────────────────────────────────
class OrdenEstacion(Base):
    __tablename__ = "orden_estacion"
    __table_args__ = (
        CheckConstraint(
            "estatus IN ('borrador', 'asignada', 'en_transmision', 'en_revision', "
            "'cerrada', 'cancelada')",
            name="ck_orden_estacion_estatus",
        ),
        CheckConstraint(
            "duracion_spot IN ('20s', '30s', '60s', 'mencion')",
            name="ck_orden_estacion_duracion_spot",
        ),
        CheckConstraint(
            "porcentaje_participacion_oir >= 0 AND porcentaje_participacion_oir <= 100",
            name="ck_orden_estacion_pct_oir",
        ),
        # Auditoría de migración a RDS: las 8 columnas de dinero de OrdenEstacion no
        # tenían CHECK — omisión de la misma pasada que sí cubrió orden_cliente e
        # incidencia. Ninguna es legítimamente negativa: precio_spot es una tarifa;
        # importe_estacion = spots * precio_spot; importe_oir/iva_oir/total_oir e
        # importe_emisora/iva_emisora/total_emisora se derivan de porcentaje_participacion_oir
        # (ya acotado a 0-100 arriba), así que importe_oir <= importe_estacion siempre —
        # a diferencia de Incidencia.diferencia_spots/monto_ajuste, aquí no hay caso de
        # ajuste que legitime un valor negativo.
        CheckConstraint("precio_spot >= 0", name="ck_orden_estacion_precio_spot"),
        CheckConstraint("importe_estacion >= 0", name="ck_orden_estacion_importe_estacion"),
        CheckConstraint("importe_oir >= 0", name="ck_orden_estacion_importe_oir"),
        CheckConstraint("iva_oir >= 0", name="ck_orden_estacion_iva_oir"),
        CheckConstraint("total_oir >= 0", name="ck_orden_estacion_total_oir"),
        CheckConstraint("importe_emisora >= 0", name="ck_orden_estacion_importe_emisora"),
        CheckConstraint("iva_emisora >= 0", name="ck_orden_estacion_iva_emisora"),
        CheckConstraint("total_emisora >= 0", name="ck_orden_estacion_total_emisora"),
        # 3 invariantes de suma exacta (Tanda 4c). Verificado en el servicio
        # (`create()`, más abajo): `importe_emisora = importe_estacion - importe_oir`
        # es una RESTA pura entre dos `Decimal` ya `.quantize(CENTAVOS)`, no un segundo
        # cálculo redondeado por separado — por construcción hoy nunca puede descuadrar
        # por un centavo, así que el CHECK no corre riesgo de falso positivo. Mismo
        # razonamiento para `total_oir`/`total_emisora`: son la suma de dos montos que
        # YA se redondearon antes de sumarse, no una tercera cantidad con su propio
        # redondeo independiente. NO se agrega un CHECK que compare `importe_estacion`
        # contra la suma de `OrdenEstacionDia` (tabla hija): eso no es expresable en una
        # constraint de una sola tabla.
        #
        # `ROUND(x, 2)` en ambos lados, no comparación directa (Tanda 4c, hallazgo de
        # la re-siembra): en SQLite, `NUMERIC` se almacena como float64 — sumar dos
        # floats ya redondeados puede diferir por 1 ULP del float64 del total
        # almacenado por separado (probado con `oe8` de `seed_dev.py`: 44478.00 +
        # 7116.48 = 51594.48 exacto en Decimal, pero 51594.479999999996 en float64,
        # que no calza bit a bit con el 51594.48 guardado). SQL Server no tiene este
        # problema (`NUMERIC(14,2)` ahí es de punto fijo real, no float), así que
        # `ROUND` es un no-op inofensivo en el destino real y solo neutraliza el ruido
        # de float64 en SQLite. Verificado que `ROUND` NO enmascara una violación real:
        # una diferencia de 1 centavo completo sigue siendo rechazada.
        CheckConstraint(
            "ROUND(importe_oir + importe_emisora, 2) = ROUND(importe_estacion, 2)",
            name="ck_orden_estacion_margen_oir_emisora",
        ),
        CheckConstraint(
            "ROUND(total_oir, 2) = ROUND(importe_oir + iva_oir, 2)",
            name="ck_orden_estacion_total_oir_suma",
        ),
        CheckConstraint(
            "ROUND(total_emisora, 2) = ROUND(importe_emisora + iva_emisora, 2)",
            name="ck_orden_estacion_total_emisora_suma",
        ),
    )

    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    folio_orden_estacion: Mapped[str] = mapped_column(Unicode(25), unique=True, index=True)
    orden_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_cliente.orden_id", name="fk_orden_estacion_orden_cliente", ondelete="NO ACTION"
        ),
        index=True,
    )
    numero_orden_estacion: Mapped[str | None] = mapped_column(Unicode(50), default=None)

    contrato_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contrato.contrato_id", name="fk_orden_estacion_contrato", ondelete="NO ACTION"),
        default=None,
    )
    # Derivado: heredado de OrdenCliente.anunciante_id al crear la OE.
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "anunciante.anunciante_id", name="fk_orden_estacion_anunciante", ondelete="NO ACTION"
        ),
        index=True,
    )
    vendedor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendedor.vendedor_id", name="fk_orden_estacion_vendedor", ondelete="NO ACTION"),
        index=True,
    )
    # Derivado: heredado de OrdenCliente.agencia_id al crear la OE.
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agencia.agencia_id", name="fk_orden_estacion_agencia", ondelete="NO ACTION"),
        default=None,
    )
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "categoria.categoria_id", name="fk_orden_estacion_categoria", ondelete="NO ACTION"
        ),
        default=None,
    )
    producto: Mapped[str | None] = mapped_column(Unicode(200), default=None)

    estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("estacion.estacion_id", name="fk_orden_estacion_estacion", ondelete="NO ACTION"),
        index=True,
    )
    # Derivado: heredado de Estacion.plaza_id al crear la OE (mismo patrón que ADR-005).
    plaza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plaza.plaza_id", name="fk_orden_estacion_plaza", ondelete="NO ACTION"),
        index=True,
    )

    # Heredado de OrdenCliente.duracion_spot.
    duracion_spot: Mapped[str] = mapped_column(Unicode(10))
    precio_spot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Calculado (spec) — agregado sobre OrdenEstacionDia, lo persiste el servicio.
    importe_estacion: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    porcentaje_participacion_oir: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    # Calculados (spec): importe_oir = importe_estacion * pct_oir / 100; iva_oir = importe_oir
    # * IVA_RATE; total_oir = importe_oir + iva_oir. importe_emisora = importe_estacion -
    # importe_oir; iva_emisora/total_emisora análogos. Todos persistidos por el servicio.
    importe_oir: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_oir: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_oir: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    importe_emisora: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_emisora: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_emisora: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    # Indexado: filtro real de `OrdenEstacionRepository._apply_filters` (pantallas de
    # lista) — mismo criterio que `OrdenCliente.estatus_orden`.
    estatus: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusOrdenEstacion.BORRADOR.value, index=True
    )
    observaciones_estacion: Mapped[str | None] = mapped_column(texto_largo(), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuario.usuario_id", name="fk_orden_estacion_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )

    # ── Extensión aditiva: captura por lote de 2.2/2.3 (ADR-030) ─────────────────
    testigos_url: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    testigos_ubicacion_alterna: Mapped[str | None] = mapped_column(Unicode(300), default=None)
    notas_transmision: Mapped[str | None] = mapped_column(texto_largo(), default=None)
    reporte_programados_ref: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    reporte_reales_ref: Mapped[str | None] = mapped_column(Unicode(500), default=None)


# ── Periodo de transmisión por día (ADR-030) ─────────────────────────────────────
class OrdenEstacionDia(Base):
    __tablename__ = "orden_estacion_dia"
    __table_args__ = (
        # `> 0`, no `>= 0` (auditoría de migración a RDS, Tanda 4c): mismo argumento que
        # `ck_orden_cliente_total_spots` (`total_spots > 0`) — un día con cero spots
        # solicitados no tiene razón de existir como fila; el prototipo de frontend ya
        # exigía `spots_diarios > 0` por día (`PeriodoTransmisionGrid.tsx`).
        CheckConstraint("spots_solicitados > 0", name="ck_orden_estacion_dia_spots_solicitados"),
        CheckConstraint("spots_asignados >= 0", name="ck_orden_estacion_dia_spots_asignados"),
        # Respaldado por el texto literal de la spec ("Puede ser menor o igual a los
        # solicitados") — auditoría de migración a RDS, Tanda 4. NO se agrega el
        # equivalente para spots_programados <= spots_asignados: ni la spec ni el
        # prototipo de frontend respaldan ese tope (spots_programados es un override
        # libre del afiliado, sin restricción documentada en ningún lado), y
        # spots_verificados NUNCA lleva tope — "excedente" es un tipo de incidencia
        # válido, la realidad sí puede superar lo programado.
        CheckConstraint(
            "spots_asignados <= spots_solicitados", name="ck_orden_estacion_dia_asignados_max"
        ),
        CheckConstraint(
            "spots_programados IS NULL OR spots_programados >= 0",
            name="ck_orden_estacion_dia_spots_programados",
        ),
        CheckConstraint("hora_fin > hora_inicio", name="ck_orden_estacion_dia_horas"),
        # Auditoría de migración a RDS, Tanda 4: un duplicado de (OE, fecha, hora de
        # inicio) rompería en silencio las sumas de balance/importe, que agregan sobre
        # estas filas. Se incluye `hora_inicio` (no solo OE+fecha) porque el prototipo
        # de frontend sí permite legítimamente dos franjas horarias distintas el mismo
        # día para la misma OE.
        UniqueConstraint(
            "orden_estacion_id",
            "fecha_transmision",
            "hora_inicio",
            name="uq_orden_estacion_dia_oe_fecha_hora",
        ),
    )

    orden_estacion_dia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # Sin `index=True`: sería redundante con `uq_orden_estacion_dia_oe_fecha_hora`
    # (columna líder), mismo patrón que `orden_cliente_vobo_item.orden_id` — auditoría
    # de migración a RDS.
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_orden_estacion_dia_orden_estacion",
            ondelete="NO ACTION",
        )
    )
    # Sin `index=True`: verificado que ningún endpoint filtra por `fecha_transmision`
    # sola — `listar_dias()` siempre filtra por `orden_estacion_id` primero (mismo
    # criterio ya aplicado a las fechas de campaña de `orden_cliente`, que tampoco se
    # indexaron por la misma razón). Auditoría de migración a RDS.
    fecha_transmision: Mapped[date] = mapped_column(fecha_sql())
    hora_inicio: Mapped[time] = mapped_column(hora_sql())  # 2.1 asignado
    hora_fin: Mapped[time] = mapped_column(hora_sql())  # 2.1 asignado
    spots_solicitados: Mapped[int] = mapped_column()
    spots_asignados: Mapped[int] = mapped_column()  # 2.1 asignado
    # 2.2 programado: NULL hasta que el afiliado confirma; al confirmar se llena con el
    # valor EFECTIVO de ese día (no un delta) — puede ser igual a spots_asignados.
    spots_programados: Mapped[int | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas de lectura (Tanda 3 — API de lectura; Create/Update llegan en Tanda 5) ────
class OrdenEstacionRead(BaseModel):
    """Espejo de las columnas reales de `OrdenEstacion` (sin `CatalogoReadBase`: no tiene
    `activo`, usa la máquina de estados propia `estatus`, independiente de la OC)."""

    model_config = ConfigDict(from_attributes=True)

    orden_estacion_id: uuid.UUID
    folio_orden_estacion: str
    orden_id: uuid.UUID
    numero_orden_estacion: str | None = None
    contrato_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID
    vendedor_id: uuid.UUID
    agencia_id: uuid.UUID | None = None
    categoria_id: uuid.UUID | None = None
    producto: str | None = None
    estacion_id: uuid.UUID
    plaza_id: uuid.UUID
    duracion_spot: str
    precio_spot: Decimal
    importe_estacion: Decimal
    porcentaje_participacion_oir: Decimal
    importe_oir: Decimal
    iva_oir: Decimal
    total_oir: Decimal
    importe_emisora: Decimal
    iva_emisora: Decimal
    total_emisora: Decimal
    estatus: EstatusOrdenEstacion
    observaciones_estacion: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    testigos_url: str | None = None
    testigos_ubicacion_alterna: str | None = None
    notas_transmision: str | None = None
    reporte_programados_ref: str | None = None
    reporte_reales_ref: str | None = None

    @field_serializer(
        "precio_spot",
        "importe_estacion",
        "porcentaje_participacion_oir",
        "importe_oir",
        "iva_oir",
        "total_oir",
        "importe_emisora",
        "iva_emisora",
        "total_emisora",
    )
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


class OrdenEstacionDiaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden_estacion_dia_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    fecha_transmision: date
    hora_inicio: time
    hora_fin: time
    spots_solicitados: int
    spots_asignados: int
    spots_programados: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class OrdenEstacionListParams(ListParams):
    """`ListParams` + filtros propios. Hereda `activo`, pero NUNCA se expone como query
    param: `OrdenEstacion` no tiene baja lógica, usa `estatus` (ciclo propio). Se hereda
    solo por compatibilidad de tipo con `BaseRepository`/`BaseService`. Razonamiento
    completo — incluyendo el hueco real de que `cancelada` hoy no es alcanzable por
    ningún endpoint — en ADR-035 (docs/arquitectura.md)."""

    orden_id: uuid.UUID | None = None  # OE de una OC (panel de detalle de OrdenCliente)
    estacion_id: uuid.UUID | None = None
    plaza_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID | None = None
    estatus: EstatusOrdenEstacion | None = None


# ── Schemas de escritura (Tanda 5) ────────────────────────────────────────────────
class OrdenEstacionDiaCreate(BaseModel):
    fecha_transmision: date
    hora_inicio: time
    hora_fin: time
    spots_asignados: int = Field(ge=0)
    # "Solicitado" vs "asignado" (spec: pueden diferir); si se omite, se asume que se
    # asignó exactamente lo solicitado (mismo criterio que `seed_dev.py`, Tanda 2).
    # `gt=0`, no `ge=0` (Tanda 4c): espejo del nuevo `ck_orden_estacion_dia_spots_solicitados`
    # — un valor explícito de 0 debe rechazarse aquí con un 422 claro, no llegar a
    # reventar el CHECK de la base con un 500.
    spots_solicitados: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _valida_horas(self) -> OrdenEstacionDiaCreate:
        if self.hora_fin <= self.hora_inicio:
            raise ValueError("hora_fin debe ser mayor que hora_inicio.")
        # `spots_solicitados` omitido cae a `spots_asignados` (ver comentario del campo
        # arriba) — si ese fallback también fuera 0, la fila violaría
        # `ck_orden_estacion_dia_spots_solicitados` (`> 0`) al llegar a la base. Se
        # atrapa aquí para un 422 claro en vez de un 500 del CHECK (Tanda 4c).
        if self.spots_solicitados is None and self.spots_asignados == 0:
            raise ValueError(
                "spots_asignados no puede ser 0 cuando no se especifica spots_solicitados "
                "(el día quedaría con 0 spots solicitados)."
            )
        return self


class OrdenEstacionCreate(BaseModel):
    orden_id: uuid.UUID
    estacion_id: uuid.UUID
    precio_spot: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    observaciones_estacion: str | None = Field(default=None, max_length=2000)
    dias: list[OrdenEstacionDiaCreate] = Field(min_length=1)


class OrdenEstacionDiaProgramadoIn(BaseModel):
    fecha_transmision: date
    spots_programados: int = Field(ge=0)


class OrdenEstacionProgramadosIn(BaseModel):
    """Solo las EXCEPCIONES (los días que confirmaron un valor distinto al asignado) —
    mismo formato disperso que ya manda `ProgramadosForm` del frontend. Los días no
    listados quedan `spots_programados = spots_asignados` (confirmados tal cual)."""

    dias: list[OrdenEstacionDiaProgramadoIn] = Field(default_factory=list)
    reporte_programados_ref: str | None = Field(default=None, max_length=500)


class OrdenEstacionDiaRealIn(BaseModel):
    fecha_transmision: date
    spots_verificados: int = Field(ge=0)


class OrdenEstacionRealesIn(BaseModel):
    """Solo las EXCEPCIONES respecto al programado EFECTIVO — mismo formato disperso que
    ya manda `RealesForm`. TODOS los días reciben una fila `Verificacion` (spec: una por
    día); los no listados aquí se verifican con el mismo valor programado (sin cambio,
    sin incidencia)."""

    dias: list[OrdenEstacionDiaRealIn] = Field(default_factory=list)
    testigos_url: str | None = Field(default=None, max_length=500)
    testigos_ubicacion_alterna: str | None = Field(default=None, max_length=300)
    notas_transmision: str | None = Field(default=None, max_length=2000)
    reporte_reales_ref: str | None = Field(default=None, max_length=500)


# ── Repositorio ───────────────────────────────────────────────────────────────
class OrdenEstacionRepository(BaseRepository[OrdenEstacion]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`, columna
        # que OrdenEstacion no tiene (usa `estatus`, ciclo de vida propio — ver docstring).
        q = (getattr(params, "q", None) or "").strip()
        if q:
            patron = f"%{q}%"
            stmt = stmt.where(
                OrdenEstacion.folio_orden_estacion.ilike(patron)
                | OrdenEstacion.numero_orden_estacion.ilike(patron)
            )
        estatus = getattr(params, "estatus", None)
        if estatus is not None:
            stmt = stmt.where(OrdenEstacion.estatus == EstatusOrdenEstacion(estatus).value)
        for campo in ("orden_id", "estacion_id", "plaza_id", "anunciante_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(OrdenEstacion, campo) == valor)
        return stmt

    def listar_dias(self, orden_estacion_id: uuid.UUID) -> Sequence[OrdenEstacionDia]:
        stmt = (
            select(OrdenEstacionDia)
            .where(OrdenEstacionDia.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionDia.fecha_transmision)
        )
        return self.db.scalars(stmt).all()


# ── Servicio ──────────────────────────────────────────────────────────────────
class OrdenEstacionService(
    BaseService[OrdenEstacion, OrdenEstacionCreate, BaseModel, OrdenEstacionRead]
):
    """`create` asigna una estación a una OrdenCliente (Ventas). Las transiciones
    2.1→2.2→2.3 (`avanzar_programados`/`avanzar_reales`) son métodos dedicados, no
    `update` genérico: cada una tiene su propia forma de entrada y efectos (generación
    de `Verificacion`/`Incidencia`, cascada de estatus a la OC)."""

    read_schema = OrdenEstacionRead
    entidad = "OrdenEstacion"

    def __init__(self, repo: OrdenEstacionRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def dias(self, orden_estacion_id: uuid.UUID) -> Sequence[OrdenEstacionDiaRead]:
        self._get_or_404(orden_estacion_id)
        return [
            OrdenEstacionDiaRead.model_validate(d)
            for d in self._repo.listar_dias(orden_estacion_id)
        ]

    # ── alta ──────────────────────────────────────────────────────────────────────
    def create(self, data: OrdenEstacionCreate, usuario: CurrentUser) -> OrdenEstacionRead:
        # Import diferido: evita el ciclo orden_cliente.py ↔ orden_estacion.py (mismo
        # patrón que `OrdenClienteService.cerrar`).
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente

        db = self._repo.db
        oc = db.get(OrdenCliente, data.orden_id)
        if oc is None:
            raise NotFoundError(
                "OrdenCliente no encontrada.", detalles={"orden_id": str(data.orden_id)}
            )
        if oc.estatus_orden not in (
            EstatusOrden.CAPTURADA.value,
            EstatusOrden.EN_TRANSMISION.value,
        ):
            raise StateTransitionError(
                "Solo se pueden asignar estaciones a una orden en 'capturada' o 'en_transmision'.",
                detalles={"estatus_orden": oc.estatus_orden},
            )
        estacion = db.get(Estacion, data.estacion_id)
        if estacion is None:
            raise NotFoundError("Estacion no encontrada.", detalles={"id": str(data.estacion_id)})

        if data.precio_spot > oc.precio_unitario:
            raise DomainError(
                "La tarifa de la estación no puede ser mayor que la tarifa cliente de la OC.",
                detalles={
                    "precio_spot": str(data.precio_spot),
                    "precio_unitario_oc": str(oc.precio_unitario),
                },
            )
        for dia in data.dias:
            if not (oc.fecha_inicio_campania <= dia.fecha_transmision <= oc.fecha_fin_campania):
                raise DomainError(
                    "Hay días fuera del rango de campaña de la orden.",
                    detalles={
                        "fecha": str(dia.fecha_transmision),
                        "campania": [str(oc.fecha_inicio_campania), str(oc.fecha_fin_campania)],
                    },
                )

        hermanas_ids = db.scalars(
            select(OrdenEstacion.orden_estacion_id).where(OrdenEstacion.orden_id == oc.orden_id)
        ).all()
        asignados_previos = 0
        if hermanas_ids:
            asignados_previos = (
                db.scalar(
                    select(func.coalesce(func.sum(OrdenEstacionDia.spots_asignados), 0)).where(
                        OrdenEstacionDia.orden_estacion_id.in_(hermanas_ids)
                    )
                )
                or 0
            )
        nuevos = sum(d.spots_asignados for d in data.dias)
        if asignados_previos + nuevos > oc.total_spots:
            raise DomainError(
                "Excede el total de spots de la orden.",
                detalles={
                    "total_oc": oc.total_spots,
                    "ya_asignados": asignados_previos,
                    "nuevos": nuevos,
                },
            )

        # % de participación OIR: CALCULADO (ya no lo captura el formulario, ver plan de
        # la Tanda 5) = (precio_unitario_OC − precio_spot) / precio_unitario_OC × 100.
        pct_oir = Decimal("0")
        if oc.precio_unitario > 0:
            pct_oir = (
                (oc.precio_unitario - data.precio_spot) / oc.precio_unitario * Decimal(100)
            ).quantize(Decimal("0.1"))

        importe_estacion = (Decimal(nuevos) * data.precio_spot).quantize(CENTAVOS)
        importe_oir = (importe_estacion * pct_oir / Decimal(100)).quantize(CENTAVOS)
        iva_oir = (importe_oir * IVA_RATE).quantize(CENTAVOS)
        importe_emisora = importe_estacion - importe_oir
        iva_emisora = (importe_emisora * IVA_RATE).quantize(CENTAVOS)

        letra = chr(65 + len(hermanas_ids))
        folio = oc.folio_orden.replace("OC-", "OE-") + letra

        obj = OrdenEstacion(
            orden_estacion_id=uuid4(),
            folio_orden_estacion=folio,
            orden_id=oc.orden_id,
            contrato_id=oc.contrato_id,
            anunciante_id=oc.anunciante_id,
            vendedor_id=oc.vendedor_principal_id,
            agencia_id=oc.agencia_id,
            categoria_id=oc.categoria_id,
            producto=oc.producto,
            estacion_id=estacion.estacion_id,
            plaza_id=estacion.plaza_id,
            duracion_spot=oc.duracion_spot,
            precio_spot=data.precio_spot,
            importe_estacion=importe_estacion,
            porcentaje_participacion_oir=pct_oir,
            importe_oir=importe_oir,
            iva_oir=iva_oir,
            total_oir=importe_oir + iva_oir,
            importe_emisora=importe_emisora,
            iva_emisora=iva_emisora,
            total_emisora=importe_emisora + iva_emisora,
            estatus=EstatusOrdenEstacion.ASIGNADA.value,
            observaciones_estacion=data.observaciones_estacion,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        for dia in data.dias:
            db.add(
                OrdenEstacionDia(
                    orden_estacion_dia_id=uuid4(),
                    orden_estacion_id=obj.orden_estacion_id,
                    fecha_transmision=dia.fecha_transmision,
                    hora_inicio=dia.hora_inicio,
                    hora_fin=dia.hora_fin,
                    spots_solicitados=(
                        dia.spots_solicitados
                        if dia.spots_solicitados is not None
                        else dia.spots_asignados
                    ),
                    spots_asignados=dia.spots_asignados,
                )
            )
        if oc.estatus_orden == EstatusOrden.CAPTURADA.value:
            oc.estatus_orden = EstatusOrden.EN_TRANSMISION.value

        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── 2.1 → 2.2 ─────────────────────────────────────────────────────────────────
    def avanzar_programados(
        self, orden_estacion_id: uuid.UUID, input_: OrdenEstacionProgramadosIn, usuario: CurrentUser
    ) -> OrdenEstacionRead:
        obj = self._get_or_404(orden_estacion_id)
        if obj.estatus != EstatusOrdenEstacion.ASIGNADA.value:
            raise StateTransitionError(
                "Solo se puede avanzar a programados desde 'asignada'.",
                detalles={"estatus": obj.estatus},
            )
        db = self._repo.db
        overrides = {d.fecha_transmision: d.spots_programados for d in input_.dias}
        dias = self._repo.listar_dias(orden_estacion_id)
        for dia in dias:
            dia.spots_programados = overrides.get(dia.fecha_transmision, dia.spots_asignados)
        obj.reporte_programados_ref = input_.reporte_programados_ref
        obj.estatus = EstatusOrdenEstacion.EN_TRANSMISION.value
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── 2.2 → 2.3 (genera Verificacion + Incidencia automática) ────────────────────
    def avanzar_reales(
        self, orden_estacion_id: uuid.UUID, input_: OrdenEstacionRealesIn, usuario: CurrentUser
    ) -> OrdenEstacionRead:
        # Imports diferidos: evitan los ciclos orden_estacion.py ↔ verificacion.py /
        # incidencia.py / orden_cliente.py (mismo patrón que `OrdenClienteService.cerrar`).
        from app.modules.ordenes.incidencia import Incidencia, ResolucionIncidencia, TipoIncidencia
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente
        from app.modules.ordenes.verificacion import Verificacion

        obj = self._get_or_404(orden_estacion_id)
        if obj.estatus != EstatusOrdenEstacion.EN_TRANSMISION.value:
            raise StateTransitionError(
                "Solo se puede avanzar a reales desde 'en_transmision'.",
                detalles={"estatus": obj.estatus},
            )
        db = self._repo.db
        overrides = {d.fecha_transmision: d.spots_verificados for d in input_.dias}
        dias = self._repo.listar_dias(orden_estacion_id)
        usuario_id = resolver_usuario_id(db, usuario.username)
        hoy = date.today()

        for dia in dias:
            programado_efectivo = (
                dia.spots_programados if dia.spots_programados is not None else dia.spots_asignados
            )
            verificado = overrides.get(dia.fecha_transmision, programado_efectivo)
            verificacion = Verificacion(
                verificacion_id=uuid4(),
                orden_estacion_dia_id=dia.orden_estacion_dia_id,
                spots_verificados=verificado,
                fecha_verificacion=hoy,
                notas_verificacion=(
                    input_.notas_transmision if dia.fecha_transmision in overrides else None
                ),
                reconciliada=True,
                created_by=usuario_id,
            )
            db.add(verificacion)
            # Sin `relationship()` entre Verificacion e Incidencia (este módulo no las usa),
            # el unit-of-work de SQLAlchemy no conoce la dependencia entre ambas tablas y
            # puede intentar insertar la Incidencia ANTES que su Verificacion en el mismo
            # flush → viola fk_incidencia_verificacion. flush() fuerza el INSERT de
            # Verificacion primero, dentro de la misma transacción (no hace commit).
            db.flush()

            diferencia = verificado - programado_efectivo
            if diferencia != 0:
                db.add(
                    Incidencia(
                        incidencia_id=uuid4(),
                        verificacion_id=verificacion.verificacion_id,
                        orden_estacion_id=obj.orden_estacion_id,
                        tipo_incidencia=(
                            TipoIncidencia.FALTANTE.value
                            if diferencia < 0
                            else TipoIncidencia.EXCEDENTE.value
                        ),
                        spots_ordenados=programado_efectivo,
                        spots_ejecutados=verificado,
                        diferencia_spots=diferencia,
                        descripcion_incidencia=input_.notas_transmision,
                        fecha_incidencia=dia.fecha_transmision,
                        resolucion=ResolucionIncidencia.PENDIENTE.value,
                        monto_ajuste=(Decimal(diferencia) * obj.precio_spot).quantize(CENTAVOS),
                    )
                )

        obj.testigos_url = input_.testigos_url
        obj.testigos_ubicacion_alterna = input_.testigos_ubicacion_alterna
        obj.notas_transmision = input_.notas_transmision
        obj.reporte_reales_ref = input_.reporte_reales_ref
        obj.estatus = EstatusOrdenEstacion.CERRADA.value

        hermanas = db.scalars(
            select(OrdenEstacion).where(OrdenEstacion.orden_id == obj.orden_id)
        ).all()
        if all(
            h.estatus == EstatusOrdenEstacion.CERRADA.value
            for h in hermanas
            if h.orden_estacion_id != obj.orden_estacion_id
        ):
            oc = db.get(OrdenCliente, obj.orden_id)
            if oc is not None and oc.estatus_orden == EstatusOrden.EN_TRANSMISION.value:
                oc.estatus_orden = EstatusOrden.EN_VERIFICACION.value

        db.commit()
        db.refresh(obj)
        return self._to_read(obj)


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_orden_estacion_service(db: Session = Depends(get_db)) -> OrdenEstacionService:
    repo = OrdenEstacionRepository(
        db,
        OrdenEstacion,
        search_columns=[OrdenEstacion.folio_orden_estacion],
        default_order_by=[OrdenEstacion.folio_orden_estacion],
    )
    return OrdenEstacionService(repo)


router_estaciones = APIRouter(prefix="/estaciones", tags=["ordenes:estaciones"])


@router_estaciones.get("", response_model=Page[OrdenEstacionRead])
def listar_ordenes_estacion(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Búsqueda por folio o número de orden de estación"),
    orden_id: uuid.UUID | None = Query(None, description="Acota a las OE de una OrdenCliente"),
    estacion_id: uuid.UUID | None = Query(None),
    plaza_id: uuid.UUID | None = Query(None),
    anunciante_id: uuid.UUID | None = Query(None),
    estatus: EstatusOrdenEstacion | None = Query(None, description="Filtro por estatus"),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> Page[OrdenEstacionRead]:
    return svc.list(
        OrdenEstacionListParams(
            page=page,
            size=size,
            q=q,
            orden_id=orden_id,
            estacion_id=estacion_id,
            plaza_id=plaza_id,
            anunciante_id=anunciante_id,
            estatus=estatus,
        )
    )


@router_estaciones.get("/{item_id}", response_model=OrdenEstacionRead)
def obtener_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    return svc.get(item_id)


@router_estaciones.get("/{item_id}/dias", response_model=list[OrdenEstacionDiaRead])
def listar_dias_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> Sequence[OrdenEstacionDiaRead]:
    """Periodo de transmisión día a día (ADR-030) de una OrdenEstacion, ordenado por fecha."""
    return svc.dias(item_id)


# ── Escritura (Tanda 5) ────────────────────────────────────────────────────────
@router_estaciones.post("", response_model=OrdenEstacionRead, status_code=201)
def crear_orden_estacion(
    payload: OrdenEstacionCreate,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:crear")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    """Asigna una estación a una OrdenCliente (Ventas). Hereda de la OC (anunciante,
    vendedor, agencia, categoría, producto, contrato, duración de spot) y de la
    Estación (plaza); calcula % de participación OIR e importes. 400 si la tarifa de
    estación excede la tarifa cliente o si excede el balance de spots de la orden."""
    return svc.create(payload, usuario)


@router_estaciones.post("/{item_id}/programados", response_model=OrdenEstacionRead)
def avanzar_programados_orden_estacion(
    item_id: uuid.UUID,
    payload: OrdenEstacionProgramadosIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    """2.1 → 2.2: confirma spots programados por día (solo excepciones; el resto queda
    igual a lo asignado). 409 si la OE no está en 'asignada'."""
    return svc.avanzar_programados(item_id, payload, usuario)


@router_estaciones.post("/{item_id}/reales", response_model=OrdenEstacionRead)
def avanzar_reales_orden_estacion(
    item_id: uuid.UUID,
    payload: OrdenEstacionRealesIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    """2.2 → 2.3: registra lo realmente transmitido (solo excepciones). Genera una
    `Verificacion` por CADA día (spec) y una `Incidencia` automática por cada día con
    diferencia. 409 si la OE no está en 'en_transmision'. Si todas las OE de la OC
    quedan 'cerrada', la OC pasa a 'en_verificacion'."""
    return svc.avanzar_reales(item_id, payload, usuario)
