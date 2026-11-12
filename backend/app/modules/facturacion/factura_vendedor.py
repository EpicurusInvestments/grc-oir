"""FacturaVendedor + FacturaVendedorOrden (F2) — factura que OIR RECIBE del vendedor
por su comisión.

Entidad NUEVA, fuera de la especificación BD v2 (33 entidades): el usuario la pidió
como paridad exacta de `FacturaAgencia` — así como OIR necesita procesar la comisión de
la agencia, también necesita procesar la del vendedor PRINCIPAL de la orden (no el
secundario — confirmado con el usuario). Por ser nueva, no carga campos legado
(`archivo_nombre`/`archivo_path` genéricos que sí tienen `FacturaAfiliado`/
`FacturaAgencia` por ser literales de la spec): va directo a
`archivo_pdf_path`/`archivo_xml_path`, sin nada que "migrar después".

ADR nuevo (petición del usuario, con captura, 2026-11-06) — mismo cambio que ADR-239
hizo para `FacturaAgencia`, aplicado aquí en la MISMA entrega (petición explícita del
usuario: "hazlo para todos" de una vez): la relación con `OrdenCliente` deja de ser
1:1-por-factura (`orden_id` único en la cabecera) y pasa a ser **N:M vía
`FacturaVendedorOrden`**, mismo patrón que `FacturaAgenciaOrden`/`FacturaAfiliadoOrden` —
una factura de vendedor acumula VARIAS órdenes, cada una con su propio `%` ya pactado
(`OrdenCliente.porcentaje_comision_vendedor_principal_snap`, con el default del catálogo
Vendedor como respaldo).

`monto_factura_vendedor`/`iva_factura_vendedor`/`total_factura_vendedor` DEJAN de
capturarse a mano — se derivan de la suma de comisiones de las órdenes elegidas, con el
IVA a la tasa central (a diferencia de `FacturaAfiliado`, donde el IVA SÍ es "Manual").

ADR-264 (petición del usuario, con captura) ajusta dos reglas más, igual que hizo para
`FacturaAgencia`:
- El combo "Buscar y agregar" ya NO sugiere una orden que ya esté en OTRA factura de
  vendedor (antes, parcialidades sin límite). La validación DURA (`_validar_ordenes`)
  no cambia: sigue aceptando un alta que mande explícito el id de una orden ya
  facturada.
- Autorizar (`autorizar()`) se bloquea si alguna orden asignada todavía no está
  `cobrada` — OIR no debe pagarle la comisión al vendedor antes de haber cobrado esa
  orden al cliente.

La misma orden puede repetirse en facturas distintas si se fuerza por API directa, pero
no dentro de la MISMA factura (`UniqueConstraint` en la puente).
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

#: Misma tasa central que `factura_agencia.py` — aquí el IVA SÍ se calcula (a diferencia
#: de `FacturaAfiliado`, que lo captura porque reconcilia contra una factura real de un
#: tercero con posibles retenciones: esta factura ya no reconcilia nada).
IVA_RATE = Decimal(str(settings.iva_rate))


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaVendedor(Base):
    __tablename__ = "factura_vendedor"
    __table_args__ = (
        CheckConstraint(
            f"estatus_factura_vendedor IN ({_ESTATUS_PROVEEDOR_SQL})",
            name="ck_factura_vendedor_estatus",
        ),
        CheckConstraint("monto_factura_vendedor >= 0", name="ck_factura_vendedor_monto"),
        CheckConstraint("iva_factura_vendedor >= 0", name="ck_factura_vendedor_iva"),
        CheckConstraint("total_factura_vendedor >= 0", name="ck_factura_vendedor_total"),
        CheckConstraint("comision_vendedor >= 0", name="ck_factura_vendedor_comision"),
        CheckConstraint(
            "ROUND(total_factura_vendedor, 2) = "
            "ROUND(monto_factura_vendedor + iva_factura_vendedor, 2)",
            name="ck_factura_vendedor_total_suma",
        ),
        # NUEVO: a diferencia de FacturaAfiliado, aquí el IVA SÍ se calcula a la tasa
        # central (ya no se captura a mano) — tasa LITERAL 0.16 (mismo criterio que
        # `factura_agencia.py`/`factura_cliente.py`: un CHECK no puede leer `settings`).
        CheckConstraint(
            "ROUND(iva_factura_vendedor, 2) = ROUND(monto_factura_vendedor * 0.16, 2)",
            name="ck_factura_vendedor_iva_tasa",
        ),
    )

    factura_vendedor_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    vendedor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "vendedor.vendedor_id", name="fk_factura_vendedor_vendedor", ondelete="NO ACTION"
        )
    )
    folio_factura_vendedor: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    fecha_factura_vendedor: Mapped[date] = mapped_column(fecha_sql())

    # Los 3 se CALCULAN en el servicio, suma de las `FacturaVendedorOrden` de esta
    # factura — ya NO se aceptan como entrada del cliente (ADR nuevo, ver docstring).
    monto_factura_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_factura_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Alias semántico de `monto_factura_vendedor` (mismo valor) — mismo criterio que
    # `FacturaAgencia.comision_agencia`: la pantalla aprobada lo muestra en "Monto
    # comisión".
    comision_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    archivo_pdf_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    archivo_xml_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    estatus_factura_vendedor: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusFacturaProveedor.RECIBIDA.value
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "usuario.usuario_id", name="fk_factura_vendedor_created_by", ondelete="NO ACTION"
        )
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class FacturaVendedorOrden(Base):
    """Tabla puente N:M (ADR nuevo, mismo patrón que `FacturaAgenciaOrden`): acumula las
    órdenes elegidas para UNA factura de vendedor. `porcentaje_comision_snap` es el `%`
    YA PACTADO de esa orden específica
    (`OrdenCliente.porcentaje_comision_vendedor_principal_snap`, con el default del
    catálogo Vendedor como respaldo) — se congela al agregarla.
    `comision_calculada = OrdenCliente.total * porcentaje_comision_snap / 100`.
    """

    __tablename__ = "factura_vendedor_orden"
    __table_args__ = (
        UniqueConstraint(
            "factura_vendedor_id", "orden_id", name="uq_factura_vendedor_orden_factura_oc"
        ),
        CheckConstraint("comision_calculada >= 0", name="ck_factura_vendedor_orden_comision"),
        CheckConstraint(
            "porcentaje_comision_snap >= 0 AND porcentaje_comision_snap <= 100",
            name="ck_factura_vendedor_orden_pct",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    factura_vendedor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_vendedor.factura_vendedor_id",
            name="fk_factura_vendedor_orden_factura",
            ondelete="NO ACTION",
        )
    )
    orden_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "orden_cliente.orden_id", name="fk_factura_vendedor_orden_oc", ondelete="NO ACTION"
        )
    )
    porcentaje_comision_snap: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    comision_calculada: Mapped[Decimal] = mapped_column(Numeric(14, 2))


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaVendedorOrdenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_vendedor_id: uuid.UUID
    orden_id: uuid.UUID
    porcentaje_comision_snap: Decimal
    comision_calculada: Decimal
    # Se resuelven en el servicio, en lote (mismo criterio que `FacturaAgenciaOrdenRead`).
    folio_orden: str = ""
    numero_orden_cliente: str = ""
    anunciante: str | None = None
    producto: str | None = None
    orden_total: Decimal | None = None


class FacturaVendedorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_vendedor_id: uuid.UUID
    vendedor_id: uuid.UUID
    folio_factura_vendedor: str | None = None
    fecha_factura_vendedor: date
    monto_factura_vendedor: Decimal
    iva_factura_vendedor: Decimal
    total_factura_vendedor: Decimal
    comision_vendedor: Decimal
    archivo_pdf_path: str | None = None
    archivo_xml_path: str | None = None
    estatus_factura_vendedor: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    # Se resuelven en el servicio, en lote.
    vendedor: str | None = None
    ordenes_asignadas: int = 0


class OrdenClienteFacturableVendedorRead(BaseModel):
    """Fila del combo "Buscar y agregar" (alta/edición de FacturaVendedor): una OC
    `orden_cerrada` donde el vendedor elegido es el `vendedor_principal_id`, con su
    `total` y el `%` que se usaría si se agrega — el de la ORDEN
    (`porcentaje_comision_vendedor_principal_snap`) si lo tiene, si no el default del
    catálogo del vendedor."""

    model_config = ConfigDict(from_attributes=True)

    orden_id: uuid.UUID
    folio_orden: str
    numero_orden_cliente: str
    anunciante: str | None = None
    producto: str | None = None
    total: Decimal
    porcentaje_comision_vendedor_snap: Decimal | None = None
    porcentaje_comision_vendedor_default: Decimal | None = None


class FacturaVendedorListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    vendedor_id: uuid.UUID | None = None
    estatus_factura_vendedor: str | None = None


# ── Schemas de escritura (Tanda 2) ───────────────────────────────────────────────
class FacturaVendedorCreate(BaseModel):
    """Captura de CxP. `monto_factura_vendedor`/`iva_factura_vendedor`/
    `total_factura_vendedor`/`comision_vendedor` se CALCULAN — suma de las comisiones de
    las órdenes elegidas, cada una con su propio `%` ya pactado."""

    model_config = ConfigDict(extra="forbid")

    vendedor_id: uuid.UUID
    folio_factura_vendedor: str | None = Field(default=None, max_length=50)
    fecha_factura_vendedor: date
    archivo_pdf_path: str | None = Field(default=None, max_length=500)
    archivo_xml_path: str | None = Field(default=None, max_length=500)
    # Órdenes elegidas en el combo "Buscar y agregar" (al menos 1). Cada una debe
    # existir; el mismo orden puede estar en OTRAS facturas de vendedor (parcialidades),
    # pero no repetida en ESTA.
    ordenes_ids: list[uuid.UUID] = Field(default_factory=list)


class FacturaVendedorUpdate(BaseModel):
    """Edición: hace todo lo que hace el alta — puede reasignar el vendedor y editar
    qué órdenes tiene asignadas. `ordenes_ids` reconcilia EXACTAMENTE como pide la
    lista; `None` = no tocar, `[]` = quitarlas todas."""

    model_config = ConfigDict(extra="forbid")

    vendedor_id: uuid.UUID | None = None
    folio_factura_vendedor: str | None = Field(default=None, max_length=50)
    fecha_factura_vendedor: date | None = None
    archivo_pdf_path: str | None = Field(default=None, max_length=500)
    archivo_xml_path: str | None = Field(default=None, max_length=500)
    ordenes_ids: list[uuid.UUID] | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaVendedorRepository(BaseRepository[FacturaVendedor]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        vendedor_id = getattr(params, "vendedor_id", None)
        if vendedor_id is not None:
            stmt = stmt.where(FacturaVendedor.vendedor_id == vendedor_id)
        estatus = getattr(params, "estatus_factura_vendedor", None)
        if estatus is not None:
            stmt = stmt.where(FacturaVendedor.estatus_factura_vendedor == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(FacturaVendedor.folio_factura_vendedor.ilike(patron))
        return stmt

    def listar_ordenes(self, factura_vendedor_id: uuid.UUID) -> list[FacturaVendedorOrden]:
        return list(
            self.db.scalars(
                select(FacturaVendedorOrden)
                .where(FacturaVendedorOrden.factura_vendedor_id == factura_vendedor_id)
                .order_by(FacturaVendedorOrden.id)
            ).all()
        )


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaVendedorService(
    BaseService[FacturaVendedor, FacturaVendedorCreate, FacturaVendedorUpdate, FacturaVendedorRead]
):
    """Captura de CxP, acumulación de comisión sobre varias órdenes (cada una con su
    propio `%` pactado), y la misma máquina de estados que `FacturaAfiliado`/
    `FacturaAgencia` (autorizar exige Dirección/Admin)."""

    read_schema = FacturaVendedorRead
    entidad = "FacturaVendedor"

    def __init__(self, repo: FacturaVendedorRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def _calcular_comision(self, total_orden: Decimal, porcentaje: Decimal) -> Decimal:
        """`comision = OrdenCliente.total * porcentaje / 100` — sobre el **total** de la
        orden (con IVA), no sobre el subtotal."""
        return (Decimal(total_orden) * Decimal(porcentaje) / Decimal(100)).quantize(CENTAVOS)

    # ── Enriquecido de lectura ────────────────────────────────────────────────
    def _datos_vendedor(self, facturas: list[FacturaVendedorRead]) -> dict[uuid.UUID, str]:
        """Nombres de los vendedores de una página, en UNA consulta."""
        from app.modules.catalogos.vendedor import Vendedor

        ids = {f.vendedor_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(Vendedor.vendedor_id, Vendedor.nombre_vendedor).where(
                Vendedor.vendedor_id.in_(ids)
            )
        ).all()
        return {fila[0]: fila[1] for fila in filas}

    def _datos_oc(
        self, ordenes: list[FacturaVendedorOrdenRead]
    ) -> dict[uuid.UUID, tuple[str, str, str | None, str | None, Decimal]]:
        """Folio/número/anunciante/producto/total de las OC de una página de filas de la
        puente, en UNA consulta."""
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

    def _conteo_ordenes(self, facturas: list[FacturaVendedorRead]) -> dict[uuid.UUID, int]:
        """Cuántas OrdenCliente tiene asignadas cada factura de una página, en UNA
        consulta (columna "Órdenes asig." de la lista)."""
        ids = {f.factura_vendedor_id for f in facturas}
        if not ids:
            return {}
        filas = self._repo.db.execute(
            select(FacturaVendedorOrden.factura_vendedor_id, func.count(FacturaVendedorOrden.id))
            .where(FacturaVendedorOrden.factura_vendedor_id.in_(ids))
            .group_by(FacturaVendedorOrden.factura_vendedor_id)
        ).all()
        return {fila[0]: fila[1] for fila in filas}

    def _enriquecida(self, leida: FacturaVendedorRead) -> FacturaVendedorRead:
        leida.vendedor = self._datos_vendedor([leida]).get(leida.vendedor_id)
        leida.ordenes_asignadas = self._conteo_ordenes([leida]).get(
            leida.factura_vendedor_id, 0
        )
        return leida

    def list(self, params: ListParams) -> Page[FacturaVendedorRead]:
        pagina = super().list(params)
        vendedores = self._datos_vendedor(pagina.items)
        conteos = self._conteo_ordenes(pagina.items)
        for f in pagina.items:
            f.vendedor = vendedores.get(f.vendedor_id)
            f.ordenes_asignadas = conteos.get(f.factura_vendedor_id, 0)
        return pagina

    def get(self, id_: Any) -> FacturaVendedorRead:
        return self._enriquecida(super().get(id_))

    def ordenes(self, factura_vendedor_id: uuid.UUID) -> list[FacturaVendedorOrdenRead]:
        """Órdenes acumuladas en esta factura, con sus datos denormalizados."""
        self._get_or_404(factura_vendedor_id)
        leidas = [
            FacturaVendedorOrdenRead.model_validate(o)
            for o in self._repo.listar_ordenes(factura_vendedor_id)
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
        self, vendedor_id: uuid.UUID, excluir_de_factura_id: uuid.UUID | None = None
    ) -> list[OrdenClienteFacturableVendedorRead]:
        """OC donde el vendedor elegido es el `vendedor_principal_id`, ya `orden_cerrada`,
        `facturada` o `cobrada` — combo "Buscar y agregar" del alta/edición (NO se
        factura la comisión del vendedor secundario; ADR-264: antes solo `orden_cerrada`).

        Excluye las que YA tienen una `FacturaVendedorOrden` registrada en OTRA factura
        — mismo criterio que `FacturaAfiliadoService.ordenes_facturables`/
        `FacturaAgenciaService.ordenes_facturables` (ADR-264). Al EDITAR,
        `excluir_de_factura_id` es el id de esa misma factura: sus propias asignaciones
        no cuentan como "ya facturadas"."""
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import FROZEN_STATES_OC, OrdenCliente

        db = self._repo.db
        vendedor = db.get(Vendedor, vendedor_id)
        porcentaje_default = vendedor.porcentaje_comision_default if vendedor else None

        ya_facturadas_stmt = select(FacturaVendedorOrden.orden_id)
        if excluir_de_factura_id is not None:
            ya_facturadas_stmt = ya_facturadas_stmt.where(
                FacturaVendedorOrden.factura_vendedor_id != excluir_de_factura_id
            )
        ya_facturadas = set(db.scalars(ya_facturadas_stmt).all())

        filas = db.execute(
            select(
                OrdenCliente.orden_id,
                OrdenCliente.folio_orden,
                OrdenCliente.numero_orden_cliente,
                Anunciante.nombre_comercial,
                OrdenCliente.producto,
                OrdenCliente.total,
                OrdenCliente.porcentaje_comision_vendedor_principal_snap,
            )
            .join(Anunciante, Anunciante.anunciante_id == OrdenCliente.anunciante_id)
            .where(
                OrdenCliente.vendedor_principal_id == vendedor_id,
                OrdenCliente.estatus_orden.in_(FROZEN_STATES_OC),
            )
            .order_by(OrdenCliente.folio_orden)
        ).all()
        return [
            OrdenClienteFacturableVendedorRead(
                orden_id=f.orden_id,
                folio_orden=f.folio_orden,
                numero_orden_cliente=f.numero_orden_cliente,
                anunciante=f.nombre_comercial,
                producto=f.producto,
                total=f.total,
                porcentaje_comision_vendedor_snap=f.porcentaje_comision_vendedor_principal_snap,
                porcentaje_comision_vendedor_default=porcentaje_default,
            )
            for f in filas
            if f.orden_id not in ya_facturadas
        ]

    def _validar_ordenes(
        self, vendedor: Any, ids: list[uuid.UUID]
    ) -> list[tuple[Any, Decimal, Decimal]]:
        """Valida una lista de OC: sin repetidos, cada una debe existir y resolver un
        `%` de comisión (de la orden o, si no, del catálogo del vendedor) — devuelve
        `(OrdenCliente, porcentaje, comision)` ya calculados, en el mismo orden."""
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
            # `Vendedor.porcentaje_comision_default` es NOT NULL (default 0 si no se
            # capturó) — siempre hay un `%` que resolver, aunque sea 0.
            porcentaje = oc.porcentaje_comision_vendedor_principal_snap
            if porcentaje is None:
                porcentaje = vendedor.porcentaje_comision_default
            resultado.append((oc, porcentaje, self._calcular_comision(oc.total, porcentaje)))
        return resultado

    def _totales(
        self, validadas: list[tuple[Any, Decimal, Decimal]]
    ) -> tuple[Decimal, Decimal, Decimal]:
        comision_total = sum((c for _, _, c in validadas), Decimal("0")).quantize(CENTAVOS)
        iva = (comision_total * IVA_RATE).quantize(CENTAVOS)
        return comision_total, iva, (comision_total + iva).quantize(CENTAVOS)

    def _aplicar_ordenes(
        self, obj: FacturaVendedor, validadas: list[tuple[Any, Decimal, Decimal]]
    ) -> None:
        """Deja las órdenes de la factura EXACTAMENTE como pide `validadas` — agrega las
        nuevas y quita las que ya no están, deja intactas las que siguen (mismo criterio
        que `_aplicar_ordenes` en `factura_agencia.py`)."""
        db = self._repo.db
        existentes = {
            o.orden_id: o for o in self._repo.listar_ordenes(obj.factura_vendedor_id)
        }
        ids_nuevos = {oc.orden_id for oc, _, _ in validadas}

        for oid, fila in existentes.items():
            if oid not in ids_nuevos:
                db.delete(fila)

        for oc, porcentaje, comision in validadas:
            if oc.orden_id in existentes:
                continue
            db.add(
                FacturaVendedorOrden(
                    id=uuid4(),
                    factura_vendedor_id=obj.factura_vendedor_id,
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
                "monto_factura_vendedor": comision_total,
                "iva_factura_vendedor": iva,
                "total_factura_vendedor": total,
                "comision_vendedor": comision_total,
            },
        )

    def create(self, data: FacturaVendedorCreate, usuario: CurrentUser) -> FacturaVendedorRead:
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        vendedor = db.get(Vendedor, data.vendedor_id)
        if vendedor is None:
            raise DomainError(
                "El vendedor indicado no existe.", detalles={"vendedor_id": str(data.vendedor_id)}
            )
        validadas = self._validar_ordenes(vendedor, data.ordenes_ids)
        if not validadas:
            raise DomainError("Agrega al menos una orden para calcular la comisión.")

        comision_total, iva, total = self._totales(validadas)
        obj = FacturaVendedor(
            factura_vendedor_id=uuid4(),
            **data.model_dump(exclude={"ordenes_ids"}),
            monto_factura_vendedor=comision_total,
            iva_factura_vendedor=iva,
            total_factura_vendedor=total,
            comision_vendedor=comision_total,
            estatus_factura_vendedor=EstatusFacturaProveedor.RECIBIDA.value,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        for oc, porcentaje, comision in validadas:
            db.add(
                FacturaVendedorOrden(
                    id=uuid4(),
                    factura_vendedor_id=obj.factura_vendedor_id,
                    orden_id=oc.orden_id,
                    porcentaje_comision_snap=porcentaje,
                    comision_calculada=comision,
                )
            )
        db.commit()
        db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def update(
        self, id_: Any, data: FacturaVendedorUpdate, usuario: CurrentUser
    ) -> FacturaVendedorRead:
        """Edición solo antes de autorizar (mismo candado que `FacturaAgencia`). Hace
        todo lo que hace el alta: puede reasignar el vendedor y editar qué órdenes tiene
        asignadas — ambas se validan ANTES de tocar la factura."""
        from app.modules.catalogos.vendedor import Vendedor

        obj = self._get_or_404(id_)
        if obj.estatus_factura_vendedor not in (
            EstatusFacturaProveedor.RECIBIDA.value,
            EstatusFacturaProveedor.EN_REVISION.value,
        ):
            raise ConflictError(
                "Una factura autorizada o pagada ya no se edita.",
                detalles={"estatus_factura_vendedor": obj.estatus_factura_vendedor},
            )
        payload = data.model_dump(exclude_unset=True)
        ordenes_ids = payload.pop("ordenes_ids", None)

        vendedor_nuevo = None
        if "vendedor_id" in payload:
            vendedor_nuevo = self._repo.db.get(Vendedor, payload["vendedor_id"])
            if vendedor_nuevo is None:
                raise DomainError(
                    "El vendedor indicado no existe.",
                    detalles={"vendedor_id": str(payload["vendedor_id"])},
                )
        validadas = None
        if ordenes_ids is not None:
            vendedor_para_validar = (
                vendedor_nuevo if vendedor_nuevo is not None
                else self._repo.db.get(Vendedor, obj.vendedor_id)
            )
            validadas = self._validar_ordenes(vendedor_para_validar, ordenes_ids)

        obj = self._repo.update(obj, payload)

        if validadas is not None:
            self._aplicar_ordenes(obj, validadas)

        return self._enriquecida(self._to_read(obj))

    def transicionar(
        self,
        factura_vendedor_id: uuid.UUID,
        destino: str,
        usuario: CurrentUser,
        *,
        autorizando: bool = False,
    ) -> FacturaVendedorRead:
        """Misma máquina y misma regla de autorización que `FacturaAfiliado`/
        `FacturaAgencia`: autorizar es de Dirección/Admin, no de quien captura."""
        obj = self._get_or_404(factura_vendedor_id)
        if destino not in {e.value for e in EstatusFacturaProveedor}:
            raise DomainError(f"Estatus desconocido: '{destino}'.")
        if obj.estatus_factura_vendedor == destino:
            return self._enriquecida(self._to_read(obj))  # idempotente
        if destino not in TRANSICIONES_PROVEEDOR.get(obj.estatus_factura_vendedor, set()):
            raise StateTransitionError(
                f"No se puede pasar de '{obj.estatus_factura_vendedor}' a '{destino}'.",
                detalles={"estatus": obj.estatus_factura_vendedor, "destino": destino},
            )
        if destino == EstatusFacturaProveedor.AUTORIZADA.value and not autorizando:
            raise PermissionDeniedError(
                "Autorizar va por el canal dedicado POST /{id}/autorizar "
                "(solo Direccion/Admin), no por el cambio de estatus operativo."
            )
        obj.estatus_factura_vendedor = destino
        self._repo.db.commit()
        self._repo.db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def _validar_cobradas_antes_de_autorizar(self, factura_vendedor_id: uuid.UUID) -> None:
        """ADR-264 (petición del usuario, con captura): no se autoriza el pago al
        vendedor hasta que el CLIENTE ya pagó esa orden — protege el flujo de caja (OIR
        no desembolsa antes de haber cobrado). Sin órdenes asignadas, no hay nada que
        validar (pasa libre, igual que `FacturaAfiliado`/`FacturaAgencia`)."""
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente

        db = self._repo.db
        filas = db.execute(
            select(OrdenCliente.folio_orden, OrdenCliente.estatus_orden)
            .join(FacturaVendedorOrden, FacturaVendedorOrden.orden_id == OrdenCliente.orden_id)
            .where(FacturaVendedorOrden.factura_vendedor_id == factura_vendedor_id)
        ).all()
        pendientes = sorted(
            {f.folio_orden for f in filas if f.estatus_orden != EstatusOrden.COBRADA.value}
        )
        if pendientes:
            raise DomainError(
                "No se puede autorizar el pago: la(s) orden(es) de servicio "
                f"{', '.join(pendientes)} todavía no ha(n) sido cobrada(s) al cliente.",
                detalles={"ordenes_pendientes_de_cobro": pendientes},
            )

    def autorizar(
        self, factura_vendedor_id: uuid.UUID, usuario: CurrentUser
    ) -> FacturaVendedorRead:
        """Canal dedicado `en_revision -> autorizada`. Solo Direccion/Admin — mismo
        diseño y motivo que en `FacturaAfiliado`/`FacturaAgencia`."""
        if usuario.area not in (Area.DIRECCION, Area.ADMIN):
            raise PermissionDeniedError(
                f"El area '{usuario.area.value}' no puede autorizar facturas de vendedor "
                "- solo Direccion."
            )
        self._validar_cobradas_antes_de_autorizar(factura_vendedor_id)
        return self.transicionar(
            factura_vendedor_id,
            EstatusFacturaProveedor.AUTORIZADA.value,
            usuario,
            autorizando=True,
        )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_vendedor_service(db: Session = Depends(get_db)) -> FacturaVendedorService:
    return FacturaVendedorService(
        FacturaVendedorRepository(
            db,
            FacturaVendedor,
            default_order_by=[
                FacturaVendedor.created_at.desc(),
                FacturaVendedor.factura_vendedor_id,
            ],
        )
    )


router_vendedores = APIRouter(prefix="/vendedores", tags=["facturacion:vendedores"])


@router_vendedores.get("", response_model=Page[FacturaVendedorRead])
def listar_facturas_vendedor(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en el folio externo del vendedor"),
    vendedor_id: uuid.UUID | None = Query(None),
    estatus_factura_vendedor: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> Page[FacturaVendedorRead]:
    return svc.list(
        FacturaVendedorListParams(
            page=page,
            size=size,
            q=q,
            vendedor_id=vendedor_id,
            estatus_factura_vendedor=estatus_factura_vendedor,
        )
    )


@router_vendedores.get(
    "/ordenes-facturables", response_model=list[OrdenClienteFacturableVendedorRead]
)
def listar_ordenes_facturables_vendedor(
    vendedor_id: uuid.UUID = Query(...),
    excluir_de_factura_id: uuid.UUID | None = Query(
        None, description="Al editar: no excluye las órdenes de esta misma factura."
    ),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> list[OrdenClienteFacturableVendedorRead]:
    """Combo "Buscar y agregar" del alta/edición: OC cerrada/facturada/cobrada donde ese
    vendedor es el `vendedor_principal_id`, sin las que ya tienen factura registrada en
    OTRA (ADR-264). Declarado ANTES de `/{item_id}`."""
    return svc.ordenes_facturables(vendedor_id, excluir_de_factura_id)


@router_vendedores.get("/{item_id}", response_model=FacturaVendedorRead)
def obtener_factura_vendedor(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    return svc.get(item_id)


@router_vendedores.get("/{item_id}/ordenes", response_model=list[FacturaVendedorOrdenRead])
def listar_ordenes_factura_vendedor(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> list[FacturaVendedorOrdenRead]:
    """Órdenes acumuladas en esta factura (detalle + precargado al editar)."""
    return svc.ordenes(item_id)


# ── Escritura + transiciones (Tanda 2) ────────────────────────────────────────
@router_vendedores.post("", response_model=FacturaVendedorRead, status_code=201)
def crear_factura_vendedor(
    payload: FacturaVendedorCreate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:crear")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    """El subtotal/IVA/total/comisión se calculan como la suma de
    `OrdenCliente.total * porcentaje / 100` de cada orden elegida, cada una con su
    propio `%` (el de la orden, o si no el default del catálogo Vendedor)."""
    return svc.create(payload, usuario)


@router_vendedores.put("/{item_id}", response_model=FacturaVendedorRead)
def actualizar_factura_vendedor(
    item_id: uuid.UUID,
    payload: FacturaVendedorUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    return svc.update(item_id, payload, usuario)


@router_vendedores.post("/{item_id}/estatus", response_model=FacturaVendedorRead)
def cambiar_estatus_factura_vendedor(
    item_id: uuid.UUID,
    payload: TransicionProveedorIn,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    """**`autorizada` exige área Dirección o Admin** — 403 si lo intenta CxP."""
    return svc.transicionar(item_id, payload.estatus, usuario)


@router_vendedores.post("/{item_id}/autorizar", response_model=FacturaVendedorRead)
def autorizar_factura_vendedor(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    """Canal dedicado `en_revision → autorizada`, solo Dirección/Admin — mismo criterio
    que en facturas de afiliado/agencia."""
    return svc.autorizar(item_id, usuario)
