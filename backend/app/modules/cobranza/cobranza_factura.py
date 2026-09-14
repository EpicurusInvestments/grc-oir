"""CobranzaFactura + PagoCliente (F3) — seguimiento de cobranza de facturas al cliente.

`CobranzaFactura` se crea AUTOMÁTICAMENTE cuando `FacturaCliente.estado_facturacion`
llega a `timbrada` (1:1 con la factura, spec — no cambió con ADR-064: sigue siendo una
`CobranzaFactura` por `FacturaCliente`, sin importar cuántas órdenes cubra la factura).
Nadie la crea a mano: no hay `POST` para esta entidad. El mecanismo es el mismo handoff
"método acotado en el dueño del agregado, invocado en la misma transacción" que ya usan
F1↔F2 (`OrdenClienteService.marcar_facturada`/`revertir_facturacion`) — aquí el dueño del
agregado es F3, y quien lo invoca es `FacturaClienteService` (ver `timbrar`/`entregar`/
`cancelar` en `app/modules/facturacion/factura_cliente.py`).

Tres desviaciones aditivas aprobadas respecto a la spec BD v2:

1. **`metodo_pago_clave` sin FK formal** (idéntico a F2): `MetodoPago` vive dentro de
   `ConstantesSistema` (grupo `MetodoPago`), no como tabla propia.
2. **`importe_cobrado`/`importe_pendiente_cobro`: derivados en CADA lectura, NO columnas
   persistidas.** La spec los marca "Calculado", pero son una suma viva
   (`SUM(PagoCliente.monto_aplicado)`) que puede cambiar en cualquier momento —
   persistirlos arriesgaría que queden desincronizados si algo falla a medio camino.
3. **`estatus_cobro`: el CHECK solo admite 3 valores** (`pendiente`/`cobro_parcial`/
   `cobrada`). `vencida` es un badge DERIVADO en el servicio (`fecha_estimada_cobro` vs
   hoy, y no cobrada) — mismo patrón que `Vigente`/`Expirada` de `TarifaPlaza` (F0-02) —,
   nunca se escribe en la columna. Se recalcula automáticamente al crear o borrar un
   `PagoCliente`: no es una transición manual con endpoint dedicado.

Una cuarta desviación, menor y documentada en el propio código: `fecha_estimada_cobro` se
calcula con `FacturaCliente.fecha_entrega_factura` como ancla (spec), pero esa columna es
NULLABLE y todavía no existe cuando se crea la `CobranzaFactura` (se crea al TIMBRAR, y
`fecha_entrega_factura` se llena después, al ENTREGAR). Se usa `fecha_timbrado` como
ancla PROVISIONAL en la creación, y se recalcula con el ancla real en
`FacturaClienteService.entregar()` — ver `refrescar_fecha_estimada` abajo.

`fecha_cobro` se asigna AUTOMÁTICAMENTE cuando `estatus_cobro` pasa a `cobrada`
(`importe_cobrado >= total_factura`), no por captura manual, aunque la spec la marque
"Manual" — el dato de VERDAD es cuándo se completó el pago, y ese momento ya lo sabe el
propio recálculo; pedirlo de nuevo a mano solo invitaría a que no coincidiera.

## La cascada `CobranzaFactura → FacturaCliente → OrdenCliente`

Cuando `estatus_cobro` llega a `cobrada`, este servicio invoca
`FacturaClienteService.marcar_cobrada`, que a su vez invoca
`OrdenClienteService.marcar_cobrada` para TODAS las órdenes de la factura — misma
transacción, disparada desde `recalcular_tras_pago()`. Es la cascada que F2 dejó anticipada desde
que `EstadoFacturacion.COBRADA` entró al enum con el comentario "F3 hará avanzar".

**La cascada NO tiene reversa.** Si se borra un `PagoCliente` y eso haría que
`estatus_cobro` retrocediera desde `cobrada`, `PagoClienteService.eliminar` lo RECHAZA con
409 (conflicto con el estado actual, no un error de captura) — mismo principio que
ADR-047 (deshacer un cobro real exige una nota de crédito que el sistema no maneja).
Borrar un pago que NUNCA llegó a completar el cobro (la `CobranzaFactura` seguía
`pendiente`/`cobro_parcial`) sí se permite y recalcula con normalidad.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, ForeignKey, Numeric, Unicode, Uuid, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, datetime2, fecha_sql, get_db, texto_largo
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.schemas import ListParams, Page

CENTAVOS = Decimal("0.01")


class EstatusCobro(StrEnum):
    PENDIENTE = "pendiente"
    COBRO_PARCIAL = "cobro_parcial"
    COBRADA = "cobrada"


_ESTADOS_SQL = ", ".join(f"'{e.value}'" for e in EstatusCobro)


# ── Modelos ───────────────────────────────────────────────────────────────────
class CobranzaFactura(Base):
    __tablename__ = "cobranza_factura"
    __table_args__ = (
        CheckConstraint(f"estatus_cobro IN ({_ESTADOS_SQL})", name="ck_cobranza_factura_estatus"),
        CheckConstraint("dias_credito >= 0", name="ck_cobranza_factura_dias_credito"),
    )

    cobranza_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)

    # 1:1 con FacturaCliente — UNIQUE, no cambió con ADR-064 (una factura, aunque cubra
    # varias órdenes, sigue siendo una sola CobranzaFactura).
    factura_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "factura_cliente.factura_id", name="fk_cobranza_factura_factura", ondelete="NO ACTION"
        ),
        unique=True,
    )
    # Derivado de la factura al crear (spec). Se copia, no se lee por JOIN en cada
    # consulta, porque es el filtro más común de la bandeja de CxC.
    anunciante_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("anunciante.anunciante_id", name="fk_cobranza_factura_anunciante"),
    )

    # Desviación aditiva (idéntica a F2): sin FK formal, ver docstring del módulo.
    metodo_pago_clave: Mapped[str] = mapped_column(Unicode(20))
    dias_credito: Mapped[int] = mapped_column()
    fecha_estimada_cobro: Mapped[date] = mapped_column(fecha_sql())
    fecha_cobro: Mapped[date | None] = mapped_column(fecha_sql(), default=None)
    estatus_cobro: Mapped[str] = mapped_column(
        Unicode(20), default=EstatusCobro.PENDIENTE.value
    )
    comentarios_cobranza: Mapped[str | None] = mapped_column(texto_largo(), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "usuario.usuario_id", name="fk_cobranza_factura_created_by", ondelete="NO ACTION"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


class PagoCliente(Base):
    """Pago recibido del cliente, aplicado a UNA `CobranzaFactura`.

    Sin baja lógica (ADR-035, mismo criterio que F1/F2): `DELETE` físico, a propósito —
    ver el docstring del módulo sobre por qué SÍ se permite borrar, a diferencia del resto
    del proyecto, y bajo qué guardarraíl (no se puede si eso revertiría un cobro ya
    completado).
    """

    __tablename__ = "pago_cliente"
    __table_args__ = (CheckConstraint("monto_aplicado > 0", name="ck_pago_cliente_monto"),)

    pago_cliente_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    cobranza_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "cobranza_factura.cobranza_id", name="fk_pago_cliente_cobranza", ondelete="NO ACTION"
        ),
        index=True,
    )
    fecha_pago_cliente: Mapped[date] = mapped_column(fecha_sql())
    monto_aplicado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    metodo_pago_clave: Mapped[str] = mapped_column(Unicode(20))
    referencia_pago: Mapped[str | None] = mapped_column(Unicode(100), default=None)
    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)

    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey(
            "usuario.usuario_id", name="fk_pago_cliente_created_by", ondelete="NO ACTION"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


# ── Schemas de lectura ────────────────────────────────────────────────────────
class CobranzaFacturaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cobranza_id: uuid.UUID
    factura_id: uuid.UUID
    anunciante_id: uuid.UUID
    metodo_pago_clave: str
    dias_credito: int
    fecha_estimada_cobro: date
    fecha_cobro: date | None = None
    estatus_cobro: EstatusCobro
    comentarios_cobranza: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None

    # ── Derivados, NUNCA columnas (ver docstring del módulo) ──
    importe_cobrado: Decimal = Decimal("0")
    importe_pendiente_cobro: Decimal = Decimal("0")
    #: Badge, no estado almacenado: `fecha_estimada_cobro < hoy` y NO cobrada.
    vencida: bool = False
    #: Denormalizado para no obligar una consulta aparte a la lista (mismo criterio que
    #: `empresa_facturadora`/`folio_orden` en F2).
    numero_factura: str | None = None


class CobranzaFacturaListParams(ListParams):
    factura_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID | None = None
    estatus_cobro: str | None = None


class CobranzaFacturaUpdate(BaseModel):
    """Los 3 campos "editable" de la spec. `estatus_cobro`/`fecha_cobro`/los importes NO
    están aquí: son calculados, el cliente nunca los manda."""

    model_config = ConfigDict(extra="forbid")

    metodo_pago_clave: str | None = Field(default=None, min_length=1, max_length=20)
    dias_credito: int | None = Field(default=None, ge=0)
    comentarios_cobranza: str | None = None


class PagoClienteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pago_cliente_id: uuid.UUID
    cobranza_id: uuid.UUID
    fecha_pago_cliente: date
    monto_aplicado: Decimal
    metodo_pago_clave: str
    referencia_pago: str | None = None
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    created_by: uuid.UUID
    created_at: datetime


class PagoClienteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_pago_cliente: date
    monto_aplicado: Decimal = Field(gt=0)
    metodo_pago_clave: str = Field(min_length=1, max_length=20)
    referencia_pago: str | None = Field(default=None, max_length=100)
    archivo_nombre: str | None = None
    archivo_path: str | None = None


# ── Repositorios ──────────────────────────────────────────────────────────────
class CobranzaFacturaRepository(BaseRepository[CobranzaFactura]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: esta entidad no tiene `activo`.
        for campo in ("factura_id", "anunciante_id"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(CobranzaFactura, campo) == valor)
        estatus = getattr(params, "estatus_cobro", None)
        if estatus is not None:
            stmt = stmt.where(CobranzaFactura.estatus_cobro == estatus)
        return stmt


class PagoClienteRepository(BaseRepository[PagoCliente]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        cobranza_id = getattr(params, "cobranza_id", None)
        if cobranza_id is not None:
            stmt = stmt.where(PagoCliente.cobranza_id == cobranza_id)
        return stmt


class PagoClienteListParams(ListParams):
    cobranza_id: uuid.UUID | None = None


# ── Servicio de CobranzaFactura ───────────────────────────────────────────────
class CobranzaFacturaService(
    BaseService[CobranzaFactura, BaseModel, CobranzaFacturaUpdate, CobranzaFacturaRead]
):
    read_schema = CobranzaFacturaRead
    entidad = "CobranzaFactura"

    def __init__(self, repo: CobranzaFacturaRepository) -> None:
        super().__init__(repo)
        self._repo = repo

    # ── lectura enriquecida (importes derivados + badge `vencida` + denormalizado) ──
    def importe_cobrado(self, cobranza_id: uuid.UUID) -> Decimal:
        total = self._repo.db.scalar(
            select(func.coalesce(func.sum(PagoCliente.monto_aplicado), 0)).where(
                PagoCliente.cobranza_id == cobranza_id
            )
        )
        return Decimal(total or 0).quantize(CENTAVOS)

    def datos_factura(self, factura_id: uuid.UUID) -> tuple[Decimal, str]:
        """`(total_factura, numero_factura)` de la factura — UNA consulta, sin importar
        `FacturaCliente` (acoplaría F3 a F2 en tiempo de import); se resuelve por SQL
        crudo sobre la tabla, igual que otros módulos leen catálogos ajenos."""
        from app.modules.facturacion.factura_cliente import FacturaCliente

        fila = self._repo.db.execute(
            select(FacturaCliente.total_factura, FacturaCliente.numero_factura).where(
                FacturaCliente.factura_id == factura_id
            )
        ).one_or_none()
        if fila is None:  # pragma: no cover — FK NOT NULL lo garantiza
            raise DomainError("La FacturaCliente asociada no existe.")
        return Decimal(fila[0]).quantize(CENTAVOS), fila[1]

    def _enriquecida(self, leida: CobranzaFacturaRead) -> CobranzaFacturaRead:
        total_factura, numero_factura = self.datos_factura(leida.factura_id)
        cobrado = self.importe_cobrado(leida.cobranza_id)
        leida.importe_cobrado = cobrado
        leida.importe_pendiente_cobro = (total_factura - cobrado).quantize(CENTAVOS)
        leida.numero_factura = numero_factura
        leida.vencida = (
            leida.estatus_cobro != EstatusCobro.COBRADA.value
            and leida.fecha_estimada_cobro < date.today()
        )
        return leida

    def get(self, id_: Any) -> CobranzaFacturaRead:
        return self._enriquecida(super().get(id_))

    def list(self, params: ListParams) -> Page[CobranzaFacturaRead]:
        pagina = super().list(params)
        for item in pagina.items:
            self._enriquecida(item)
        return pagina

    def update(
        self, id_: Any, data: CobranzaFacturaUpdate, usuario: CurrentUser
    ) -> CobranzaFacturaRead:
        obj = self._get_or_404(id_)
        payload = data.model_dump(exclude_unset=True)
        if "dias_credito" in payload:
            obj.dias_credito = payload.pop("dias_credito")
            self._recalcular_fecha_estimada(obj)
        for campo, valor in payload.items():
            setattr(obj, campo, valor)
        self._repo.db.commit()
        self._repo.db.refresh(obj)
        return self._enriquecida(self._to_read(obj))

    # ── Handoff con F2 (creación) ─────────────────────────────────────────────
    def crear_para_factura(self, factura: Any, usuario: CurrentUser) -> None:
        """Crea la `CobranzaFactura` al TIMBRAR (spec: 1:1, dispara F2). Sin `commit`
        propio — el llamador es `FacturaClienteService.timbrar`, misma sesión.

        Idempotente: si ya existe (reintento de timbrado tras un fallo a medio camino),
        no la duplica — mismo criterio que `marcar_facturada`.
        """
        from app.modules.catalogos.anunciante import Anunciante
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        if db.scalar(
            select(CobranzaFactura.cobranza_id).where(
                CobranzaFactura.factura_id == factura.factura_id
            )
        ):
            return  # ya existe: nada que hacer

        anunciante = db.get(Anunciante, factura.anunciante_id)
        if anunciante is None:  # pragma: no cover — la FK de la factura lo garantiza
            raise DomainError("El anunciante de la factura no existe.")

        obj = CobranzaFactura(
            cobranza_id=uuid4(),
            factura_id=factura.factura_id,
            anunciante_id=factura.anunciante_id,
            metodo_pago_clave=factura.metodo_pago_clave,
            dias_credito=anunciante.dias_credito_default,
            # Ancla PROVISIONAL (ver docstring del módulo): `fecha_entrega_factura` aún
            # no existe en este punto, se llena hasta `entregar()`.
            fecha_estimada_cobro=(
                factura.fecha_entrega_factura or factura.fecha_timbrado or date.today()
            )
            + timedelta(days=anunciante.dias_credito_default),
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)

    def refrescar_fecha_estimada(self, factura_id: uuid.UUID) -> None:
        """Recalcula `fecha_estimada_cobro` con el ancla REAL una vez que
        `FacturaCliente.fecha_entrega_factura` ya existe. La invoca
        `FacturaClienteService.entregar()`, misma sesión, sin `commit` propio.

        Si la `CobranzaFactura` no existe (dato huérfano imposible en el flujo normal,
        pero defensivo) o la factura tampoco, no hace nada: `entregar()` no debe fallar
        por esto.
        """
        obj = self._repo.db.scalar(
            select(CobranzaFactura).where(CobranzaFactura.factura_id == factura_id)
        )
        if obj is None:
            return
        self._recalcular_fecha_estimada(obj)

    def _recalcular_fecha_estimada(self, obj: CobranzaFactura) -> None:
        from app.modules.facturacion.factura_cliente import FacturaCliente

        factura = self._repo.db.get(FacturaCliente, obj.factura_id)
        if factura is None:  # pragma: no cover — la FK lo garantiza
            return
        ancla = factura.fecha_entrega_factura or factura.fecha_timbrado or date.today()
        obj.fecha_estimada_cobro = ancla + timedelta(days=obj.dias_credito)

    # ── Handoff con F2 (cancelación) ──────────────────────────────────────────
    def eliminar_o_rechazar(self, factura_id: uuid.UUID) -> None:
        """Al cancelar la `FacturaCliente`: si ya hay pagos, RECHAZA con 400 (ANTES de
        que `FacturaClienteService.cancelar` toque nada); si no hay ninguno, borra la
        `CobranzaFactura`. Sin `commit` propio — misma sesión que `cancelar()`.
        """
        db = self._repo.db
        obj = db.scalar(
            select(CobranzaFactura).where(CobranzaFactura.factura_id == factura_id)
        )
        if obj is None:
            return  # el handoff nunca ocurrió (cancelar desde preparada/enviada): nada que hacer

        cobrado = self.importe_cobrado(obj.cobranza_id)
        if cobrado > 0:
            raise DomainError(
                "No se puede cancelar: ya se recibieron pagos de esta factura "
                f"(importe_cobrado={cobrado}). Requiere una nota de crédito, que el "
                "sistema todavía no maneja.",
                detalles={"factura_id": str(factura_id), "importe_cobrado": str(cobrado)},
            )
        db.delete(obj)

    # ── Recálculo al crear/borrar un PagoCliente ──────────────────────────────
    def recalcular_tras_pago(self, cobranza: CobranzaFactura, usuario: CurrentUser) -> None:
        """Recalcula `estatus_cobro`/`fecha_cobro` a partir de la suma real de pagos, y
        dispara la cascada hacia F2 cuando el resultado es `cobrada`. Invocado por
        `PagoClienteService.crear`/`eliminar`, misma sesión, sin `commit` propio.
        """
        total_factura, _ = self.datos_factura(cobranza.factura_id)
        cobrado = self.importe_cobrado(cobranza.cobranza_id)

        if cobrado <= 0:
            nuevo = EstatusCobro.PENDIENTE.value
        elif cobrado >= total_factura:
            nuevo = EstatusCobro.COBRADA.value
        else:
            nuevo = EstatusCobro.COBRO_PARCIAL.value

        if nuevo == cobranza.estatus_cobro:
            return  # sin cambio: nada que recalcular ni que disparar de nuevo

        cobranza.estatus_cobro = nuevo
        if nuevo == EstatusCobro.COBRADA.value:
            cobranza.fecha_cobro = date.today()
            from app.modules.facturacion.factura_cliente import (
                FacturaCliente,
                FacturaClienteRepository,
                FacturaClienteService,
            )

            FacturaClienteService(
                FacturaClienteRepository(self._repo.db, FacturaCliente)
            ).marcar_cobrada(cobranza.factura_id)
        else:
            # Se sale de `cobrada` (o nunca se llegó): sin fecha de cobro. Si el estado
            # ANTERIOR era `cobrada`, `PagoClienteService.eliminar` ya rechazó el borrado
            # que hubiera causado esto — este `else` solo se alcanza en la transición
            # pendiente↔cobro_parcial, que nunca tuvo `fecha_cobro` que limpiar.
            cobranza.fecha_cobro = None


def get_cobranza_factura_service(db: Session = Depends(get_db)) -> CobranzaFacturaService:
    return CobranzaFacturaService(
        CobranzaFacturaRepository(
            db, CobranzaFactura, default_order_by=[CobranzaFactura.fecha_estimada_cobro]
        )
    )


# ── Servicio de PagoCliente ───────────────────────────────────────────────────
class PagoClienteService:
    """Sin `BaseService`: no expone `update` (un pago mal capturado se borra y se vuelve
    a capturar, no se edita — evita que "corregir un pago" sea indistinguible de
    "cambiar cuánto se cobró" en la auditoría) y su `create`/`eliminar` necesitan
    recalcular la `CobranzaFactura` padre en la MISMA transacción, que `BaseService` no
    contempla."""

    entidad = "PagoCliente"

    def __init__(self, repo: PagoClienteRepository) -> None:
        self._repo = repo

    def list(self, params: PagoClienteListParams) -> Page[PagoClienteRead]:
        items, total = self._repo.list(params)
        from math import ceil

        return Page[PagoClienteRead](
            items=[PagoClienteRead.model_validate(o) for o in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    def _get_cobranza_or_404(self, cobranza_id: uuid.UUID) -> CobranzaFactura:
        obj = self._repo.db.get(CobranzaFactura, cobranza_id)
        if obj is None:
            raise NotFoundError(
                "CobranzaFactura no encontrada.", detalles={"cobranza_id": str(cobranza_id)}
            )
        return obj

    def crear(
        self, cobranza_id: uuid.UUID, data: PagoClienteCreate, usuario: CurrentUser
    ) -> PagoClienteRead:
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        cobranza = self._get_cobranza_or_404(cobranza_id)

        pago = PagoCliente(
            pago_cliente_id=uuid4(),
            cobranza_id=cobranza_id,
            **data.model_dump(),
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(pago)
        db.flush()  # el recálculo suma por SELECT: el pago debe existir ya en la sesión

        servicio_cobranza = CobranzaFacturaService(CobranzaFacturaRepository(db, CobranzaFactura))
        servicio_cobranza.recalcular_tras_pago(cobranza, usuario)

        db.commit()
        db.refresh(pago)
        return PagoClienteRead.model_validate(pago)

    def eliminar(self, pago_id: uuid.UUID, usuario: CurrentUser) -> None:
        """Borra un pago y recalcula la `CobranzaFactura` padre. RECHAZA con 409 si el
        pago pertenece a una `CobranzaFactura` ya `cobrada` Y borrarlo la haría retroceder
        (ver docstring del módulo) — deshacer un cobro completado exige una nota de
        crédito que el sistema no maneja, mismo principio que ADR-047.
        """
        db = self._repo.db
        pago = db.get(PagoCliente, pago_id)
        if pago is None:
            raise NotFoundError(
                "PagoCliente no encontrado.", detalles={"pago_cliente_id": str(pago_id)}
            )

        cobranza = self._get_cobranza_or_404(pago.cobranza_id)
        servicio_cobranza = CobranzaFacturaService(CobranzaFacturaRepository(db, CobranzaFactura))

        if cobranza.estatus_cobro == EstatusCobro.COBRADA.value:
            total_factura, _ = servicio_cobranza.datos_factura(cobranza.factura_id)
            cobrado_actual = servicio_cobranza.importe_cobrado(cobranza.cobranza_id)
            cobrado_sin_este = (cobrado_actual - Decimal(pago.monto_aplicado)).quantize(CENTAVOS)
            if cobrado_sin_este < total_factura:
                raise ConflictError(
                    "No se puede borrar: esta factura ya está COBRADA en su totalidad. "
                    "Borrar este pago la dejaría incompleta, y deshacer un cobro "
                    "completado requiere una nota de crédito que el sistema no maneja.",
                    detalles={
                        "pago_cliente_id": str(pago_id),
                        "cobranza_id": str(cobranza.cobranza_id),
                    },
                )

        db.delete(pago)
        db.flush()
        servicio_cobranza.recalcular_tras_pago(cobranza, usuario)
        db.commit()


def get_pago_cliente_service(db: Session = Depends(get_db)) -> PagoClienteService:
    return PagoClienteService(
        PagoClienteRepository(db, PagoCliente, default_order_by=[PagoCliente.fecha_pago_cliente])
    )


# ── Router ────────────────────────────────────────────────────────────────────
router_cobranza = APIRouter(prefix="/facturas", tags=["cobranza:facturas"])


@router_cobranza.get("", response_model=Page[CobranzaFacturaRead])
def listar_cobranza_facturas(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    factura_id: uuid.UUID | None = Query(None),
    anunciante_id: uuid.UUID | None = Query(None),
    estatus_cobro: str | None = Query(None),
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: CobranzaFacturaService = Depends(get_cobranza_factura_service),
) -> Page[CobranzaFacturaRead]:
    return svc.list(
        CobranzaFacturaListParams(
            page=page,
            size=size,
            factura_id=factura_id,
            anunciante_id=anunciante_id,
            estatus_cobro=estatus_cobro,
        )
    )


@router_cobranza.get("/{item_id}", response_model=CobranzaFacturaRead)
def obtener_cobranza_factura(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: CobranzaFacturaService = Depends(get_cobranza_factura_service),
) -> CobranzaFacturaRead:
    return svc.get(item_id)


@router_cobranza.put("/{item_id}", response_model=CobranzaFacturaRead)
def actualizar_cobranza_factura(
    item_id: uuid.UUID,
    payload: CobranzaFacturaUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:editar")),
    svc: CobranzaFacturaService = Depends(get_cobranza_factura_service),
) -> CobranzaFacturaRead:
    """Edita `dias_credito` (recalcula `fecha_estimada_cobro`), `metodo_pago_clave` o
    `comentarios_cobranza`. `estatus_cobro`/`fecha_cobro`/los importes NO son editables:
    son calculados."""
    return svc.update(item_id, payload, usuario)


router_pagos_cliente = APIRouter(prefix="/facturas/{cobranza_id}/pagos", tags=["cobranza:pagos"])


@router_pagos_cliente.get("", response_model=Page[PagoClienteRead])
def listar_pagos_cliente(
    cobranza_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> Page[PagoClienteRead]:
    return svc.list(PagoClienteListParams(page=page, size=size, cobranza_id=cobranza_id))


@router_pagos_cliente.post("", response_model=PagoClienteRead, status_code=201)
def crear_pago_cliente(
    cobranza_id: uuid.UUID,
    payload: PagoClienteCreate,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:crear")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> PagoClienteRead:
    return svc.crear(cobranza_id, payload, usuario)


router_pagos_cliente_por_id = APIRouter(prefix="/pagos", tags=["cobranza:pagos"])


@router_pagos_cliente_por_id.delete("/{pago_id}", status_code=204)
def eliminar_pago_cliente(
    pago_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:editar")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> None:
    svc.eliminar(pago_id, usuario)
