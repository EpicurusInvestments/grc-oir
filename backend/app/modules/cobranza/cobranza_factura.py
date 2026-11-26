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

**La cascada SÍ tiene reversa (ADR-286, reemplaza la regla "ciega" de ADR-271).**
`PagoClienteService.cancelar` puede deshacer una `CobranzaFactura` que ya estaba
`cobrada`: `recalcular_tras_pago` detecta que el estado ANTERIOR era `cobrada` y el
NUEVO ya no lo es, y llama `FacturaClienteService.revertir_cobro` (que a su vez llama
`OrdenClienteService.revertir_cobro` para cada orden) — misma transacción, mismo
mecanismo de handoff que la cascada hacia adelante. Lo único que SÍ bloquea la
cancelación, validado ANTES de tocar cualquier fila: que alguna de las órdenes
involucradas ya tenga una `FacturaAgencia`/`FacturaVendedor`/`FacturaAfiliado`
autorizada o pagada con base en que estaba `cobrada` (`comisiones_comprometidas_de_orden`
en `factura_cliente.py`) — eso sí es un compromiso tomado que ya no se puede deshacer
limpiamente. Cancelar un pago que NUNCA llegó a completar el cobro (la
`CobranzaFactura` seguía `pendiente`/`cobro_parcial`) se permite igual, sin pasar por
ninguna de estas validaciones (no hay nada que revertir aguas arriba).

ADR-271 también cancela TODO el pago "global" de una sola vez: todas las filas de
`PagoCliente` que comparten `pago_multiple_id` (o la única fila si es un pago
individual), no una factura aplicada a la vez — ver `PagoClienteService._resolver_grupo`.
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
#: ADR-270: tope del "Ajuste" por renglón del pago múltiple (+/- $10). ADR-273 quitó el
#: umbral que antes separaba una diferencia chica (exige ajuste) de un "pago de menos"
#: grande tolerado como huérfano (ADR-230) — ahora CUALQUIER diferencia se rechaza; esta
#: constante solo acota lo que el Ajuste puede cubrir por renglón.
_ADR270_TOLERANCIA = Decimal("10")


class EstatusCobro(StrEnum):
    PENDIENTE = "pendiente"
    COBRO_PARCIAL = "cobro_parcial"
    COBRADA = "cobrada"


_ESTADOS_SQL = ", ".join(f"'{e.value}'" for e in EstatusCobro)


class EstatusPago(StrEnum):
    """ADR-271 — estatus del `PagoCliente` en sí (distinto de `EstatusCobro`, que es el
    de la `CobranzaFactura`). `CANCELADO` es terminal: no hay "descancelar"."""

    PAGADO = "pagado"
    CANCELADO = "cancelado"


