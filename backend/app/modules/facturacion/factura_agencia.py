"""FacturaAgencia + FacturaAgenciaOrden (F2) — factura que OIR RECIBE de la agencia por
su comisión.

Igual que `FacturaAfiliado`, es un COSTO y lo captura **CxP** (permiso `costos:*`).

ADR nuevo (petición del usuario, con captura, 2026-11-06) — SUSTITUYE el criterio de
ADR-079: la relación con `OrdenCliente` deja de ser 1:1-por-factura (un solo `orden_id`
en la cabecera) y pasa a ser **N:M vía tabla puente** `FacturaAgenciaOrden`, mismo
patrón que `FacturaAfiliadoOrden` en F2 — una factura de agencia puede acumular VARIAS
órdenes. A diferencia de `FacturaAfiliadoOrden` (que reparte un monto YA capturado en la
factura), aquí el monto de cada fila se CALCULA: `OrdenCliente.total *
porcentaje_comision / 100`, usando el `%` YA PACTADO en esa orden
(`OrdenCliente.porcentaje_comision_agencia_snap`), con el default del catálogo Agencia
como respaldo si la orden no trae snapshot — cada orden conserva el suyo, nunca un `%`
único para toda la factura.

`monto_factura_agencia`/`iva_factura_agencia`/`total_factura_agencia` DEJAN de
capturarse a mano (petición del usuario: "no se captura Subtotal manual, se vuelve un
campo calculado") — se derivan de la suma de comisiones de las órdenes elegidas, con el
IVA a la tasa central (a diferencia de `FacturaAfiliado`, donde el IVA SÍ es "Manual"
porque ahí se reconcilia contra una factura real de un tercero con posibles retenciones;
aquí ya no hay semejante reconciliación que hacer, es 100% lo que el sistema calculó).

El orden puede seguir apareciendo en varias facturas de agencia distintas (no cambia esa
regla de ADR-079: "una OC puede tener varias facturas de agencia"), pero no repetida
dentro de la MISMA factura (`UniqueConstraint` en la puente).

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
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    Unicode,
    UniqueConstraint,
    Uuid,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
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

#: Misma tasa central que `factura_cliente.py` — aquí el IVA SÍ se calcula (a diferencia
#: de `FacturaAfiliado`, que lo captura porque reconcilia contra una factura real de un
#: tercero con posibles retenciones: esta factura ya no reconcilia nada, es 100% lo que
#: el sistema calculó a partir de las órdenes elegidas).
IVA_RATE = Decimal(str(settings.iva_rate))


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
        # Invariante de suma exacta con `ROUND(x, 2)` en ambos lados (ADR-039).
        CheckConstraint(
            "ROUND(total_factura_agencia, 2) = "
            "ROUND(monto_factura_agencia + iva_factura_agencia, 2)",
            name="ck_factura_agencia_total_suma",
        ),
        # NUEVO: a diferencia de FacturaAfiliado, aquí el IVA SÍ se calcula a la tasa
        # central (ya no se captura a mano) — se escribe la tasa LITERAL 0.16 porque un
        # CHECK no puede leer `settings.iva_rate` (mismo criterio que `factura_cliente.py`).
        CheckConstraint(
            "ROUND(iva_factura_agencia, 2) = ROUND(monto_factura_agencia * 0.16, 2)",
            name="ck_factura_agencia_iva_tasa",
        ),
    )

    factura_agencia_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    agencia_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("agencia.agencia_id", name="fk_factura_agencia_agencia", ondelete="NO ACTION")
    )
    folio_factura_agencia: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    fecha_factura_agencia: Mapped[date] = mapped_column(fecha_sql())

    # Los 3 se CALCULAN en el servicio, suma de las `FacturaAgenciaOrden` de esta
    # factura — ya NO se aceptan como entrada del cliente (ADR nuevo, ver docstring).
    monto_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_factura_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Alias semántico de `monto_factura_agencia` (son el mismo valor): se conserva como
    # columna aparte porque la pantalla aprobada ya lo mostraba con este nombre en
    # "Monto comisión" — evita renombrar esa sección de la UI.
    comision_agencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    # CLAVE del almacenamiento (S3/local), no una ruta de disco (ADR-042).
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    # ADITIVO (ADR-079, mismo criterio que ADR-070 en `FacturaAfiliado`): la factura de
    # la agencia se sube en PDF y XML por separado. `archivo_nombre`/`archivo_path`
    # (arriba) quedan sin tocar por compatibilidad, aunque en la práctica no los llena
    # ningún formulario.
    archivo_pdf_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    archivo_xml_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    estatus_factura_agencia: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusFacturaProveedor.RECIBIDA.value
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("usuario.usuario_id", name="fk_factura_agencia_created_by", ondelete="NO ACTION")
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # ADITIVO (la spec no lo pide) — ver `factura_afiliado.py`.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class FacturaAgenciaOrden(Base):
    """Tabla puente N:M (ADR nuevo): acumula las órdenes elegidas para UNA factura de
    agencia. `porcentaje_comision_snap` es el `%` YA PACTADO de esa orden específica
    (`OrdenCliente.porcentaje_comision_agencia_snap`, con el default del catálogo Agencia
    como respaldo) — cada orden conserva el suyo, se congela al agregarla (si el
    catálogo o la orden cambian después, esta fila no se recalcula sola).
    `comision_calculada = OrdenCliente.total * porcentaje_comision_snap / 100`.
    """

    __tablename__ = "factura_agencia_orden"
    __table_args__ = (
        UniqueConstraint(
            "factura_agencia_id", "orden_id", name="uq_factura_agencia_orden_factura_oc"
        ),
        CheckConstraint("comision_calculada >= 0", name="ck_factura_agencia_orden_comision"),
        CheckConstraint(
            "porcentaje_comision_snap >= 0 AND porcentaje_comision_snap <= 100",
            name="ck_factura_agencia_orden_pct",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    factura_agencia_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_agencia.factura_agencia_id",
            name="fk_factura_agencia_orden_factura",
            ondelete="NO ACTION",
        )
    )
    orden_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "orden_cliente.orden_id", name="fk_factura_agencia_orden_oc", ondelete="NO ACTION"
        )
    )
    porcentaje_comision_snap: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    comision_calculada: Mapped[Decimal] = mapped_column(Numeric(14, 2))


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaAgenciaOrdenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_agencia_id: uuid.UUID
    orden_id: uuid.UUID
    porcentaje_comision_snap: Decimal
    comision_calculada: Decimal
    # Se resuelven en el servicio, en lote (mismo criterio que `FacturaAfiliadoOrdenRead`):
    # sin esto, la lista de órdenes asignadas solo podía mostrar el UUID crudo de la OC.
    folio_orden: str = ""
    numero_orden_cliente: str = ""
    anunciante: str | None = None
    producto: str | None = None
    orden_total: Decimal | None = None


class FacturaAgenciaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_agencia_id: uuid.UUID
    agencia_id: uuid.UUID
    folio_factura_agencia: str | None = None
    fecha_factura_agencia: date
    monto_factura_agencia: Decimal
    iva_factura_agencia: Decimal
    total_factura_agencia: Decimal
    comision_agencia: Decimal
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    archivo_pdf_path: str | None = None
    archivo_xml_path: str | None = None
    estatus_factura_agencia: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    # Se resuelven en el servicio, en lote — mismo criterio que `agencia` en la versión
    # anterior de este schema.
    agencia: str | None = None
    # Cuántas OrdenCliente tiene esta factura (columna "Órdenes asig." de la lista) —
    # mismo criterio que `ordenes_asignadas` en `FacturaAfiliadoRead`.
    ordenes_asignadas: int = 0


class OrdenClienteFacturableAgenciaRead(BaseModel):
    """Fila del combo "Buscar y agregar" (alta/edición de FacturaAgencia): una OC
    `orden_cerrada` de la agencia elegida, con su `total` y el `%` que se usaría si se
    agrega — el de la ORDEN (`porcentaje_comision_agencia_snap`) si lo tiene, si no el
    default del catálogo de la agencia (mismo respaldo que usa el servicio al calcular)."""

    model_config = ConfigDict(from_attributes=True)

    orden_id: uuid.UUID
    folio_orden: str
    numero_orden_cliente: str
    anunciante: str | None = None
    producto: str | None = None
    total: Decimal
    porcentaje_comision_agencia_snap: Decimal | None = None
    porcentaje_comision_agencia_default: Decimal | None = None


class FacturaAgenciaListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    agencia_id: uuid.UUID | None = None
    estatus_factura_agencia: str | None = None


# ── Schemas de escritura (Tanda 2) ───────────────────────────────────────────────
class FacturaAgenciaCreate(BaseModel):
    """Captura de CxP. `monto_factura_agencia`/`iva_factura_agencia`/
    `total_factura_agencia`/`comision_agencia` se CALCULAN — suma de las comisiones de
    las órdenes elegidas, cada una con su propio `%` ya pactado."""

    model_config = ConfigDict(extra="forbid")

    agencia_id: uuid.UUID
    folio_factura_agencia: str | None = Field(default=None, max_length=50)
    fecha_factura_agencia: date
    archivo_nombre: str | None = Field(default=None, max_length=255)
    archivo_path: str | None = Field(default=None, max_length=500)
    archivo_pdf_path: str | None = Field(default=None, max_length=500)
    archivo_xml_path: str | None = Field(default=None, max_length=500)
    # Órdenes elegidas en el combo "Buscar y agregar" (al menos 1: sin órdenes no hay
    # comisión que calcular). Cada una debe existir; el mismo orden puede estar en OTRAS
    # facturas de agencia (parcialidades, ADR-079), pero no repetida en ESTA.
    ordenes_ids: list[uuid.UUID] = Field(default_factory=list)


class FacturaAgenciaUpdate(BaseModel):
    """Edición: hace todo lo que hace el alta (mismo criterio que ADR-087 en
    `FacturaAfiliado`) — puede reasignar la agencia y editar qué órdenes tiene
    asignadas. `ordenes_ids` reconcilia EXACTAMENTE como pide la lista (agrega, quita,
    deja intactas las que siguen); `None` = no tocar, `[]` = quitarlas todas (aunque
    entonces la factura se queda sin comisión que mostrar)."""

    model_config = ConfigDict(extra="forbid")

    agencia_id: uuid.UUID | None = None
    folio_factura_agencia: str | None = Field(default=None, max_length=50)
    fecha_factura_agencia: date | None = None
    archivo_nombre: str | None = Field(default=None, max_length=255)
    archivo_path: str | None = Field(default=None, max_length=500)
    archivo_pdf_path: str | None = Field(default=None, max_length=500)
    archivo_xml_path: str | None = Field(default=None, max_length=500)
    ordenes_ids: list[uuid.UUID] | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaAgenciaRepository(BaseRepository[FacturaAgencia]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        agencia_id = getattr(params, "agencia_id", None)
        if agencia_id is not None:
            stmt = stmt.where(FacturaAgencia.agencia_id == agencia_id)
        estatus = getattr(params, "estatus_factura_agencia", None)
        if estatus is not None:
            stmt = stmt.where(FacturaAgencia.estatus_factura_agencia == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(FacturaAgencia.folio_factura_agencia.ilike(patron))
        return stmt

    def listar_ordenes(self, factura_agencia_id: uuid.UUID) -> list[FacturaAgenciaOrden]:
        return list(
            self.db.scalars(
                select(FacturaAgenciaOrden)
                .where(FacturaAgenciaOrden.factura_agencia_id == factura_agencia_id)
                .order_by(FacturaAgenciaOrden.id)
            ).all()
        )


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaAgenciaService(
    BaseService[FacturaAgencia, FacturaAgenciaCreate, FacturaAgenciaUpdate, FacturaAgenciaRead]
):
    """Captura de CxP, acumulación de comisión sobre varias órdenes (cada una con su
    propio `%` pactado), y la misma máquina de estados que `FacturaAfiliado` (autorizar
    exige Dirección/Admin)."""

    read_schema = FacturaAgenciaRead
    entidad = "FacturaAgencia"

    def __init__(self, repo: FacturaAgenciaRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def _calcular_comision(self, total_orden: Decimal, porcentaje: Decimal) -> Decimal:
        """`comision = OrdenCliente.total * porcentaje / 100` (spec), sobre el **total**
        de la orden (con IVA), no sobre el subtotal."""
        return (Decimal(total_orden) * Decimal(porcentaje) / Decimal(100)).quantize(CENTAVOS)

    # ── Enriquecido de lectura ────────────────────────────────────────────────
    def _datos_agencia(self, facturas: list[FacturaAgenciaRead]) -> dict[uuid.UUID, str]:
        """Nombres de las agencias de una página, en UNA consulta — mismo patrón por
        lote que `_nombres_emisoras` en `factura_cliente.py`."""
        from app.modules.catalogos.agencia import Agencia

        ids = {f.agencia_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(Agencia.agencia_id, Agencia.nombre_agencia).where(Agencia.agencia_id.in_(ids))
        ).all()
        return {fila[0]: fila[1] for fila in filas}

    def _datos_oc(
        self, ordenes: list[FacturaAgenciaOrdenRead]
    ) -> dict[uuid.UUID, tuple[str, str, str | None, str | None, Decimal]]:
        """Folio/número/anunciante/producto/total de las OC de una página de filas de la
        puente, en UNA consulta — mismo patrón por lote que `_datos_oe` en
        `factura_afiliado.py`."""
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.ordenes.orden_cliente import OrdenCliente

        ids = {o.orden_id for o in ordenes}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(
                OrdenCliente.orden_id,
                OrdenCliente.folio_orden,
                OrdenCliente.numero_orden_cliente,
                Anunciante.nombre_comercial,
                OrdenCliente.producto,
                OrdenCliente.total,
            )
            .join(Anunciante, Anunciante.anunciante_id == OrdenCliente.anunciante_id)
            .where(OrdenCliente.orden_id.in_(ids))
        ).all()
        return {fila[0]: (fila[1], fila[2], fila[3], fila[4], fila[5]) for fila in filas}

    def _conteo_ordenes(self, facturas: list[FacturaAgenciaRead]) -> dict[uuid.UUID, int]:
        """Cuántas OrdenCliente tiene asignadas cada factura de una página, en UNA
        consulta (columna "Órdenes asig." de la lista) — mismo patrón que
        `_conteo_asignaciones` en `factura_afiliado.py`."""
        ids = {f.factura_agencia_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(FacturaAgenciaOrden.factura_agencia_id, func.count(FacturaAgenciaOrden.id))
            .where(FacturaAgenciaOrden.factura_agencia_id.in_(ids))
            .group_by(FacturaAgenciaOrden.factura_agencia_id)
        ).all()
        return {fila[0]: fila[1] for fila in filas}

    def _enriquecida(self, leida: FacturaAgenciaRead) -> FacturaAgenciaRead:
        leida.agencia = self._datos_agencia([leida]).get(leida.agencia_id)
        leida.ordenes_asignadas = self._conteo_ordenes([leida]).get(leida.factura_agencia_id, 0)
        return leida

    def list(self, params: ListParams) -> Page[FacturaAgenciaRead]:
        pagina = super().list(params)
        agencias = self._datos_agencia(pagina.items)
        conteos = self._conteo_ordenes(pagina.items)
        for f in pagina.items:
            f.agencia = agencias.get(f.agencia_id)
            f.ordenes_asignadas = conteos.get(f.factura_agencia_id, 0)
        return pagina

    def get(self, id_: Any) -> FacturaAgenciaRead:
        return self._enriquecida(super().get(id_))

    def ordenes(self, factura_agencia_id: uuid.UUID) -> list[FacturaAgenciaOrdenRead]:
        """Órdenes acumuladas en esta factura, con sus datos denormalizados — alimenta la
        sección "Órdenes asignadas" del detalle y el precargado al editar."""
        self._get_or_404(factura_agencia_id)
        leidas = [
            FacturaAgenciaOrdenRead.model_validate(o)
            for o in self._repo.listar_ordenes(factura_agencia_id)
        ]
        datos_oc = self._datos_oc(leidas)
        for o in leidas:
            folio, numero, anunciante, producto, total = datos_oc.get(
                o.orden_id, ("", "", None, None, None)
            )
            o.folio_orden = folio
            o.numero_orden_cliente = numero
            o.anunciante = anunciante
            o.producto = producto
            o.orden_total = total
        return leidas

    def ordenes_facturables(
        self, agencia_id: uuid.UUID
    ) -> list[OrdenClienteFacturableAgenciaRead]:
        """OC `orden_cerrada` de la agencia elegida — combo "Buscar y agregar" del
        alta/edición. No excluye OC que ya tengan otra factura de agencia: la relación
        sigue siendo N:M a propósito (parcialidades, ver docstring del módulo)."""
        from app.modules.catalogos.agencia import Agencia
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente

        db = self._repo.db
        agencia = db.get(Agencia, agencia_id)
        porcentaje_default = agencia.porcentaje_comision_agencia_default if agencia else None
        filas = db.execute(
            select(
                OrdenCliente.orden_id,
                OrdenCliente.folio_orden,
                OrdenCliente.numero_orden_cliente,
                Anunciante.nombre_comercial,
                OrdenCliente.producto,
                OrdenCliente.total,
                OrdenCliente.porcentaje_comision_agencia_snap,
            )
            .join(Anunciante, Anunciante.anunciante_id == OrdenCliente.anunciante_id)
            .where(
                OrdenCliente.agencia_id == agencia_id,
                OrdenCliente.estatus_orden == EstatusOrden.ORDEN_CERRADA.value,
            )
            .order_by(OrdenCliente.folio_orden)
        ).all()
        return [
            OrdenClienteFacturableAgenciaRead(
                orden_id=f.orden_id,
                folio_orden=f.folio_orden,
                numero_orden_cliente=f.numero_orden_cliente,
                anunciante=f.nombre_comercial,
                producto=f.producto,
                total=f.total,
                porcentaje_comision_agencia_snap=f.porcentaje_comision_agencia_snap,
                porcentaje_comision_agencia_default=porcentaje_default,
            )
            for f in filas
        ]

    def _validar_ordenes(
        self, agencia: Any, ids: list[uuid.UUID]
    ) -> list[tuple[Any, Decimal, Decimal]]:
        """Valida una lista de OC para el combo del alta/edición: sin repetidos, cada
        una debe existir y resolver un `%` de comisión (de la orden o, si no, del
        catálogo de la agencia) — devuelve `(OrdenCliente, porcentaje, comision)` ya
        calculados, en el mismo orden. Compartido por `create()`/`update()` (vía
        `_aplicar_ordenes()`)."""
        from app.modules.ordenes.orden_cliente import OrdenCliente

        db = self._repo.db
        resultado: list[tuple[Any, Decimal, Decimal]] = []
        vistos: set[uuid.UUID] = set()
        for oc_id in ids:
            if oc_id in vistos:
                raise DomainError(
                    "La misma orden no puede repetirse en la misma factura.",
                    detalles={"orden_id": str(oc_id)},
                )
            vistos.add(oc_id)
            oc = db.get(OrdenCliente, oc_id)
            if oc is None:
                raise DomainError(
                    "La OrdenCliente indicada no existe.", detalles={"orden_id": str(oc_id)}
                )
            # `Agencia.porcentaje_comision_agencia_default` es NOT NULL (default 0 si no
            # se capturó) — siempre hay un `%` que resolver, aunque sea 0.
            porcentaje = oc.porcentaje_comision_agencia_snap
            if porcentaje is None:
                porcentaje = agencia.porcentaje_comision_agencia_default
            resultado.append((oc, porcentaje, self._calcular_comision(oc.total, porcentaje)))
        return resultado

    def _totales(
        self, validadas: list[tuple[Any, Decimal, Decimal]]
    ) -> tuple[Decimal, Decimal, Decimal]:
        """`(comision_total, iva, total)` — suma de las comisiones ya calculadas por
        `_validar_ordenes`, más IVA a la tasa central."""
        comision_total = sum((c for _, _, c in validadas), Decimal("0")).quantize(CENTAVOS)
        iva = (comision_total * IVA_RATE).quantize(CENTAVOS)
        return comision_total, iva, (comision_total + iva).quantize(CENTAVOS)

    def _aplicar_ordenes(
        self, obj: FacturaAgencia, validadas: list[tuple[Any, Decimal, Decimal]]
    ) -> None:
        """Deja las órdenes de la factura EXACTAMENTE como pide `validadas` (ya
        validadas por `_validar_ordenes`): agrega las nuevas y quita las que ya no
        están — las que siguen se dejan intactas, sin recalcular su `%`/comisión
        congelados aunque la orden o el catálogo hayan cambiado desde que se agregó
        (mismo criterio que `_aplicar_asignaciones` en `factura_afiliado.py`)."""
        db = self._repo.db
        existentes = {
            o.orden_id: o for o in self._repo.listar_ordenes(obj.factura_agencia_id)
        }
        ids_nuevos = {oc.orden_id for oc, _, _ in validadas}

        for oid, fila in existentes.items():
            if oid not in ids_nuevos:
                db.delete(fila)

        for oc, porcentaje, comision in validadas:
            if oc.orden_id in existentes:
                continue
            db.add(
                FacturaAgenciaOrden(
                    id=uuid4(),
                    factura_agencia_id=obj.factura_agencia_id,
                    orden_id=oc.orden_id,
                    porcentaje_comision_snap=porcentaje,
                    comision_calculada=comision,
                )
            )
        comision_total, iva, total = self._totales(validadas)
        db.commit()
        self._repo.update(
            obj,
            {
                "monto_factura_agencia": comision_total,
                "iva_factura_agencia": iva,
                "total_factura_agencia": total,
                "comision_agencia": comision_total,
            },
        )

    def create(self, data: FacturaAgenciaCreate, usuario: CurrentUser) -> FacturaAgenciaRead:
        from app.modules.catalogos.agencia import Agencia
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        agencia = db.get(Agencia, data.agencia_id)
        if agencia is None:
            raise DomainError(
                "La agencia indicada no existe.", detalles={"agencia_id": str(data.agencia_id)}
            )
        validadas = self._validar_ordenes(agencia, data.ordenes_ids)
        if not validadas:
            raise DomainError("Agrega al menos una orden para calcular la comisión.")

        comision_total, iva, total = self._totales(validadas)
        obj = FacturaAgencia(
            factura_agencia_id=uuid4(),
            **data.model_dump(exclude={"ordenes_ids"}),
            monto_factura_agencia=comision_total,
            iva_factura_agencia=iva,
            total_factura_agencia=total,
            comision_agencia=comision_total,
            estatus_factura_agencia=EstatusFacturaProveedor.RECIBIDA.value,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        for oc, porcentaje, comision in validadas:
            db.add(
                FacturaAgenciaOrden(
                    id=uuid4(),
                    factura_agencia_id=obj.factura_agencia_id,
                    orden_id=oc.orden_id,
                    porcentaje_comision_snap=porcentaje,
                    comision_calculada=comision,
                )
            )
        db.commit()
        db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def update(
        self, id_: Any, data: FacturaAgenciaUpdate, usuario: CurrentUser
    ) -> FacturaAgenciaRead:
        """Edición solo antes de autorizar (mismo candado que `FacturaAfiliado`). Hace
        todo lo que hace el alta: puede reasignar la agencia y editar qué órdenes tiene
        asignadas — ambas se validan ANTES de tocar la factura."""
        from app.modules.catalogos.agencia import Agencia

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
        ordenes_ids = payload.pop("ordenes_ids", None)

        agencia_nueva = None
        if "agencia_id" in payload:
            agencia_nueva = self._repo.db.get(Agencia, payload["agencia_id"])
            if agencia_nueva is None:
                raise DomainError(
                    "La agencia indicada no existe.",
                    detalles={"agencia_id": str(payload["agencia_id"])},
                )
        # Se valida ANTES de tocar la factura: si la lista trae una orden repetida,
        # inexistente o sin `%` resoluble, la edición se rechaza completa.
        validadas = None
        if ordenes_ids is not None:
            agencia_para_validar = (
                agencia_nueva if agencia_nueva is not None
                else self._repo.db.get(Agencia, obj.agencia_id)
            )
            validadas = self._validar_ordenes(agencia_para_validar, ordenes_ids)

        obj = self._repo.update(obj, payload)

        if validadas is not None:
            self._aplicar_ordenes(obj, validadas)

        return self._enriquecida(self._to_read(obj))

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
            return self._enriquecida(self._to_read(obj))  # idempotente
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
        return self._enriquecida(self._to_read(obj))

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
    # Más reciente primero (mismo criterio que `FacturaAfiliado`, ADR-086): se ordena
    # por `created_at`, el momento real del alta, no por `fecha_factura_agencia`.
    return FacturaAgenciaService(
        FacturaAgenciaRepository(
            db,
            FacturaAgencia,
            default_order_by=[
                FacturaAgencia.created_at.desc(),
                FacturaAgencia.factura_agencia_id,
            ],
        )
    )


router_agencias = APIRouter(prefix="/agencias", tags=["facturacion:agencias"])


@router_agencias.get("", response_model=Page[FacturaAgenciaRead])
def listar_facturas_agencia(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en el folio externo de la agencia"),
    agencia_id: uuid.UUID | None = Query(None),
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
            estatus_factura_agencia=estatus_factura_agencia,
        )
    )


@router_agencias.get(
    "/ordenes-facturables", response_model=list[OrdenClienteFacturableAgenciaRead]
)
def listar_ordenes_facturables_agencia(
    agencia_id: uuid.UUID = Query(...),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> list[OrdenClienteFacturableAgenciaRead]:
    """Combo "Buscar y agregar" del alta/edición: OC `orden_cerrada` de esa agencia.
    Declarado ANTES de `/{item_id}` — si no, FastAPI intentaría parsear
    "ordenes-facturables" como UUID de `item_id` y respondería 422."""
    return svc.ordenes_facturables(agencia_id)


@router_agencias.get("/{item_id}", response_model=FacturaAgenciaRead)
def obtener_factura_agencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    return svc.get(item_id)


@router_agencias.get("/{item_id}/ordenes", response_model=list[FacturaAgenciaOrdenRead])
def listar_ordenes_factura_agencia(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> list[FacturaAgenciaOrdenRead]:
    """Órdenes acumuladas en esta factura (detalle + precargado al editar)."""
    return svc.ordenes(item_id)


# ── Escritura + transiciones (Tanda 2) ────────────────────────────────────────
@router_agencias.post("", response_model=FacturaAgenciaRead, status_code=201)
def crear_factura_agencia(
    payload: FacturaAgenciaCreate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:crear")),
    svc: FacturaAgenciaService = Depends(get_factura_agencia_service),
) -> FacturaAgenciaRead:
    """El subtotal/IVA/total/comisión se calculan como la suma de
    `OrdenCliente.total * porcentaje / 100` de cada orden elegida, cada una con su
    propio `%` (el de la orden, o si no el default del catálogo Agencia)."""
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
