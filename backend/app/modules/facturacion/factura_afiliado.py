"""FacturaAfiliado + FacturaAfiliadoOrden (F2) — factura que OIR RECIBE del afiliado.

Es un COSTO, no un ingreso: la emisora factura a OIR por los servicios de transmisión.
La captura es de **CxP** (no de Facturación — ver la matriz de la ficha), por eso su
permiso es `costos:*` y no `facturacion:*`.

`FacturaAfiliadoOrden` es la tabla N:M que reparte el costo de UNA factura entre varias
`OrdenEstacion` **cerradas**. Vive en este archivo, junto a su padre, con el mismo
criterio que `OrdenEstacionDia` vive dentro de `orden_estacion.py` en F1.

La validación de que la OE esté `cerrada` es una regla de NEGOCIO: se implementa en el
servicio (Tanda 2), no en el esquema — un CHECK no puede leer otra tabla, y una FK no
puede condicionarse a un estado.

`updated_at` es ADITIVO: la spec solo pide `created_at` para esta entidad, pero el
CLAUDE.md §6 lo exige en toda entidad y F1 ya sentó el precedente (se agregó a las tres
entidades de F1 que la spec tampoco lo pedía). Decisión confirmada para F2.
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
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    Unicode,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.errors import ConflictError, DomainError, PermissionDeniedError, StateTransitionError
from app.core.security import Area, CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page


class EstatusFacturaProveedor(StrEnum):
    """Estados de las facturas que OIR RECIBE (spec: mismos 4 valores para afiliado y
    agencia). Se define UNA vez aquí y `factura_agencia.py` lo importa — mismo criterio
    que `EstatusOrden`, definido en `orden_cliente.py` y reutilizado por
    `orden_estacion.py` en F1.

    `en_revision → autorizada` NO lo ejecuta quien capturó: es de Dirección/Admin
    (regla de área explícita en el servicio, Tanda 2 — mismo patrón que el canal de
    comisiones de F1, que tampoco se resuelve con la matriz RBAC de módulo).
    """

    RECIBIDA = "recibida"
    EN_REVISION = "en_revision"
    AUTORIZADA = "autorizada"
    PAGADA = "pagada"


_ESTATUS_PROVEEDOR_SQL = ", ".join(f"'{e.value}'" for e in EstatusFacturaProveedor)

#: Dinero cuantizado a centavos, igual que F1 y `factura_cliente.py`.
CENTAVOS = Decimal("0.01")


# ── Modelo ──────────────────────────────────────────────────────────────────────
class FacturaAfiliado(Base):
    __tablename__ = "factura_afiliado"
    __table_args__ = (
        CheckConstraint(
            f"estatus_factura_afiliado IN ({_ESTATUS_PROVEEDOR_SQL})",
            name="ck_factura_afiliado_estatus",
        ),
        CheckConstraint("monto_factura_afiliado >= 0", name="ck_factura_afiliado_monto"),
        CheckConstraint("iva_factura_afiliado >= 0", name="ck_factura_afiliado_iva"),
        CheckConstraint("total_factura_afiliado >= 0", name="ck_factura_afiliado_total"),
        # Invariante de suma exacta con `ROUND(x, 2)` en ambos lados (ADR-039): ver la
        # explicación completa en `factura_cliente.py`. Aquí el IVA es CAPTURADO (la
        # spec lo marca "Manual": la factura del afiliado puede traer un IVA que no sea
        # exactamente el 16% — retenciones, exentos), así que NO se agrega un CHECK
        # `iva = monto * 0.16` como sí lo lleva FacturaCliente.
        CheckConstraint(
            "ROUND(total_factura_afiliado, 2) = "
            "ROUND(monto_factura_afiliado + iva_factura_afiliado, 2)",
            name="ck_factura_afiliado_total_suma",
        ),
    )

    factura_afiliado_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    afiliado_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "afiliado.afiliado_id", name="fk_factura_afiliado_afiliado", ondelete="NO ACTION"
        )
    )
    # Heredado del catálogo Afiliado al capturar (spec: origen "Derivado").
    razon_social_afiliada: Mapped[str | None] = mapped_column(Unicode(200), default=None)
    factura_emisora: Mapped[str] = mapped_column(Unicode(50))
    fecha_factura_afiliado: Mapped[date] = mapped_column(fecha_sql())

    monto_factura_afiliado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    iva_factura_afiliado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Calculado en el servicio: monto + iva.
    total_factura_afiliado: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    # CLAVE del almacenamiento (S3/local), no una ruta de disco (ADR-042).
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    estatus_factura_afiliado: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusFacturaProveedor.RECIBIDA.value
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "usuario.usuario_id", name="fk_factura_afiliado_created_by", ondelete="NO ACTION"
        )
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # ADITIVO (la spec no lo pide) — ver docstring del módulo.
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class FacturaAfiliadoOrden(Base):
    """Reparto del costo de una factura de afiliado entre varias OrdenEstacion cerradas."""

    __tablename__ = "factura_afiliado_orden"
    __table_args__ = (
        # Una OE no puede asignarse dos veces a la MISMA factura (el reparto sería
        # ambiguo). Sí puede aparecer en facturas distintas: la spec no lo prohíbe y el
        # negocio lo permite (una emisora puede facturar en parcialidades).
        UniqueConstraint(
            "factura_afiliado_id",
            "orden_estacion_id",
            name="uq_factura_afiliado_orden_factura_oe",
        ),
        CheckConstraint("monto_asignado >= 0", name="ck_factura_afiliado_orden_monto"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    factura_afiliado_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_afiliado.factura_afiliado_id",
            name="fk_factura_afiliado_orden_factura",
            ondelete="NO ACTION",
        )
    )
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_factura_afiliado_orden_oe",
            ondelete="NO ACTION",
        )
    )
    monto_asignado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    notas_asignacion: Mapped[str | None] = mapped_column(texto_largo(), default=None)


# ── Schemas de lectura (Tanda 1) ─────────────────────────────────────────────────
class FacturaAfiliadoOrdenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    factura_afiliado_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    monto_asignado: Decimal
    notas_asignacion: str | None = None


class FacturaAfiliadoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    factura_afiliado_id: uuid.UUID
    afiliado_id: uuid.UUID
    razon_social_afiliada: str | None = None
    factura_emisora: str
    fecha_factura_afiliado: date
    monto_factura_afiliado: Decimal
    iva_factura_afiliado: Decimal
    total_factura_afiliado: Decimal
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    estatus_factura_afiliado: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class FacturaAfiliadoListParams(ListParams):
    """Hereda `activo` sin exponerlo: esta entidad no tiene baja lógica (ADR-035)."""

    afiliado_id: uuid.UUID | None = None
    estatus_factura_afiliado: str | None = None


# ── Schemas de escritura (Tanda 2) ───────────────────────────────────────────────
# Transiciones permitidas. `autorizada` exige área Dirección/Admin (ver el servicio).
TRANSICIONES_PROVEEDOR: dict[str, set[str]] = {
    EstatusFacturaProveedor.RECIBIDA.value: {EstatusFacturaProveedor.EN_REVISION.value},
    EstatusFacturaProveedor.EN_REVISION.value: {
        EstatusFacturaProveedor.AUTORIZADA.value,
        # Vuelta atrás deliberada: si la revisión encuentra un error, la factura regresa
        # a `recibida` para que CxP la corrija. La spec dibuja el flujo lineal pero no
        # prohíbe el rechazo, y sin esta arista una factura mal capturada quedaría
        # atorada para siempre.
        EstatusFacturaProveedor.RECIBIDA.value,
    },
    EstatusFacturaProveedor.AUTORIZADA.value: {EstatusFacturaProveedor.PAGADA.value},
    EstatusFacturaProveedor.PAGADA.value: set(),  # terminal
}


class FacturaAfiliadoCreate(BaseModel):
    """Captura de CxP. `razon_social_afiliada` y `total_factura_afiliado` NO se aceptan:
    la primera se hereda del catálogo Afiliado y la segunda se calcula."""

    model_config = ConfigDict(extra="forbid")

    afiliado_id: uuid.UUID
    factura_emisora: str = Field(min_length=1, max_length=50)
    fecha_factura_afiliado: date
    monto_factura_afiliado: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    # IVA CAPTURADO, no derivado: la factura del afiliado puede traer retenciones o
    # conceptos exentos (spec lo marca "Manual"), así que no se le impone el 16%.
    iva_factura_afiliado: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    archivo_nombre: str | None = Field(default=None, max_length=255)
    archivo_path: str | None = Field(default=None, max_length=500)


class FacturaAfiliadoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factura_emisora: str | None = Field(default=None, min_length=1, max_length=50)
    fecha_factura_afiliado: date | None = None
    monto_factura_afiliado: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    iva_factura_afiliado: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    archivo_nombre: str | None = Field(default=None, max_length=255)
    archivo_path: str | None = Field(default=None, max_length=500)


class AsignarOrdenIn(BaseModel):
    """Asignación de una porción del costo a una OrdenEstacion CERRADA."""

    model_config = ConfigDict(extra="forbid")

    orden_estacion_id: uuid.UUID
    monto_asignado: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    notas_asignacion: str | None = None


class TransicionProveedorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estatus: str


# ── Repositorio ───────────────────────────────────────────────────────────────
class FacturaAfiliadoRepository(BaseRepository[FacturaAfiliado]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: la base filtra por `model.activo`.
        afiliado_id = getattr(params, "afiliado_id", None)
        if afiliado_id is not None:
            stmt = stmt.where(FacturaAfiliado.afiliado_id == afiliado_id)
        estatus = getattr(params, "estatus_factura_afiliado", None)
        if estatus is not None:
            stmt = stmt.where(FacturaAfiliado.estatus_factura_afiliado == estatus)
        if params.q:
            patron = f"%{params.q.strip()}%"
            stmt = stmt.where(
                FacturaAfiliado.factura_emisora.ilike(patron)
                | FacturaAfiliado.razon_social_afiliada.ilike(patron)
            )
        return stmt

    def listar_asignaciones(self, factura_afiliado_id: uuid.UUID) -> list[FacturaAfiliadoOrden]:
        return list(
            self.db.scalars(
                select(FacturaAfiliadoOrden)
                .where(FacturaAfiliadoOrden.factura_afiliado_id == factura_afiliado_id)
                .order_by(FacturaAfiliadoOrden.id)
            ).all()
        )


# ── Servicio ──────────────────────────────────────────────────────────────────
class FacturaAfiliadoService(
    BaseService[FacturaAfiliado, FacturaAfiliadoCreate, FacturaAfiliadoUpdate, FacturaAfiliadoRead]
):
    """Captura de CxP, máquina de estados con autorización de Dirección/Admin, y reparto
    del costo entre OrdenEstacion cerradas."""

    read_schema = FacturaAfiliadoRead
    entidad = "FacturaAfiliado"

    def __init__(self, repo: FacturaAfiliadoRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    def asignaciones(self, factura_afiliado_id: uuid.UUID) -> list[FacturaAfiliadoOrdenRead]:
        self._get_or_404(factura_afiliado_id)
        return [
            FacturaAfiliadoOrdenRead.model_validate(a)
            for a in self._repo.listar_asignaciones(factura_afiliado_id)
        ]

    # ── Captura ───────────────────────────────────────────────────────────────
    def create(self, data: FacturaAfiliadoCreate, usuario: CurrentUser) -> FacturaAfiliadoRead:
        from app.modules.catalogos.afiliado import Afiliado
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        afiliado = db.get(Afiliado, data.afiliado_id)
        if afiliado is None:
            raise DomainError(
                "El afiliado indicado no existe.", detalles={"afiliado_id": str(data.afiliado_id)}
            )
        monto = Decimal(data.monto_factura_afiliado).quantize(CENTAVOS)
        iva = Decimal(data.iva_factura_afiliado).quantize(CENTAVOS)
        obj = FacturaAfiliado(
            factura_afiliado_id=uuid4(),
            **data.model_dump(exclude={"monto_factura_afiliado", "iva_factura_afiliado"}),
            # Heredado del catálogo (spec: origen "Derivado").
            razon_social_afiliada=afiliado.razon_social_afiliado,
            monto_factura_afiliado=monto,
            iva_factura_afiliado=iva,
            total_factura_afiliado=(monto + iva).quantize(CENTAVOS),
            estatus_factura_afiliado=EstatusFacturaProveedor.RECIBIDA.value,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    def update(
        self, id_: Any, data: FacturaAfiliadoUpdate, usuario: CurrentUser
    ) -> FacturaAfiliadoRead:
        """Edición solo antes de autorizar: una vez autorizada, el monto ya sirvió de base
        para la decisión de pago."""
        obj = self._get_or_404(id_)
        if obj.estatus_factura_afiliado not in (
            EstatusFacturaProveedor.RECIBIDA.value,
            EstatusFacturaProveedor.EN_REVISION.value,
        ):
            raise ConflictError(
                "Una factura autorizada o pagada ya no se edita.",
                detalles={"estatus_factura_afiliado": obj.estatus_factura_afiliado},
            )
        payload = data.model_dump(exclude_unset=True)
        obj = self._repo.update(obj, payload)
        # Recalcular el total si cambió alguno de sus sumandos.
        if "monto_factura_afiliado" in payload or "iva_factura_afiliado" in payload:
            total = (
                Decimal(obj.monto_factura_afiliado) + Decimal(obj.iva_factura_afiliado)
            ).quantize(CENTAVOS)
            obj = self._repo.update(obj, {"total_factura_afiliado": total})
        return self._to_read(obj)

    # ── Máquina de estados ────────────────────────────────────────────────────
    def transicionar(
        self,
        factura_afiliado_id: uuid.UUID,
        destino: str,
        usuario: CurrentUser,
        *,
        autorizando: bool = False,
    ) -> FacturaAfiliadoRead:
        """Autorizar exige **Dirección o Admin**, no basta el permiso de módulo.

        Es el mismo patrón que el canal de comisiones de F1: la matriz RBAC da captura a
        CxP sobre TODO el módulo de costos, así que sin este chequeo quien captura podría
        autorizar su propia factura. La regla vive en el servicio porque es una
        autorización por ACCIÓN, no por módulo, y `_nivel()` no puede expresarla.
        """
        obj = self._get_or_404(factura_afiliado_id)
        if destino not in {e.value for e in EstatusFacturaProveedor}:
            raise DomainError(f"Estatus desconocido: '{destino}'.")
        if obj.estatus_factura_afiliado == destino:
            return self._to_read(obj)  # idempotente
        if destino not in TRANSICIONES_PROVEEDOR.get(obj.estatus_factura_afiliado, set()):
            raise StateTransitionError(
                f"No se puede pasar de '{obj.estatus_factura_afiliado}' a '{destino}'.",
                detalles={"estatus": obj.estatus_factura_afiliado, "destino": destino},
            )
        if destino == EstatusFacturaProveedor.AUTORIZADA.value and not autorizando:
            # Se llega aqui por el endpoint operativo (`/estatus`), que exige
            # `costos:editar` — permiso que Direccion NO tiene. Autorizar va por su
            # canal dedicado (`/autorizar`), igual que el canal de comisiones de F1.
            raise PermissionDeniedError(
                "Autorizar va por el canal dedicado POST /{id}/autorizar "
                "(solo Direccion/Admin), no por el cambio de estatus operativo."
            )
        obj.estatus_factura_afiliado = destino
        self._repo.db.commit()
        self._repo.db.refresh(obj)
        return self._to_read(obj)

    def autorizar(
        self, factura_afiliado_id: uuid.UUID, usuario: CurrentUser
    ) -> FacturaAfiliadoRead:
        """CANAL DEDICADO para `en_revision -> autorizada`. Solo Direccion/Admin.

        Mismo diseno que el canal de comisiones de F1 (`PATCH /clientes/{id}/comisiones`):
        el permiso del ROUTER es `costos:leer` a proposito, porque Direccion NO tiene
        `costos:editar` en la matriz (captura es de CxP) — y la autorizacion REAL se
        valida aqui, por area. Sin este canal separado, la matriz de modulo dejaria a
        Direccion fuera de una accion que la ficha le asigna explicitamente.
        """
        if usuario.area not in (Area.DIRECCION, Area.ADMIN):
            raise PermissionDeniedError(
                f"El area '{usuario.area.value}' no puede autorizar facturas de afiliado "
                "- solo Direccion."
            )
        return self.transicionar(
            factura_afiliado_id,
            EstatusFacturaProveedor.AUTORIZADA.value,
            usuario,
            autorizando=True,
        )

    # ── Reparto entre OrdenEstacion cerradas ──────────────────────────────────
    def asignar_orden(
        self, factura_afiliado_id: uuid.UUID, data: AsignarOrdenIn, usuario: CurrentUser
    ) -> FacturaAfiliadoOrdenRead:
        """La OE debe estar **cerrada** (ficha): un costo no se imputa a transmisión que
        todavía no terminó de verificarse. Es una regla de negocio, no de esquema: una FK
        no puede condicionarse al estado de la fila referida."""
        from app.modules.ordenes.orden_estacion import EstatusOrdenEstacion, OrdenEstacion

        obj = self._get_or_404(factura_afiliado_id)
        db = self._repo.db
        oe = db.get(OrdenEstacion, data.orden_estacion_id)
        if oe is None:
            raise DomainError(
                "La OrdenEstacion indicada no existe.",
                detalles={"orden_estacion_id": str(data.orden_estacion_id)},
            )
        if oe.estatus != EstatusOrdenEstacion.CERRADA.value:
            raise DomainError(
                "Solo se puede asignar costo a una OrdenEstacion 'cerrada'.",
                detalles={
                    "orden_estacion_id": str(data.orden_estacion_id),
                    "estatus": oe.estatus,
                },
            )
        duplicada = db.scalar(
            select(FacturaAfiliadoOrden)
            .where(
                FacturaAfiliadoOrden.factura_afiliado_id == factura_afiliado_id,
                FacturaAfiliadoOrden.orden_estacion_id == data.orden_estacion_id,
            )
            .limit(1)
        )
        if duplicada is not None:
            raise ConflictError(
                "Esa OrdenEstacion ya está asignada a esta factura.",
                detalles={"orden_estacion_id": str(data.orden_estacion_id)},
            )
        asignacion = FacturaAfiliadoOrden(
            id=uuid4(),
            factura_afiliado_id=obj.factura_afiliado_id,
            orden_estacion_id=data.orden_estacion_id,
            monto_asignado=Decimal(data.monto_asignado).quantize(CENTAVOS),
            notas_asignacion=data.notas_asignacion,
        )
        db.add(asignacion)
        db.commit()
        db.refresh(asignacion)
        return FacturaAfiliadoOrdenRead.model_validate(asignacion)


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_factura_afiliado_service(db: Session = Depends(get_db)) -> FacturaAfiliadoService:
    return FacturaAfiliadoService(FacturaAfiliadoRepository(db, FacturaAfiliado))


router_afiliados = APIRouter(prefix="/afiliados", tags=["facturacion:afiliados"])


@router_afiliados.get("", response_model=Page[FacturaAfiliadoRead])
def listar_facturas_afiliado(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, description="Busca en folio de la emisora y razón social"),
    afiliado_id: uuid.UUID | None = Query(None),
    estatus_factura_afiliado: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> Page[FacturaAfiliadoRead]:
    return svc.list(
        FacturaAfiliadoListParams(
            page=page,
            size=size,
            q=q,
            afiliado_id=afiliado_id,
            estatus_factura_afiliado=estatus_factura_afiliado,
        )
    )


@router_afiliados.get("/{item_id}", response_model=FacturaAfiliadoRead)
def obtener_factura_afiliado(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoRead:
    return svc.get(item_id)


@router_afiliados.get("/{item_id}/ordenes", response_model=list[FacturaAfiliadoOrdenRead])
def listar_asignaciones_factura_afiliado(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> list[FacturaAfiliadoOrdenRead]:
    """Reparto de esta factura entre las OrdenEstacion a las que se asignó."""
    return svc.asignaciones(item_id)


# ── Escritura + transiciones (Tanda 2) ────────────────────────────────────────
@router_afiliados.post("", response_model=FacturaAfiliadoRead, status_code=201)
def crear_factura_afiliado(
    payload: FacturaAfiliadoCreate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:crear")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoRead:
    return svc.create(payload, usuario)


@router_afiliados.put("/{item_id}", response_model=FacturaAfiliadoRead)
def actualizar_factura_afiliado(
    item_id: uuid.UUID,
    payload: FacturaAfiliadoUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoRead:
    return svc.update(item_id, payload, usuario)


@router_afiliados.post("/{item_id}/estatus", response_model=FacturaAfiliadoRead)
def cambiar_estatus_factura_afiliado(
    item_id: uuid.UUID,
    payload: TransicionProveedorIn,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoRead:
    """`recibida → en_revision → autorizada → pagada` (con vuelta de `en_revision` a
    `recibida` si la revisión rechaza). **`autorizada` exige área Dirección o Admin** —
    403 si lo intenta el propio CxP que capturó."""
    return svc.transicionar(item_id, payload.estatus, usuario)


@router_afiliados.post(
    "/{item_id}/ordenes", response_model=FacturaAfiliadoOrdenRead, status_code=201
)
def asignar_orden_a_factura_afiliado(
    item_id: uuid.UUID,
    payload: AsignarOrdenIn,
    usuario: CurrentUser = Depends(requiere_permiso("costos:editar")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoOrdenRead:
    """Reparte una porción del costo a una OrdenEstacion **cerrada** (400 si no lo está)."""
    return svc.asignar_orden(item_id, payload, usuario)


@router_afiliados.post("/{item_id}/autorizar", response_model=FacturaAfiliadoRead)
def autorizar_factura_afiliado(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("costos:leer")),
    svc: FacturaAfiliadoService = Depends(get_factura_afiliado_service),
) -> FacturaAfiliadoRead:
    """Canal dedicado `en_revision → autorizada`. Permiso de router deliberadamente
    `costos:leer` (Dirección no tiene captura sobre el módulo); la autorización real
    —solo Dirección/Admin— se valida DENTRO del servicio. 403 para cualquier otra área,
    incluida la CxP que capturó la factura."""
    return svc.autorizar(item_id, usuario)
