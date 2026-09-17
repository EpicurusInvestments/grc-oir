"""FacturaVendedor (F2) — factura que OIR RECIBE del vendedor por su comisión.

Entidad NUEVA, fuera de la especificación BD v2 (33 entidades): el usuario la pidió
como paridad exacta de `FacturaAgencia` — así como OIR necesita procesar la comisión de
la agencia, también necesita procesar la del vendedor PRINCIPAL de la orden (no el
secundario — confirmado con el usuario; ver ADR de esta sesión). Por ser nueva, no
carga campos legado (`archivo_nombre`/`archivo_path` genéricos que sí tienen
`FacturaAfiliado`/`FacturaAgencia` por ser literales de la spec): va directo a
`archivo_pdf_path`/`archivo_xml_path`, sin nada que "migrar después".

Mismo criterio que `FacturaAgencia` en todo lo demás: es un COSTO, lo captura **CxP**
(permiso `costos:*`), la relación con `OrdenCliente` es **1:N** (una OC puede tener
varias facturas de vendedor — parcialidades, confirmado con el usuario), y comparte la
MISMA máquina de 4 estados (`EstatusFacturaProveedor`, importado de
`factura_afiliado.py`).

`comision_vendedor = OrdenCliente.total * porcentaje_comision_vendedor / 100`. El
porcentaje se SUGIERE desde `Vendedor.porcentaje_comision_default` (el catálogo, no el
snapshot de la OC — mismo criterio que `FacturaAgencia` usa el default de `Agencia`, no
`OrdenCliente.porcentaje_comision_agencia_snap`) pero es editable por operación y se
persiste en la factura.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, Uuid, select
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
            "porcentaje_comision_vendedor >= 0 AND porcentaje_comision_vendedor <= 100",
            name="ck_factura_vendedor_pct_comision",
        ),
        # Invariante de suma exacta con `ROUND(x, 2)` en ambos lados (ADR-039, mismo
        # criterio que `FacturaAgencia`/`FacturaAfiliado`): el IVA es CAPTURADO, no se
        # le impone la tasa del 16%.
        CheckConstraint(
            "ROUND(total_factura_vendedor, 2) = "
            "ROUND(monto_factura_vendedor + iva_factura_vendedor, 2)",
            name="ck_factura_vendedor_total_suma",
        ),
    )

    factura_vendedor_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    vendedor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "vendedor.vendedor_id", name="fk_factura_vendedor_vendedor", ondelete="NO ACTION"
        )
    )
    # 1:N (a diferencia de FacturaCliente): SIN UniqueConstraint sobre orden_id.
    orden_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("orden_cliente.orden_id", name="fk_factura_vendedor_orden", ondelete="NO ACTION")
    )
    folio_factura_vendedor: Mapped[str | None] = mapped_column(Unicode(50), default=None)
    fecha_factura_vendedor: Mapped[date] = mapped_column(fecha_sql())

    monto_factura_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Calculado en el servicio: monto + iva.
    total_factura_vendedor: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    # Sugerido desde el catálogo Vendedor, editable por operación.
    porcentaje_comision_vendedor: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), default=None
    )
    # Calculado en el servicio: OrdenCliente.total * porcentaje / 100.
    comision_vendedor: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)

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


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaVendedorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_vendedor_id: uuid.UUID
    vendedor_id: uuid.UUID
    orden_id: uuid.UUID
    folio_factura_vendedor: str | None = None
    fecha_factura_vendedor: date
    monto_factura_vendedor: Decimal
    iva_factura_vendedor: Decimal
    total_factura_vendedor: Decimal
    porcentaje_comision_vendedor: Decimal | None = None
    comision_vendedor: Decimal | None = None
    archivo_pdf_path: str | None = None
    archivo_xml_path: str | None = None
    estatus_factura_vendedor: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None
    # Se resuelven en el servicio, en lote (mismo criterio que `FacturaAgenciaRead`):
    # sin esto, la lista y el detalle solo podían mostrar los UUID crudos.
    vendedor: str | None = None
    folio_orden: str | None = None
    numero_orden_cliente: str | None = None
    anunciante: str | None = None
    producto: str | None = None
    orden_total: Decimal | None = None


class OrdenClienteFacturableVendedorRead(BaseModel):
    """Fila del combo "Orden relacionada" (alta/edición de FacturaVendedor): una OC
    `orden_cerrada` donde el vendedor elegido es el `vendedor_principal_id`, con su
    `total` (para calcular en vivo la comisión) y el `%` default de ese vendedor
    (sugerido, editable)."""

    model_config = ConfigDict(from_attributes=True)

    orden_id: uuid.UUID
    folio_orden: str
    numero_orden_cliente: str
    anunciante: str | None = None
    producto: str | None = None
    total: Decimal
    porcentaje_comision_vendedor_default: Decimal | None = None


class FacturaVendedorListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    vendedor_id: uuid.UUID | None = None
    orden_id: uuid.UUID | None = None
    estatus_factura_vendedor: str | None = None


# ── Schemas de escritura (Tanda 2) ───────────────────────────────────────────────
class FacturaVendedorCreate(BaseModel):
    """Captura de CxP. `total_factura_vendedor` y `comision_vendedor` se calculan; el
    `porcentaje_comision_vendedor` se SUGIERE desde el catálogo Vendedor si no viene."""

    model_config = ConfigDict(extra="forbid")

    vendedor_id: uuid.UUID
    orden_id: uuid.UUID
    folio_factura_vendedor: str | None = Field(default=None, max_length=50)
    fecha_factura_vendedor: date
    monto_factura_vendedor: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    # IVA capturado, igual que en FacturaAgencia/FacturaAfiliado (spec: "Manual").
    iva_factura_vendedor: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    # Si viene NULL, se toma el default del catálogo Vendedor (editable por operación).
    porcentaje_comision_vendedor: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    archivo_pdf_path: str | None = Field(default=None, max_length=500)
    archivo_xml_path: str | None = Field(default=None, max_length=500)


class FacturaVendedorUpdate(BaseModel):
    """Edición: hace todo lo que hace el alta (mismo criterio que `FacturaAgencia`) —
    puede reasignar el vendedor y la orden relacionada. Cambiar `orden_id` o
    `porcentaje_comision_vendedor` recalcula `comision_vendedor` contra el total de la
    orden (nueva o la que ya tenía)."""

    model_config = ConfigDict(extra="forbid")

    vendedor_id: uuid.UUID | None = None
    orden_id: uuid.UUID | None = None
    folio_factura_vendedor: str | None = Field(default=None, max_length=50)
    fecha_factura_vendedor: date | None = None
    monto_factura_vendedor: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    iva_factura_vendedor: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    porcentaje_comision_vendedor: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    archivo_pdf_path: str | None = Field(default=None, max_length=500)
    archivo_xml_path: str | None = Field(default=None, max_length=500)


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaVendedorRepository(BaseRepository[FacturaVendedor]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        for campo in ("vendedor_id", "orden_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(FacturaVendedor, campo) == valor)
        estatus = getattr(params, "estatus_factura_vendedor", None)
        if estatus is not None:
            stmt = stmt.where(FacturaVendedor.estatus_factura_vendedor == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(FacturaVendedor.folio_factura_vendedor.ilike(patron))
        return stmt


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaVendedorService(
    BaseService[FacturaVendedor, FacturaVendedorCreate, FacturaVendedorUpdate, FacturaVendedorRead]
):
    """Captura de CxP, cálculo de la comisión sobre el total de la OC, y la misma
    máquina de estados que `FacturaAfiliado`/`FacturaAgencia` (autorizar exige
    Dirección/Admin)."""

    read_schema = FacturaVendedorRead
    entidad = "FacturaVendedor"

    def __init__(self, repo: FacturaVendedorRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def _calcular_comision(
        self, total_orden: Decimal, porcentaje: Decimal | None
    ) -> Decimal | None:
        """`comision_vendedor = OrdenCliente.total * porcentaje / 100` — mismo criterio
        que `FacturaAgenciaService._calcular_comision`: sobre el total (con IVA), no el
        subtotal. Sin porcentaje no hay comisión que calcular."""
        if porcentaje is None:
            return None
        return (Decimal(total_orden) * Decimal(porcentaje) / Decimal(100)).quantize(CENTAVOS)

    # ── Enriquecido de lectura ────────────────────────────────────────────────
    def _datos_vendedor(self, facturas: list[FacturaVendedorRead]) -> dict[uuid.UUID, str]:
        """Nombres de los vendedores de una página, en UNA consulta — mismo patrón por
        lote que `_datos_agencia` en `factura_agencia.py`."""
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

    def _datos_orden(
        self, facturas: list[FacturaVendedorRead]
    ) -> dict[uuid.UUID, tuple[str, str, str | None, str | None, Decimal]]:
        """Folio/número/anunciante/producto/total de las OC de una página, en UNA
        consulta — mismo criterio que `factura_agencia.py` (relación 1:N, `IN` sobre el
        conjunto de `orden_id` distintos, no un `JOIN` 1:1)."""
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.ordenes.orden_cliente import OrdenCliente

        ids = {f.orden_id for f in facturas}
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

    def _enriquecida(self, leida: FacturaVendedorRead) -> FacturaVendedorRead:
        """Enriquece UNA lectura (alta/edición/transiciones) con vendedor/orden — mismo
        criterio que `_enriquecida` en `factura_agencia.py`: sin esto, la respuesta de
        un alta/edición mostraría esos campos en `None` hasta el próximo GET."""
        leida.vendedor = self._datos_vendedor([leida]).get(leida.vendedor_id)
        datos_oc = self._datos_orden([leida]).get(leida.orden_id)
        if datos_oc:
            (
                leida.folio_orden,
                leida.numero_orden_cliente,
                leida.anunciante,
                leida.producto,
                leida.orden_total,
            ) = datos_oc
        return leida

    def list(self, params: ListParams) -> Page[FacturaVendedorRead]:
        pagina = super().list(params)
        vendedores = self._datos_vendedor(pagina.items)
        ordenes = self._datos_orden(pagina.items)
        for f in pagina.items:
            f.vendedor = vendedores.get(f.vendedor_id)
            datos_oc = ordenes.get(f.orden_id)
            if datos_oc:
                f.folio_orden, f.numero_orden_cliente, f.anunciante, f.producto, f.orden_total = (
                    datos_oc
                )
        return pagina

    def get(self, id_: Any) -> FacturaVendedorRead:
        return self._enriquecida(super().get(id_))

    def ordenes_facturables(
        self, vendedor_id: uuid.UUID
    ) -> list[OrdenClienteFacturableVendedorRead]:
        """OC `orden_cerrada` donde el vendedor elegido es el `vendedor_principal_id`
        — combo "Orden relacionada" del alta/edición (NO se factura la comisión del
        vendedor secundario, confirmado con el usuario). No excluye OC que ya tengan
        otra factura de vendedor: la relación es 1:N a propósito."""
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import EstatusOrden, OrdenCliente

        db = self._repo.db
        vendedor = db.get(Vendedor, vendedor_id)
        porcentaje_default = vendedor.porcentaje_comision_default if vendedor else None
        filas = db.execute(
            select(
                OrdenCliente.orden_id,
                OrdenCliente.folio_orden,
                OrdenCliente.numero_orden_cliente,
                Anunciante.nombre_comercial,
                OrdenCliente.producto,
                OrdenCliente.total,
            )
            .join(Anunciante, Anunciante.anunciante_id == OrdenCliente.anunciante_id)
            .where(
                OrdenCliente.vendedor_principal_id == vendedor_id,
                OrdenCliente.estatus_orden == EstatusOrden.ORDEN_CERRADA.value,
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
                porcentaje_comision_vendedor_default=porcentaje_default,
            )
            for f in filas
        ]

    def create(self, data: FacturaVendedorCreate, usuario: CurrentUser) -> FacturaVendedorRead:
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import OrdenCliente
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        vendedor = db.get(Vendedor, data.vendedor_id)
        if vendedor is None:
            raise DomainError(
                "El vendedor indicado no existe.", detalles={"vendedor_id": str(data.vendedor_id)}
            )
        oc = db.get(OrdenCliente, data.orden_id)
        if oc is None:
            raise DomainError(
                "La OrdenCliente indicada no existe.", detalles={"orden_id": str(data.orden_id)}
            )
        # Igual que FacturaAgencia: aquí NO se exige `orden_cerrada` para la ORDEN al
        # crear (el combo sí filtra por cerrada, pero el servicio no lo re-valida, mismo
        # criterio ya aceptado para agencia).

        # El porcentaje se sugiere del catálogo si no viene capturado, y se PERSISTE:
        # si el catálogo cambia después, esta factura conserva el pactado.
        porcentaje = data.porcentaje_comision_vendedor
        if porcentaje is None:
            porcentaje = vendedor.porcentaje_comision_default

        monto = Decimal(data.monto_factura_vendedor).quantize(CENTAVOS)
        iva = Decimal(data.iva_factura_vendedor).quantize(CENTAVOS)
        obj = FacturaVendedor(
            factura_vendedor_id=uuid4(),
            **data.model_dump(
                exclude={
                    "monto_factura_vendedor",
                    "iva_factura_vendedor",
                    "porcentaje_comision_vendedor",
                }
            ),
            monto_factura_vendedor=monto,
            iva_factura_vendedor=iva,
            total_factura_vendedor=(monto + iva).quantize(CENTAVOS),
            porcentaje_comision_vendedor=porcentaje,
            comision_vendedor=self._calcular_comision(oc.total, porcentaje),
            estatus_factura_vendedor=EstatusFacturaProveedor.RECIBIDA.value,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    def update(
        self, id_: Any, data: FacturaVendedorUpdate, usuario: CurrentUser
    ) -> FacturaVendedorRead:
        """Edición solo antes de autorizar (mismo candado que `FacturaAgencia`). Hace
        todo lo que hace el alta: puede reasignar vendedor/orden — ambas se validan
        ANTES de tocar la factura, para no dejarla a medio actualizar si alguna no
        existe."""
        from app.modules.catalogos.vendedor import Vendedor
        from app.modules.ordenes.orden_cliente import OrdenCliente

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

        if "vendedor_id" in payload and self._repo.db.get(Vendedor, payload["vendedor_id"]) is None:
            raise DomainError(
                "El vendedor indicado no existe.",
                detalles={"vendedor_id": str(payload["vendedor_id"])},
            )
        oc_nueva = None
        if "orden_id" in payload:
            oc_nueva = self._repo.db.get(OrdenCliente, payload["orden_id"])
            if oc_nueva is None:
                raise DomainError(
                    "La OrdenCliente indicada no existe.",
                    detalles={"orden_id": str(payload["orden_id"])},
                )

        obj = self._repo.update(obj, payload)
        recalculos: dict[str, Any] = {}
        if "monto_factura_vendedor" in payload or "iva_factura_vendedor" in payload:
            recalculos["total_factura_vendedor"] = (
                Decimal(obj.monto_factura_vendedor) + Decimal(obj.iva_factura_vendedor)
            ).quantize(CENTAVOS)
        if "porcentaje_comision_vendedor" in payload or "orden_id" in payload:
            # Si cambió la orden, usa la NUEVA (ya validada arriba); si no, la que ya
            # tenía la factura.
            oc = oc_nueva if oc_nueva is not None else self._repo.db.get(OrdenCliente, obj.orden_id)
            if oc is not None:
                recalculos["comision_vendedor"] = self._calcular_comision(
                    oc.total, obj.porcentaje_comision_vendedor
                )
        if recalculos:
            obj = self._repo.update(obj, recalculos)
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
        return self.transicionar(
            factura_vendedor_id,
            EstatusFacturaProveedor.AUTORIZADA.value,
            usuario,
            autorizando=True,
        )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_vendedor_service(db: Session = Depends(get_db)) -> FacturaVendedorService:
    # Más reciente primero (mismo criterio que FacturaAfiliado/FacturaAgencia): se
    # ordena por `created_at`, el momento real del alta.
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
    orden_id: uuid.UUID | None = Query(None),
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
            orden_id=orden_id,
            estatus_factura_vendedor=estatus_factura_vendedor,
        )
    )


@router_vendedores.get(
    "/ordenes-facturables", response_model=list[OrdenClienteFacturableVendedorRead]
)
def listar_ordenes_facturables_vendedor(
    vendedor_id: uuid.UUID = Query(...),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> list[OrdenClienteFacturableVendedorRead]:
    """Combo "Orden relacionada" del alta/edición: OC `orden_cerrada` donde ese
    vendedor es el `vendedor_principal_id`. Declarado ANTES de `/{item_id}` — si no,
    FastAPI intentaría parsear "ordenes-facturables" como UUID de `item_id` y
    respondería 422."""
    return svc.ordenes_facturables(vendedor_id)


@router_vendedores.get("/{item_id}", response_model=FacturaVendedorRead)
def obtener_factura_vendedor(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    return svc.get(item_id)


# ── Escritura + transiciones (Tanda 2) ────────────────────────────────────────
@router_vendedores.post("", response_model=FacturaVendedorRead, status_code=201)
def crear_factura_vendedor(
    payload: FacturaVendedorCreate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:crear")),
    svc: FacturaVendedorService = Depends(get_factura_vendedor_service),
) -> FacturaVendedorRead:
    """`comision_vendedor` se calcula como `OrdenCliente.total * porcentaje / 100`; si
    no se captura el porcentaje, se toma el default del catálogo Vendedor."""
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