_ESTADOS_PAGO_SQL = ", ".join(f"'{e.value}'" for e in EstatusPago)


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
    # ADR-225 (petición del usuario): derivado igual que `anunciante_id` — hace falta
    # para filtrar "facturas pendientes de esta AGENCIA" en el picker de pago múltiple.
    # `None` = facturación directa (sin agencia), mismo criterio que `FacturaCliente`.
    agencia_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("agencia.agencia_id", name="fk_cobranza_factura_agencia"),
        default=None,
    )
    # ADR-236 (petición del usuario, reportado con captura): `agencia_id` NO alcanza para
    # filtrar "del Anunciante" vs "de la Agencia" en el picker de Pago Múltiple —
    # `agencia_id` es solo una referencia capturada en la orden y puede estar lleno aunque
    # el receptor real sea el anunciante directo. Copiado de `FacturaCliente.
    # facturado_directo` (mismo criterio ya usado para `agencia_id`, ver arriba).
    facturado_directo: Mapped[bool] = mapped_column(default=True)

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

    ADR-271 (petición del usuario, "Cancelación de Pago") cambia el criterio de baja:
    un pago SIN asignar (nunca tocó ninguna factura) sigue con `DELETE` físico, a
    propósito (ADR-035). Un pago YA ASIGNADO ya NO se borra — se CANCELA
    (`estatus_pago`, baja lógica): la fila se queda, visible en "Pagos recibidos" con
    su estatus, y `CobranzaFacturaService.importe_cobrado` la excluye de la suma. Ver
    `PagoClienteService.cancelar`/`eliminar` y el docstring del módulo.
    """

    __tablename__ = "pago_cliente"
    __table_args__ = (
        CheckConstraint("monto_aplicado > 0", name="ck_pago_cliente_monto"),
        CheckConstraint("ajuste BETWEEN -10 AND 10", name="ck_pago_cliente_ajuste"),
        CheckConstraint(
            f"estatus_pago IN ({_ESTADOS_PAGO_SQL})", name="ck_pago_cliente_estatus_pago"
        ),
    )

    pago_cliente_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # ADR-229 (petición del usuario): nullable — un pago puede capturarse SIN saber
    # todavía a qué factura corresponde ("pago no asignado"), y asignarse después
    # (`PagoClienteService.asignar`). `None` = no asignado; nunca vuelve a `None` una
    # vez asignado (no hay "desasignar").
    cobranza_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey(
            "cobranza_factura.cobranza_id", name="fk_pago_cliente_cobranza", ondelete="NO ACTION"
        ),
        index=True,
        default=None,
    )
    fecha_pago_cliente: Mapped[date] = mapped_column(fecha_sql())
    monto_aplicado: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # ADR-270 (petición del usuario, "Correcciones en pagos múltiples"): corrección de
    # +/- $10 sobre `monto_aplicado`, solo del pago múltiple — absorbe diferencias chicas
    # (comisión bancaria, redondeo) para que el pago cuadre exacto contra lo capturado,
    # sin tocar el pendiente real de la factura. Default 0 en el pago individual (no se
    # captura ahí, ver `PagoClienteCreate`).
    ajuste: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    # ADR-271: ver docstring de la clase — default 'pagado', nunca lo manda el cliente.
    estatus_pago: Mapped[str] = mapped_column(Unicode(20), default=EstatusPago.PAGADO.value)
    # ADR-225: nullable desde que existe el pago múltiple — ese flujo no lo captura (el
    # usuario no lo pidió ahí); el pago individual lo sigue exigiendo vía
    # `PagoClienteCreate.metodo_pago_clave` (Pydantic), no por esta columna.
    metodo_pago_clave: Mapped[str | None] = mapped_column(Unicode(20), default=None)
    referencia_pago: Mapped[str | None] = mapped_column(Unicode(100), default=None)
    archivo_nombre: Mapped[str | None] = mapped_column(Unicode(255), default=None)
    archivo_path: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    # ADR-225 (petición del usuario) — "Forma de pago" (efectivo/cheque/transferencia…):
    # clave de `ConstantesSistema` grupo FormaPago, sin FK formal (mismo patrón sin FK
    # que `metodo_pago_clave`) — reutiliza el catálogo que F2 ya usa para
    # `FacturaCliente.forma_pago_clave`, no uno nuevo. Se agrega también al pago
    # individual, no solo al múltiple (petición explícita del usuario).
    forma_pago_clave: Mapped[str | None] = mapped_column(Unicode(20), default=None)
    fecha_deposito: Mapped[date | None] = mapped_column(fecha_sql(), default=None)
    #: Parcialidad del pago, texto libre (p.ej. "2 de 3") — no hay catálogo ni fórmula,
    #: el usuario lo captura tal cual.
    numero_pago: Mapped[str | None] = mapped_column(Unicode(20), default=None)
    cuenta_contable_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("cuenta_contable.cuenta_contable_id", name="fk_pago_cliente_cuenta_contable"),
        default=None,
    )
    #: Comparte este UUID TODO pago creado en UNA misma captura de pago múltiple
    #: (trazabilidad/agrupación) — `None` en un pago individual.
    pago_multiple_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), default=None, index=True)
    # ADR-256 (petición del usuario, "NEW FEATURE", mismo criterio que
    # `FacturaCliente.facturado_en_sistema_externo`, ADR-248): solo IDENTIFICA que este
    # pago en realidad se registró/concilió en otro sistema (p.ej. OIR) — no cambia
    # ningún cálculo ni ninguna otra parte del flujo de cobranza.
    pagado_en_sistema_externo: Mapped[bool] = mapped_column(default=False)
    # ADR-286 (petición del usuario): motivo obligatorio al CANCELAR un pago (antes no
    # se capturaba nada) — nullable solo porque un pago nunca cancelado no lo tiene.
    motivo_cancelacion: Mapped[str | None] = mapped_column(Unicode(255), default=None)

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
    agencia_id: uuid.UUID | None = None
    facturado_directo: bool = True
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
    #: Petición del usuario (columna "Número de parcialidad" en la lista): el
    #: `numero_pago` del ÚLTIMO `PagoCliente` registrado para esta cobranza — "último" por
    #: `fecha_pago_cliente` (la fecha real del pago, no cuándo se capturó en el sistema),
    #: con `created_at` como desempate si dos pagos comparten fecha (p.ej. un pago
    #: múltiple). `None` si todavía no hay ningún pago, o si el último no capturó
    #: `numero_pago` (el pago múltiple lo deja opcional).
    ultimo_numero_pago: str | None = None
    #: Petición del usuario (columna "Número de Parcialidad" en la tabla de Pago
    #: Múltiple): cantidad de `PagoCliente` ya registrados para esta cobranza + 1, como
    #: string — por CONTEO, no por parsear `ultimo_numero_pago` (que es texto libre y
    #: puede no ser numérico). El frontend lo envía tal cual, de solo lectura, como
    #: `numero_pago` de ESE renglón al registrar el pago múltiple.
    siguiente_numero_pago: str = "1"
    #: ADR-281 (petición del usuario, columnas "Fecha de pago"/"Fecha de aplicación" de
    #: la lista): fecha real del pago y fecha de depósito del ÚLTIMO `PagoCliente` de
    #: esta cobranza — mismo criterio de "último" que `ultimo_numero_pago` arriba.
    #: `None` si todavía no hay ningún pago.
    fecha_pago: date | None = None
    fecha_deposito: date | None = None


class CobranzaFacturaListParams(ListParams):
    factura_id: uuid.UUID | None = None
    anunciante_id: uuid.UUID | None = None
    agencia_id: uuid.UUID | None = None
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
    #: ADR-229: `None` = pago no asignado todavía a ninguna factura.
    cobranza_id: uuid.UUID | None = None
    fecha_pago_cliente: date
    monto_aplicado: Decimal
    # ADR-270: corrección de +/- $10 del pago múltiple; 0 en el pago individual.
    ajuste: Decimal = Decimal("0")
    # ADR-271: 'cancelado' excluye este pago de `importe_cobrado`, sin borrarlo.
    estatus_pago: EstatusPago = EstatusPago.PAGADO
    metodo_pago_clave: str | None = None
    referencia_pago: str | None = None
    archivo_nombre: str | None = None
    archivo_path: str | None = None
    # ADR-225
    forma_pago_clave: str | None = None
    fecha_deposito: date | None = None
    numero_pago: str | None = None
    cuenta_contable_id: uuid.UUID | None = None
    pago_multiple_id: uuid.UUID | None = None
    pagado_en_sistema_externo: bool = False
    # ADR-286: motivo capturado al cancelar — `None` si nunca se canceló.
    motivo_cancelacion: str | None = None
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
    # ADR-225 (petición del usuario): se agregan también al pago individual.
    forma_pago_clave: str = Field(min_length=1, max_length=20)
    fecha_deposito: date | None = None
    numero_pago: str | None = Field(default=None, max_length=20)
    cuenta_contable_id: uuid.UUID
    # ADR-256 (petición del usuario, "NEW FEATURE")
    pagado_en_sistema_externo: bool = False


class PagoClienteCancelarRequest(BaseModel):
    """ADR-286 (petición del usuario): motivo obligatorio al cancelar un pago — antes el
    endpoint no recibía body."""

    model_config = ConfigDict(extra="forbid")

    motivo: str = Field(min_length=3, max_length=255)


class PagoAsignarFacturaRequest(BaseModel):
    """ADR-229/231 (petición del usuario): asigna una factura a un pago capturado SIN
    asignar. Solo aplica una vez — un pago ya asignado no se puede reasignar aquí.

    ADR-231: `monto_aplicado` puede ser MENOR al monto total del huérfano — el resto se
    queda en el propio huérfano (más chico), no se le asigna de más a la factura."""

    model_config = ConfigDict(extra="forbid")

    cobranza_id: uuid.UUID
    monto_aplicado: Decimal = Field(gt=0)


class PagoMultipleItemCreate(BaseModel):
    """Una factura seleccionada, el monto que se le asigna y SU parcialidad.

    ADR-227 (petición del usuario): `numero_pago` vive AQUÍ, no en `PagoMultipleCreate`
    — cada factura tiene su propio historial de pagos, así que la parcialidad "último +
    1" es independiente por factura (una puede ir en su 1er pago, otra en su 3°, en el
    MISMO lote de pago múltiple). El frontend lo calcula (`CobranzaFacturaRead.
    siguiente_numero_pago`) y lo manda de solo lectura, sin que el usuario lo escriba."""

    model_config = ConfigDict(extra="forbid")

    cobranza_id: uuid.UUID
    monto_aplicado: Decimal = Field(gt=0)
    numero_pago: str | None = Field(default=None, max_length=20)
    # ADR-270 (petición del usuario, "Correcciones en pagos múltiples"): corrección de
    # +/- $10 que se SUMA a `monto_aplicado` al validar el cuadre exacto contra
    # `monto_total_pago` — ver docstring de `PagoMultipleCreate` y `crear_multiple`.
    ajuste: Decimal = Field(default=Decimal("0"), ge=-10, le=10)


class PagoMultipleCreate(BaseModel):
    """Pago múltiple (ADR-225, petición del usuario): un solo pago recibido que se
    reparte entre varias facturas del MISMO anunciante o agencia — cada factura
    seleccionada se registra como su propio `PagoCliente` (mismos datos del pago,
    monto propio), todas con el mismo `pago_multiple_id` para trazabilidad.

    ADR-270 (petición del usuario, "Correcciones en pagos múltiples") — el pago ya NO
    puede quedar de más ni de menos: cada renglón trae un `ajuste` (+/- $10) que se suma
    a su `monto_aplicado`. Si la suma total (aplicado + ajuste) no cuadra exacto contra
    `monto_total_pago`, se RECHAZA — hay que seleccionar más facturas, subir los montos
    aplicados, o usar la columna de Ajuste para cuadrar exacto.

    ADR-273 (petición del usuario, "Correcciones en pagos múltiples — parte 2"): a
    diferencia de ADR-230 (ya retirado de AQUÍ), una diferencia por debajo del total —
    sin importar qué tan grande— YA NO genera un `PagoCliente` "huérfano" con el
    sobrante: se rechaza siempre. El mecanismo de huérfano en sí (`cobranza_id=None`)
    sigue existiendo para otros flujos (`/pagos/no-asignados`, `/asignar`, ADR-229/231)
    — solo se quitó la creación automática desde ESTE endpoint."""

    model_config = ConfigDict(extra="forbid")

    fecha_pago_cliente: date
    #: Lo que de verdad entró — debe cuadrar EXACTO contra `pagos` (ver docstring de la
    #: clase); el tablero del front llama a esto "Monto por asignar".
    monto_total_pago: Decimal = Field(gt=0)
    forma_pago_clave: str = Field(min_length=1, max_length=20)
    fecha_deposito: date | None = None
    referencia_pago: str | None = Field(default=None, max_length=100)
    cuenta_contable_id: uuid.UUID
    pagos: list[PagoMultipleItemCreate] = Field(min_length=1)
    #: ADR-230: si este lote en realidad está REPARTIENDO un pago "huérfano" (sin
    #: asignar) ya existente —en vez de capturar dinero nuevo—, aquí va su id: se borra
    #: como parte de ESTA MISMA transacción. ADR-273: el reparto debe cubrir el monto
    #: COMPLETO del huérfano (ya no puede dejar un sobrante más chico). `None` = captura
    #: nueva normal.
    pago_origen_id: uuid.UUID | None = None
    # ADR-256 (petición del usuario, "NEW FEATURE"): mismo flag que el pago individual —
    # se incluye en `comunes` (ver `crear_multiple`), así que viaja a CADA `PagoCliente`
    # del lote.
    pagado_en_sistema_externo: bool = False


class PagoGrupoRead(BaseModel):
    """ADR-271 — un pago "global" para la pantalla "Pagos recibidos": agrupa TODAS las
    filas de `PagoCliente` que comparten `pago_multiple_id` (o la única fila, si es un
    pago individual sin `pago_multiple_id`). Antes esa pantalla listaba una fila por
    factura aplicada; ahora una fila por pago, como pidió el usuario.

    `pago_cliente_id` es un REPRESENTANTE del grupo (la fila con el id más chico) — basta
    para pedir el detalle (`detalle_agrupado`) o cancelar (`cancelar`, que resuelve el
    grupo completo a partir de cualquiera de sus filas)."""

    pago_cliente_id: uuid.UUID
    pago_multiple_id: uuid.UUID | None = None
    fecha_pago_cliente: date
    referencia_pago: str | None = None
    #: Lo que de verdad se capturó — SUM(monto_aplicado + ajuste) de TODO el grupo
    #: (incluye un "huérfano" sin asignar si comparte `pago_multiple_id`, aunque desde
    #: ADR-273 `crear_multiple` ya no lo genere por sí solo). Por el invariante de
    #: `crear_multiple` (ADR-270/272), siempre da exacto el `monto_total_pago` original;
    #: en un pago individual, es simplemente su `monto_aplicado`.
    monto_pago: Decimal
    #: Facturas DISTINTAS cubiertas (no cuenta el "huérfano" sin asignar).
    cantidad_facturas: int
    estatus_pago: EstatusPago


class PagoGrupoAplicacionRead(BaseModel):
    """Una factura cubierta por el pago — fila del detalle de `PagoGrupoDetalleRead`."""

    pago_cliente_id: uuid.UUID
    cobranza_id: uuid.UUID
    numero_factura: str | None = None
    numero_pago: str | None = None
    #: El pendiente real que se le acreditó a ESTA factura (sin el `ajuste`, que no
    #: toca la factura — ver `CobranzaFacturaService.importe_cobrado`).
    monto_aplicado: Decimal


class PagoGrupoDetalleRead(BaseModel):
    """Detalle de un pago global al seleccionarlo en "Pagos recibidos": sus facturas
    aplicadas + el total, que debe corresponder EXACTO al pago (ver `PagoGrupoRead.
    monto_pago`) — puede no ser igual a la suma de `aplicaciones` si hubo `ajuste` o un
    "huérfano" que comparta `pago_multiple_id` (ADR-230/270/272)."""

    aplicaciones: list[PagoGrupoAplicacionRead]
    total_pago: Decimal
    estatus_pago: EstatusPago
    #: ADR-286: motivo capturado al cancelar — `None` si el pago sigue vigente.
    motivo_cancelacion: str | None = None


# ── Repositorios ──────────────────────────────────────────────────────────────
class CobranzaFacturaRepository(BaseRepository[CobranzaFactura]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # NO se llama a super()._apply_filters: esta entidad no tiene `activo`.
        factura_id = getattr(params, "factura_id", None)
        if factura_id is not None:
            stmt = stmt.where(CobranzaFactura.factura_id == factura_id)
        anunciante_id = getattr(params, "anunciante_id", None)
        agencia_id = getattr(params, "agencia_id", None)
        if agencia_id is not None:
            # ADR-236 (petición del usuario, reportado con captura): `agencia_id` por sí
            # solo NO basta — puede estar lleno (como referencia capturada en la orden)
            # aunque el receptor real sea el anunciante directo (ADR-235 lo dejaba pasar
            # de más). `facturado_directo == False` es el booleano real del receptor.
            stmt = stmt.where(
                CobranzaFactura.agencia_id == agencia_id,
                CobranzaFactura.facturado_directo == False,  # noqa: E712 — BIT en SQL Server
            )
        elif anunciante_id is not None:
            # ADR-235/236: "del Anunciante" (facturación directa) — antes se excluía solo
            # por `agencia_id IS NULL`, que tampoco basta por la misma razón de arriba.
            stmt = stmt.where(
                CobranzaFactura.anunciante_id == anunciante_id,
                CobranzaFactura.facturado_directo == True,  # noqa: E712 — BIT en SQL Server
            )
        estatus = getattr(params, "estatus_cobro", None)
        if estatus is not None:
            stmt = stmt.where(CobranzaFactura.estatus_cobro == estatus)
        return stmt


class PagoClienteRepository(BaseRepository[PagoCliente]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        cobranza_id = getattr(params, "cobranza_id", None)
        if cobranza_id is not None:
            stmt = stmt.where(PagoCliente.cobranza_id == cobranza_id)
        # ADR-229 (petición del usuario): filtro "Pagos no asignados".
        if getattr(params, "sin_asignar", False):
            stmt = stmt.where(PagoCliente.cobranza_id.is_(None))
        return stmt


class PagoClienteListParams(ListParams):
    cobranza_id: uuid.UUID | None = None
    sin_asignar: bool = False


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
        # ADR-271: un pago CANCELADO ya no cuenta — este filtro es lo único que hace
        # falta para que "cancelar" recalcule la factura de vuelta a pendiente/parcial
        # con la MISMA maquinaria que ya usan crear()/asignar() (`recalcular_tras_pago`).
        total = self._repo.db.scalar(
            select(func.coalesce(func.sum(PagoCliente.monto_aplicado), 0)).where(
                PagoCliente.cobranza_id == cobranza_id,
                PagoCliente.estatus_pago == EstatusPago.PAGADO.value,
            )
        )
        return Decimal(total or 0).quantize(CENTAVOS)

    def _info_pagos(
        self, cobranza_id: uuid.UUID
    ) -> tuple[str | None, str, date | None, date | None]:
        """`(ultimo_numero_pago, siguiente_numero_pago, fecha_pago, fecha_deposito)` en
        UNA sola consulta (`COUNT(*) OVER()` junto con los datos del pago más reciente —
        ver docstrings de `CobranzaFacturaRead`): orden por `fecha_pago_cliente` desc,
        `created_at` desc como desempate. Sin pagos todavía: `(None, "1", None, None)`."""
        fila = self._repo.db.execute(
            select(
                PagoCliente.numero_pago,
                func.count().over().label("total"),
                PagoCliente.fecha_pago_cliente,
                PagoCliente.fecha_deposito,
            )
            .where(PagoCliente.cobranza_id == cobranza_id)
            .order_by(PagoCliente.fecha_pago_cliente.desc(), PagoCliente.created_at.desc())
            .limit(1)
        ).one_or_none()
        if fila is None:
            return None, "1", None, None
        return fila[0], str(fila[1] + 1), fila[2], fila[3]

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
        (
            leida.ultimo_numero_pago,
            leida.siguiente_numero_pago,
            leida.fecha_pago,
            leida.fecha_deposito,
        ) = self._info_pagos(leida.cobranza_id)
        leida.vencida = (
            leida.estatus_cobro != EstatusCobro.COBRADA.value
            and leida.fecha_estimada_cobro < date.today()
        )
        return leida

    # ADR-277 (petición del usuario): suma del adeudo VENCIDO de un anunciante —
    # consumido por el alta de `OrdenCliente` (bloquea si excede `monto_maximo_credito`)
    # y por el frontend (alerta al seleccionar el anunciante). Mismo criterio de
    # "vencida" que `_enriquecida` (no cobrada + `fecha_estimada_cobro` ya pasó); se
    # reusan `datos_factura`/`importe_cobrado` fila por fila — el número de facturas
    # vencidas por anunciante es chico, no hace falta una consulta agregada.
    def adeudo_vencido(self, anunciante_id: uuid.UUID) -> Decimal:
        filas = self._repo.db.execute(
            select(CobranzaFactura.cobranza_id, CobranzaFactura.factura_id).where(
                CobranzaFactura.anunciante_id == anunciante_id,
                CobranzaFactura.estatus_cobro != EstatusCobro.COBRADA.value,
                CobranzaFactura.fecha_estimada_cobro < date.today(),
            )
        ).all()
        total = Decimal("0")
        for cobranza_id, factura_id in filas:
            total_factura, _ = self.datos_factura(factura_id)
            total += total_factura - self.importe_cobrado(cobranza_id)
        return total.quantize(CENTAVOS)

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
            agencia_id=factura.agencia_id,
            facturado_directo=factura.facturado_directo,
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
    def eliminar_o_rechazar(
        self, factura_id: uuid.UUID, usuario: CurrentUser, motivo: str
    ) -> None:
        """Al cancelar la `FacturaCliente`: si ya hay pagos recibidos, los cancela EN
        CASCADA (fix, petición del usuario — antes rechazaba con 400 pidiendo "una nota
        de crédito que el sistema no maneja", mismo defecto que ADR-286 ya corrigió para
        "Cancelar pago"); si no hay ninguno, borra la `CobranzaFactura`. Sin `commit`
        propio en su propia escritura final, pero SÍ reusa `PagoClienteService.cancelar`
        (que comitea por cada grupo cancelado) — aceptable: varios commits dentro de la
        misma request, mismo patrón ya usado en otros puntos del módulo.

        Reusa `PagoClienteService.cancelar` por cada pago GLOBAL distinto (agrupado por
        `pago_multiple_id`, para no cancelar el mismo grupo 2 veces si cubrió esta
        factura con más de una fila) — así la cascada de Requisiciones autorizadas
        (ver `PagoClienteService.cancelar`) sale gratis, sin duplicar lógica.
        """
        db = self._repo.db
        obj = db.scalar(
            select(CobranzaFactura).where(CobranzaFactura.factura_id == factura_id)
        )
        if obj is None:
            return  # el handoff nunca ocurrió (cancelar desde preparada/enviada): nada que hacer

        pagos_activos = db.scalars(
            select(PagoCliente).where(
                PagoCliente.cobranza_id == obj.cobranza_id,
                PagoCliente.estatus_pago == EstatusPago.PAGADO.value,
            )
        ).all()
        servicio_pago = PagoClienteService(PagoClienteRepository(db, PagoCliente))
        ya_cancelados: set[uuid.UUID] = set()
        for pago in pagos_activos:
            grupo_key = pago.pago_multiple_id or pago.pago_cliente_id
            if grupo_key in ya_cancelados:
                continue
            ya_cancelados.add(grupo_key)
            servicio_pago.cancelar(
                pago.pago_cliente_id,
                usuario,
                motivo=f"Cancelado en cascada al cancelar la factura: {motivo}",
            )

        # Si ya no queda NINGÚN PagoCliente (activo ni cancelado) referenciando esta
        # CobranzaFactura, se borra (comportamiento de siempre). Si quedaron filas
        # CANCELADAS por la cascada de arriba, se deja la CobranzaFactura (se dejaría un
        # registro huérfano sin ella, violando su FK, y se pierde el rastro de auditoría
        # de esos pagos).
        quedan = db.scalar(
            select(func.count())
            .select_from(PagoCliente)
            .where(PagoCliente.cobranza_id == obj.cobranza_id)
        )
        if not quedan:
            db.delete(obj)

    # ── Recálculo al crear/borrar un PagoCliente ──────────────────────────────
    def recalcular_tras_pago(self, cobranza: CobranzaFactura, usuario: CurrentUser) -> None:
        """Recalcula `estatus_cobro`/`fecha_cobro` a partir de la suma real de pagos, y
        dispara la cascada hacia F2 cuando el resultado es `cobrada`. Invocado por
        `PagoClienteService.crear`/`asignar`/`crear_multiple`/`cancelar` (ADR-271),
        misma sesión, sin `commit` propio.
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

        estado_anterior = cobranza.estatus_cobro
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
            # Se sale de `cobrada` (o nunca se llegó): sin fecha de cobro.
            cobranza.fecha_cobro = None
            # ADR-286 (petición del usuario): si el estado ANTERIOR era `cobrada`, hay
            # que deshacer también la cascada hacia F2/F1 que `marcar_cobrada` ya había
            # disparado — `PagoClienteService.cancelar` ya validó, ANTES de llegar aquí,
            # que ninguna comisión (agencia/vendedor/afiliado) se comprometió con base en
            # ese estado, así que revertir es seguro. Si el anterior NO era `cobrada`
            # (transición pendiente↔cobro_parcial), no hay nada que revertir aguas
            # arriba: nunca se disparó `marcar_cobrada`.
            if estado_anterior == EstatusCobro.COBRADA.value:
                from app.modules.facturacion.factura_cliente import (
                    FacturaCliente,
                    FacturaClienteRepository,
                    FacturaClienteService,
                )

                FacturaClienteService(
                    FacturaClienteRepository(self._repo.db, FacturaCliente)
                ).revertir_cobro(cobranza.factura_id)


def get_cobranza_factura_service(db: Session = Depends(get_db)) -> CobranzaFacturaService:
    # ADR-281 (petición del usuario): "ordenar por fecha estimada y luego por fecha de
    # pago" — la fecha de pago vive en `PagoCliente` (tabla hija), así que el desempate
    # es una subconsulta correlacionada al ÚLTIMO pago de cada cobranza (mismo criterio
    # de "último" que `_info_pagos`: `fecha_pago_cliente` desc, `created_at` desc).
    ultima_fecha_pago = (
        select(PagoCliente.fecha_pago_cliente)
        .where(PagoCliente.cobranza_id == CobranzaFactura.cobranza_id)
        .order_by(PagoCliente.fecha_pago_cliente.desc(), PagoCliente.created_at.desc())
        .limit(1)
        .correlate(CobranzaFactura)
        .scalar_subquery()
    )
    return CobranzaFacturaService(
        CobranzaFacturaRepository(
            db,
            CobranzaFactura,
            default_order_by=[CobranzaFactura.fecha_estimada_cobro, ultima_fecha_pago],
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

    def _validar_cuenta_contable(self, cuenta_contable_id: uuid.UUID) -> None:
        from app.modules.catalogos.cuenta_contable import CuentaContable

        if self._repo.db.get(CuentaContable, cuenta_contable_id) is None:
            raise DomainError(
                "La cuenta contable indicada no existe.",
                detalles={"cuenta_contable_id": str(cuenta_contable_id)},
            )

    def crear(
        self, cobranza_id: uuid.UUID, data: PagoClienteCreate, usuario: CurrentUser
    ) -> PagoClienteRead:
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        cobranza = self._get_cobranza_or_404(cobranza_id)
        self._validar_cuenta_contable(data.cuenta_contable_id)

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

    def crear_sin_asignar(self, data: PagoClienteCreate, usuario: CurrentUser) -> PagoClienteRead:
        """ADR-229 (petición del usuario): un pago recibido que todavía no se sabe a qué
        factura corresponde — mismos datos que el pago individual, pero SIN
        `cobranza_id` (se asigna después vía `asignar()`). Sin recálculo: no hay
        cobranza a la que afectar todavía."""
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        self._validar_cuenta_contable(data.cuenta_contable_id)

        pago = PagoCliente(
            pago_cliente_id=uuid4(),
            cobranza_id=None,
            **data.model_dump(),
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(pago)
        db.commit()
        db.refresh(pago)
        return PagoClienteRead.model_validate(pago)

    def asignar(
        self, pago_id: uuid.UUID, data: PagoAsignarFacturaRequest, usuario: CurrentUser
    ) -> PagoClienteRead:
        """ADR-229/231: asigna una factura a un pago capturado SIN asignar — dispara el
        mismo recálculo que `crear()` (la factura puede quedar `cobro_parcial` o
        `cobrada`). Rechaza con 409 si el pago YA está asignado (no hay "reasignar").

        ADR-231 (petición del usuario): si `data.monto_aplicado` es MENOR al monto total
        del huérfano, NO se le asigna de más a la factura — se crea un `PagoCliente`
        NUEVO solo por lo asignado, y el huérfano ORIGINAL se queda (mismo id) con el
        restante, más chico. Si es el monto completo, se reutiliza la misma fila (sin
        split) — comportamiento idéntico al de antes de ADR-231."""
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        pago = db.get(PagoCliente, pago_id)
        if pago is None:
            raise NotFoundError(
                "PagoCliente no encontrado.", detalles={"pago_cliente_id": str(pago_id)}
            )
        if pago.cobranza_id is not None:
            raise ConflictError(
                "Este pago ya está asignado a una factura.",
                detalles={"pago_cliente_id": str(pago_id), "cobranza_id": str(pago.cobranza_id)},
            )
        if data.monto_aplicado > pago.monto_aplicado:
            raise DomainError(
                "El monto a asignar no puede exceder el monto del pago sin asignar.",
                detalles={
                    "monto_aplicado": str(data.monto_aplicado),
                    "monto_sin_asignar": str(pago.monto_aplicado),
                },
            )

        cobranza = self._get_cobranza_or_404(data.cobranza_id)
        servicio_cobranza = CobranzaFacturaService(CobranzaFacturaRepository(db, CobranzaFactura))
        restante = (pago.monto_aplicado - data.monto_aplicado).quantize(CENTAVOS)

        if restante > 0:
            _, siguiente_numero_pago, _, _ = servicio_cobranza._info_pagos(data.cobranza_id)
            resultado = PagoCliente(
                pago_cliente_id=uuid4(),
                cobranza_id=data.cobranza_id,
                monto_aplicado=data.monto_aplicado,
                fecha_pago_cliente=pago.fecha_pago_cliente,
                metodo_pago_clave=pago.metodo_pago_clave,
                referencia_pago=pago.referencia_pago,
                archivo_nombre=pago.archivo_nombre,
                archivo_path=pago.archivo_path,
                forma_pago_clave=pago.forma_pago_clave,
                fecha_deposito=pago.fecha_deposito,
                numero_pago=siguiente_numero_pago,
                cuenta_contable_id=pago.cuenta_contable_id,
                pago_multiple_id=pago.pago_multiple_id,
                pagado_en_sistema_externo=pago.pagado_en_sistema_externo,
                created_by=resolver_usuario_id(db, usuario.username),
            )
            db.add(resultado)
            pago.monto_aplicado = restante
        else:
            pago.cobranza_id = data.cobranza_id
            resultado = pago

        db.flush()
        servicio_cobranza.recalcular_tras_pago(cobranza, usuario)

        db.commit()
        db.refresh(resultado)
        if restante > 0:
            db.refresh(pago)
        return PagoClienteRead.model_validate(resultado)

    def crear_multiple(
        self, data: PagoMultipleCreate, usuario: CurrentUser
    ) -> list[PagoClienteRead]:
        """Pago múltiple (ADR-225): un `PagoCliente` por cada factura seleccionada,
        todos con el mismo `pago_multiple_id`, en UNA sola transacción — si cualquiera
        falla (factura inexistente, o la suma excede `monto_total_pago`), no se guarda
        ninguno. El backend NO topa el monto de cada renglón contra el pendiente de SU
        factura individual (igual que el pago sencillo, `crear()`, nunca lo hizo): un
        "pago de más" sobre una factura puntual sigue siendo tolerado a nivel de dominio
        (`recalcular_tras_pago` la deja `cobrada` igual, ver `test_borrar_un_pago_extra_
        sobre_una_ya_cobrada_si_se_permite`) — ADR-227 agrega esa restricción solo en el
        FRONTEND de pago múltiple (petición del usuario: bloquear el guardado si algún
        renglón excede su pendiente), no aquí.

        ADR-270 (petición del usuario) — `suma_asignada` incluye el `ajuste` de cada
        renglón; debe cuadrar EXACTO contra `monto_total_pago` (usando la columna de
        Ajuste para cerrar diferencias chicas, hasta ±$10 por renglón).

        ADR-273 (petición del usuario, "Correcciones en pagos múltiples — parte 2"): a
        diferencia de ADR-230 (retirado de este método), una `suma_asignada` por debajo
        de `monto_total_pago` YA NO genera un `PagoCliente` huérfano con el sobrante —
        se rechaza siempre, sin importar qué tan grande sea la diferencia. Si
        `data.pago_origen_id` viene (se está REPARTIENDO un huérfano ya existente), debe
        cubrirse su monto COMPLETO: ya no puede dejar un sobrante más chico. El
        mecanismo de huérfano (`cobranza_id=None`) sigue vivo para otros flujos
        (`/pagos/no-asignados`, `/asignar`, ADR-229/231) — solo se quitó de AQUÍ."""
        from app.modules.usuarios.lookup import resolver_usuario_id

        db = self._repo.db
        self._validar_cuenta_contable(data.cuenta_contable_id)

        ids_vistos: set[uuid.UUID] = set()
        for item in data.pagos:
            if item.cobranza_id in ids_vistos:
                raise DomainError(
                    "La misma factura no puede aparecer dos veces en un solo pago múltiple.",
                    detalles={"cobranza_id": str(item.cobranza_id)},
                )
            ids_vistos.add(item.cobranza_id)

        suma_asignada = sum(
            (item.monto_aplicado + item.ajuste for item in data.pagos), Decimal("0")
        )
        if suma_asignada > data.monto_total_pago:
            raise DomainError(
                "La suma de los montos asignados (incluyendo ajustes) no puede exceder "
                "el monto total del pago.",
                detalles={
                    "monto_total_pago": str(data.monto_total_pago),
                    "suma_asignada": str(suma_asignada),
                },
            )
        # ADR-273 (petición del usuario): CUALQUIER diferencia por debajo del total se
        # rechaza — ya no hay un umbral de $10 a partir del cual se tolere como "pago de
        # menos" (ese huérfano de ADR-230 se quitó de este método, ver docstring).
        diferencia = (data.monto_total_pago - suma_asignada).quantize(CENTAVOS)
        if diferencia > Decimal("0"):
            raise DomainError(
                "El pago no cuadra exacto contra el monto capturado: falta "
                f"{diferencia}. Selecciona más facturas, sube los montos aplicados, o "
                f"usa la columna de Ajuste (hasta ±{_ADR270_TOLERANCIA} por factura) "
                "para cuadrar exacto.",
                detalles={
                    "monto_total_pago": str(data.monto_total_pago),
                    "suma_asignada": str(suma_asignada),
                    "diferencia": str(diferencia),
                },
            )

        origen: PagoCliente | None = None
        if data.pago_origen_id is not None:
            origen = db.get(PagoCliente, data.pago_origen_id)
            if origen is None:
                raise NotFoundError(
                    "PagoCliente no encontrado.",
                    detalles={"pago_cliente_id": str(data.pago_origen_id)},
                )
            if origen.cobranza_id is not None:
                raise ConflictError(
                    "Este pago ya está asignado a una factura; no se puede repartir.",
                    detalles={"pago_cliente_id": str(data.pago_origen_id)},
                )

        servicio_cobranza = CobranzaFacturaService(CobranzaFacturaRepository(db, CobranzaFactura))
        pago_multiple_id = uuid4()
        creado_por = resolver_usuario_id(db, usuario.username)
        # ADR-227/230: `numero_pago` y `pago_origen_id` NO van aquí — el primero es por
        # renglón (`item.numero_pago`); el segundo no es columna de `PagoCliente`.
        comunes = data.model_dump(exclude={"pagos", "monto_total_pago", "pago_origen_id"})

        pagos_creados: list[PagoCliente] = []
        try:
            if origen is not None:
                db.delete(origen)

            for item in data.pagos:
                cobranza = self._get_cobranza_or_404(item.cobranza_id)

                pago = PagoCliente(
                    pago_cliente_id=uuid4(),
                    cobranza_id=item.cobranza_id,
                    monto_aplicado=item.monto_aplicado,
                    ajuste=item.ajuste,
                    numero_pago=item.numero_pago,
                    pago_multiple_id=pago_multiple_id,
                    created_by=creado_por,
                    **comunes,
                )
                db.add(pago)
                db.flush()  # el recálculo del SIGUIENTE renglón debe ver este ya insertado
                servicio_cobranza.recalcular_tras_pago(cobranza, usuario)
                pagos_creados.append(pago)
        except Exception:
            # Todo o nada: si CUALQUIER renglón falla (factura inexistente, etc.), se
            # deshacen los que ya se habían insertado en este mismo lote — no depender
            # de que el request termine para que se revierta (ver ADR-225).
            db.rollback()
            raise

        db.commit()
        for pago in pagos_creados:
            db.refresh(pago)
        return [PagoClienteRead.model_validate(p) for p in pagos_creados]

    def eliminar(self, pago_id: uuid.UUID, usuario: CurrentUser) -> None:
        """Borra FÍSICAMENTE un pago SIN ASIGNAR (ADR-229) — nunca tocó ninguna
        factura, así que no hay nada que recalcular ni ningún guardarraíl que aplicar.

        ADR-271 (petición del usuario, "Cancelación de Pago"): un pago YA ASIGNADO ya
        NO se puede borrar por aquí — se RECHAZA con 400. La única forma de quitarle
        efecto a un pago aplicado es `cancelar()` (baja lógica, ver docstring del
        módulo), para que quede visible en el historial con su estatus en vez de
        desaparecer sin rastro.
        """
        db = self._repo.db
        pago = db.get(PagoCliente, pago_id)
        if pago is None:
            raise NotFoundError(
                "PagoCliente no encontrado.", detalles={"pago_cliente_id": str(pago_id)}
            )

        if pago.cobranza_id is not None:
            raise DomainError(
                "Este pago ya está asignado a una factura: no se puede eliminar, solo "
                "cancelar (botón 'Cancelación de Pago' en Pagos recibidos).",
                detalles={
                    "pago_cliente_id": str(pago_id),
                    "cobranza_id": str(pago.cobranza_id),
                },
            )

        db.delete(pago)
        db.commit()

    def _resolver_grupo(self, pago_id: uuid.UUID) -> list[PagoCliente]:
        """ADR-271: dado el id de CUALQUIER fila que pertenezca a un pago (individual o
        múltiple), regresa TODAS las filas que forman ese mismo pago "global" — si tiene
        `pago_multiple_id`, todas las que lo comparten (incluido el "huérfano" sin
        asignar, si existe); si no, solo ella misma."""
        pago = self._repo.db.get(PagoCliente, pago_id)
        if pago is None:
            raise NotFoundError(
                "PagoCliente no encontrado.", detalles={"pago_cliente_id": str(pago_id)}
            )
        if pago.pago_multiple_id is None:
            return [pago]
        return list(
            self._repo.db.scalars(
                select(PagoCliente).where(PagoCliente.pago_multiple_id == pago.pago_multiple_id)
            ).all()
        )

    def listar_agrupado(self) -> list[PagoGrupoRead]:
        """ADR-271 — "Pagos recibidos" agrupado: una fila por pago GLOBAL, no una por
        factura aplicada (ver `PagoGrupoRead`). Sin paginar, como el historial que
        reemplaza (límite informal de 100 que ya comparte el resto del módulo) — se
        revisita si el volumen lo exige."""
        grupo_id = func.coalesce(PagoCliente.pago_multiple_id, PagoCliente.pago_cliente_id)
        filas = self._repo.db.execute(
            select(
                grupo_id.label("grupo_id"),
                func.min(PagoCliente.pago_cliente_id).label("pago_cliente_id"),
                func.max(PagoCliente.pago_multiple_id).label("pago_multiple_id"),
                func.min(PagoCliente.fecha_pago_cliente).label("fecha_pago_cliente"),
                func.max(PagoCliente.referencia_pago).label("referencia_pago"),
                func.sum(PagoCliente.monto_aplicado + PagoCliente.ajuste).label("monto_pago"),
                func.count(func.distinct(PagoCliente.cobranza_id)).label("cantidad_facturas"),
                func.max(PagoCliente.estatus_pago).label("estatus_pago"),
            )
            .group_by(grupo_id)
            .having(func.count(func.distinct(PagoCliente.cobranza_id)) > 0)
            .order_by(func.min(PagoCliente.fecha_pago_cliente).desc())
        ).all()
        return [
            PagoGrupoRead(
                pago_cliente_id=f.pago_cliente_id,
                pago_multiple_id=f.pago_multiple_id,
                fecha_pago_cliente=f.fecha_pago_cliente,
                referencia_pago=f.referencia_pago,
                monto_pago=Decimal(f.monto_pago).quantize(CENTAVOS),
                cantidad_facturas=f.cantidad_facturas,
                estatus_pago=f.estatus_pago,
            )
            for f in filas
        ]

    def detalle_agrupado(self, pago_id: uuid.UUID) -> PagoGrupoDetalleRead:
        """Detalle de un pago global: sus facturas aplicadas + el total real del pago
        (ver docstring de `PagoGrupoDetalleRead`)."""
        grupo = self._resolver_grupo(pago_id)
        servicio_cobranza = CobranzaFacturaService(
            CobranzaFacturaRepository(self._repo.db, CobranzaFactura)
        )
        aplicaciones: list[PagoGrupoAplicacionRead] = []
        for p in grupo:
            if p.cobranza_id is None:
                continue  # el "huérfano" sin asignar no es una factura aplicada
            cobranza = self._get_cobranza_or_404(p.cobranza_id)
            _, numero_factura = servicio_cobranza.datos_factura(cobranza.factura_id)
            aplicaciones.append(
                PagoGrupoAplicacionRead(
                    pago_cliente_id=p.pago_cliente_id,
                    cobranza_id=p.cobranza_id,
                    numero_factura=numero_factura,
                    numero_pago=p.numero_pago,
                    monto_aplicado=p.monto_aplicado,
                )
            )
        total_pago = sum(
            (p.monto_aplicado + p.ajuste for p in grupo), Decimal("0")
        ).quantize(CENTAVOS)
        return PagoGrupoDetalleRead(
            aplicaciones=aplicaciones,
            total_pago=total_pago,
            estatus_pago=grupo[0].estatus_pago,
            motivo_cancelacion=grupo[0].motivo_cancelacion,
        )

    def cancelar(self, pago_id: uuid.UUID, usuario: CurrentUser, motivo: str) -> None:
        """ADR-271 (petición del usuario, "Cancelación de Pago"): cancela TODO el pago
        global de una sola vez (ver `_resolver_grupo`) — NO borra las filas, las marca
        `estatus_pago = CANCELADO` (`importe_cobrado` ya las excluye de la suma).

        ADR-286 (petición del usuario, reemplaza la regla "ciega" de ADR-271): cancelar
        SÍ puede deshacer una factura ya `cobrada` — la cascada completa
        `CobranzaFactura → FacturaCliente → OrdenCliente` se revierte vía
        `CobranzaFacturaService.recalcular_tras_pago` (que detecta la transición hacia
        atrás y llama `FacturaClienteService.revertir_cobro`).

        Fix (petición del usuario, reemplaza el bloqueo "ciego" que dejó ADR-286): que
        alguna orden ya tenga una comisión de agencia/vendedor/afiliado **autorizada o
        pagada** con base en que estaba `cobrada` YA NO bloquea la cancelación. En vez
        de rechazar: si esa comisión está `autorizada` (no pagada), su `Requisicion` se
        CANCELA EN CASCADA (`RequisicionService.transicionar(..., "cancelada", ...)`,
        que a su vez revierte la factura de proveedor a `recibida` y la vacía de
        órdenes — ver docstring de `_revertir_factura_relacionada`); si ya está
        `pagada`, no se toca nada (el dinero ya salió, es irreversible).
        """
        if not motivo.strip():
            raise DomainError("El motivo de cancelación no puede estar vacío.")

        db = self._repo.db
        grupo = self._resolver_grupo(pago_id)

        if any(p.estatus_pago == EstatusPago.CANCELADO.value for p in grupo):
            raise ConflictError(
                "Este pago ya está cancelado.", detalles={"pago_cliente_id": str(pago_id)}
            )

        from app.modules.cobranza.requisicion import (
            EstatusRequisicion,
            Requisicion,
            RequisicionRepository,
            RequisicionService,
            TransicionRequisicionIn,
        )
        from app.modules.facturacion.factura_afiliado import (
            EstatusFacturaProveedor,
        )
        from app.modules.facturacion.factura_cliente import (
            FacturaClienteOrden,
            comisiones_comprometidas_de_orden,
        )

        servicio_cobranza = CobranzaFacturaService(CobranzaFacturaRepository(db, CobranzaFactura))
        cobranzas: dict[uuid.UUID, CobranzaFactura] = {}
        for p in grupo:
            if p.cobranza_id is None:
                continue
            cobranzas.setdefault(p.cobranza_id, self._get_cobranza_or_404(p.cobranza_id))

        ordenes_ids = set(
            db.scalars(
                select(FacturaClienteOrden.orden_id).where(
                    FacturaClienteOrden.factura_id.in_(
                        c.factura_id for c in cobranzas.values()
                    )
                )
            ).all()
        )
        comprometidas = [
            c for orden_id in ordenes_ids for c in comisiones_comprometidas_de_orden(db, orden_id)
        ]

        for p in grupo:
            p.estatus_pago = EstatusPago.CANCELADO.value
            p.motivo_cancelacion = motivo
        db.flush()
        for cobranza in cobranzas.values():
            servicio_cobranza.recalcular_tras_pago(cobranza, usuario)

        # Cascada: por cada factura de proveedor AUTORIZADA (comprometida), si ya tiene
        # una Requisicion `autorizada` ligada, se cancela ESA (lo que de paso revierte
        # la factura a `recibida`, vacía — ver `_revertir_factura_relacionada`); si
        # todavía no tiene ninguna Requisicion (autorizada "a secas", antes de llegar a
        # generar la requisición), se revierte la factura DIRECTO. Las `pagada` no se
        # tocan (el dinero ya salió). Un `factura_*_id` puede repetirse si varias
        # órdenes comparten la misma factura de proveedor — se dedup antes de resolver.
        servicio_requisicion = RequisicionService(RequisicionRepository(db, Requisicion))
        facturas_ya_resueltas: set[uuid.UUID] = set()
        for c in comprometidas:
            if c.factura_id in facturas_ya_resueltas:
                continue
            facturas_ya_resueltas.add(c.factura_id)
            if c.estatus != EstatusFacturaProveedor.AUTORIZADA.value:
                continue  # `pagada`: no se toca
            columna_fk = {
                "agencia": Requisicion.factura_agencia_id,
                "vendedor": Requisicion.factura_vendedor_id,
                "afiliado": Requisicion.factura_afiliado_id,
            }[c.tipo]
            requisicion = db.scalar(select(Requisicion).where(columna_fk == c.factura_id))
            if requisicion is not None:
                servicio_requisicion.transicionar(
                    requisicion.requisicion_id,
                    EstatusRequisicion.CANCELADA.value,
                    TransicionRequisicionIn(
                        estatus=EstatusRequisicion.CANCELADA.value,
                        motivo=f"Cancelado en cascada al cancelar el pago: {motivo}",
                    ),
                    usuario,
                )
            else:
                # Autorizada pero sin Requisicion generada todavía — se revierte la
                # factura directo, no hay nada que cancelar.
                if c.tipo == "agencia":
                    from app.modules.facturacion.factura_agencia import (
                        FacturaAgencia,
                        FacturaAgenciaRepository,
                        FacturaAgenciaService,
                    )

                    FacturaAgenciaService(
                        FacturaAgenciaRepository(db, FacturaAgencia)
                    ).revertir_a_recibida(c.factura_id)
                elif c.tipo == "vendedor":
                    from app.modules.facturacion.factura_vendedor import (
                        FacturaVendedor,
                        FacturaVendedorRepository,
                        FacturaVendedorService,
                    )

                    FacturaVendedorService(
                        FacturaVendedorRepository(db, FacturaVendedor)
                    ).revertir_a_recibida(c.factura_id)
                else:
                    from app.modules.facturacion.factura_afiliado import (
                        FacturaAfiliado,
                        FacturaAfiliadoRepository,
                        FacturaAfiliadoService,
                    )

                    FacturaAfiliadoService(
                        FacturaAfiliadoRepository(db, FacturaAfiliado)
                    ).revertir_a_recibida(c.factura_id)

        db.commit()


def get_pago_cliente_service(db: Session = Depends(get_db)) -> PagoClienteService:
    return PagoClienteService(
        PagoClienteRepository(db, PagoCliente, default_order_by=[PagoCliente.fecha_pago_cliente])
    )


# ADR-277 (petición del usuario): respuesta de "¿este anunciante tiene adeudo
# vencido?" — consumida por Ventas al seleccionar el anunciante en el alta de
# OrdenCliente (alerta) y por `OrdenClienteService` (bloqueo real, ver `orden_cliente.py`).
class AdeudoVencidoRead(BaseModel):
    anunciante_id: uuid.UUID
    tiene_adeudo_vencido: bool
    suma_adeudo_vencido: Decimal


# ── Router ────────────────────────────────────────────────────────────────────
router_cobranza = APIRouter(prefix="/facturas", tags=["cobranza:facturas"])

router_adeudo_anunciante = APIRouter(prefix="/anunciantes", tags=["cobranza:facturas"])


@router_adeudo_anunciante.get(
    "/{anunciante_id}/adeudo-vencido", response_model=AdeudoVencidoRead
)
def obtener_adeudo_vencido(
    anunciante_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: CobranzaFacturaService = Depends(get_cobranza_factura_service),
) -> AdeudoVencidoRead:
    suma = svc.adeudo_vencido(anunciante_id)
    return AdeudoVencidoRead(
        anunciante_id=anunciante_id,
        tiene_adeudo_vencido=suma > 0,
        suma_adeudo_vencido=suma,
    )


@router_cobranza.get("", response_model=Page[CobranzaFacturaRead])
def listar_cobranza_facturas(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    factura_id: uuid.UUID | None = Query(None),
    anunciante_id: uuid.UUID | None = Query(None),
    agencia_id: uuid.UUID | None = Query(None),
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
            agencia_id=agencia_id,
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


@router_pagos_cliente_por_id.post(
    "/multiples", response_model=list[PagoClienteRead], status_code=201
)
def crear_pago_multiple(
    payload: PagoMultipleCreate,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:crear")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> list[PagoClienteRead]:
    """Pago múltiple (ADR-225): registra un `PagoCliente` por cada factura seleccionada
    (del mismo anunciante o agencia), en una sola transacción."""
    return svc.crear_multiple(payload, usuario)


@router_pagos_cliente_por_id.get("", response_model=list[PagoGrupoRead])
def listar_pagos_agrupado(
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> list[PagoGrupoRead]:
    """ADR-271: "Pagos recibidos" agrupado por pago global, no por factura aplicada."""
    return svc.listar_agrupado()


@router_pagos_cliente_por_id.get("/{pago_id}/detalle", response_model=PagoGrupoDetalleRead)
def detalle_pago_agrupado(
    pago_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> PagoGrupoDetalleRead:
    """ADR-271: detalle de un pago global — sus facturas aplicadas + el total real."""
    return svc.detalle_agrupado(pago_id)


@router_pagos_cliente_por_id.post("/{pago_id}/cancelar", status_code=204)
def cancelar_pago_cliente(
    pago_id: uuid.UUID,
    payload: PagoClienteCancelarRequest,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:editar")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> None:
    """ADR-271/286: cancela TODO el pago global (ver `PagoClienteService.cancelar`),
    con motivo obligatorio."""
    svc.cancelar(pago_id, usuario, payload.motivo)


@router_pagos_cliente_por_id.get("/no-asignados", response_model=Page[PagoClienteRead])
def listar_pagos_no_asignados(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:leer")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> Page[PagoClienteRead]:
    """ADR-229 (petición del usuario): pagos recibidos que aún no se asignaron a
    ninguna factura."""
    return svc.list(PagoClienteListParams(page=page, size=size, sin_asignar=True))


@router_pagos_cliente_por_id.post(
    "/no-asignados", response_model=PagoClienteRead, status_code=201
)
def crear_pago_no_asignado(
    payload: PagoClienteCreate,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:crear")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> PagoClienteRead:
    """ADR-229: captura un pago recibido SIN elegir factura todavía — se asigna
    después con `POST /pagos/{pago_id}/asignar`."""
    return svc.crear_sin_asignar(payload, usuario)


@router_pagos_cliente_por_id.post("/{pago_id}/asignar", response_model=PagoClienteRead)
def asignar_pago_cliente(
    pago_id: uuid.UUID,
    payload: PagoAsignarFacturaRequest,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:editar")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> PagoClienteRead:
    """ADR-229/231: asigna una factura a un pago capturado SIN asignar — puede ser
    parcial (ver `PagoClienteService.asignar`)."""
    return svc.asignar(pago_id, payload, usuario)


@router_pagos_cliente_por_id.delete("/{pago_id}", status_code=204)
def eliminar_pago_cliente(
    pago_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("cobranza:editar")),
    svc: PagoClienteService = Depends(get_pago_cliente_service),
) -> None:
    svc.eliminar(pago_id, usuario)
