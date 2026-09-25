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

**ADR-102 (petición del usuario) — Fase 2 del rediseño "Asignar estaciones": tarifa del
catálogo sugerida + auditada:**
- Nueva columna `producto_tarifa` (`ProductoTarifa` del catálogo Tarifa —
  `spot│mencion│control_remoto│patrocinio`, ADR-097): se elige POR ESTACIÓN. NO reusa la
  columna `producto` ya existente en esta tabla: ese campo es la "Campaña" (texto libre
  heredado de `OrdenCliente.producto`), un concepto distinto sin relación con el producto
  de tarifa.
- **`duracion_spot` (ADR-106, corrección de alcance):** originalmente (ADR-102) se
  heredaba SIN cambio de `OrdenCliente.duracion_spot` — decisión revertida a petición
  del usuario tras revisar el flujo en vivo: ahora se captura POR ESTACIÓN, igual que
  `producto_tarifa` (secuencia del formulario: Estación → Producto → Duración → Tarifa).
  La columna ya existía en `OrdenEstacion` (mismo CHECK `20s│30s│60s` del catálogo); el
  cambio es de origen del dato, no de esquema — `OrdenEstacionCreate`/`Update` la aceptan
  como entrada en vez de que el servicio la copie de la OC.
- Al crear/editar, el servicio busca la tarifa ACTIVA que coincide en
  estación+tipo_señal (de `Estacion.tipo_senal`)+duración (capturada en la OE)+producto —
  mismo criterio "sin duplicado activo" de `TarifaPlaza` (ADR-097) — y la usa como
  SUGERENCIA (el frontend la pre-carga en `precio_spot`, editable).
- **Auditoría condicional, NO el mecanismo de "parámetro sensible" de campo (ADR-016):**
  a diferencia de `TarifaPlaza.tarifa_bruta`/`descuento_pct` (que sí exigen
  `field_permissions.verificar`, hoy solo Admin), aquí el "capturista" normal es Ventas —
  igual que `OrdenCliente.actualizar_comisiones`, que por la misma razón tampoco usa el
  placeholder genérico. Se audita en `LogCambioParametro` (`entidad="OrdenEstacion"`,
  `campo="precio_spot"`) **solo si** el `precio_spot` final no coincide con la tarifa
  encontrada — sin candado de permiso: Ventas sigue capturando/editando libre, con
  `motivo_cambio_tarifa` (transitorio, no persiste) obligatorio únicamente en ese caso. Si
  no hay ninguna tarifa activa para la combinación, no hay nada contra qué comparar y no
  se audita nada (mismo comportamiento 100% libre de antes de esta fase).

**ADR-103 (petición del usuario) — Fase 3 del rediseño: "Material a Transmitir"
(audios):** tabla hija nueva `OrdenEstacionAudio` (uno o más archivos de audio por OE,
subidos vía endpoints DEDICADOS `POST`/`GET`/`DELETE .../{id}/audios`, NO por el
`create()`/`update()` genérico — a diferencia de `reporte_programados_ref` que es una
sola referencia que se reemplaza, aquí hay una lista con altas/bajas independientes).
Regla de asignación por defecto: el audio `orden=0` (el primero subido) es el que usa
CUALQUIER día que no tenga su propio override; `OrdenEstacionDia.orden_estacion_audio_id`
(nullable) guarda esa excepción puntual, asignada con `PUT .../dias/{dia_id}/audio` —
otro endpoint dedicado, para no acoplarlo al reemplazo completo de `dias`. Lista blanca
de formatos PROPIA (`EXTENSIONES_AUDIO_ORDENES`: mp3/wav/ogg — ver
`app/integrations/almacenamiento/documentos.py`) y tope de tamaño PROPIO
(`S3_MAX_AUDIO_BYTES`, 15 MB), NINGUNO de los dos comparte constante con los adjuntos de
documentos (ADR-042) para no afectarlos.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Numeric,
    Unicode,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.config import settings
from app.core.db import Base, datetime2, fecha_sql, get_db, hora_sql, texto_largo
from app.core.errors import DomainError, NotFoundError, StateTransitionError
from app.core.security import CurrentUser, requiere_permiso
from app.integrations.almacenamiento import get_almacenamiento
from app.integrations.almacenamiento.documentos import (
    EXTENSIONES_AUDIO_ORDENES,
    content_type_de_extension,
    leer_adjunto,
    leer_adjunto_libre,
)
from app.integrations.almacenamiento.port import AlmacenamientoPort
from app.modules.catalogos.estacion import Estacion
from app.modules.catalogos.tarifa import ProductoTarifa, TarifaPlaza, TarifaRepository
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


# Estados "congelados" para edición (mismo criterio que `FROZEN_STATES_OC` en
# orden_cliente.py): desde 'en_transmision' en adelante ya existen `Verificacion` ligadas
# a los días exactos de esta OE (spec: una por día) — permitir tocar tarifa/días ahí
# arriesgaría dejarlas huérfanas o desalineadas. Antes de eso, la OE no ha dejado ningún
# rastro fuera de sí misma todavía, así que corregirla es seguro.
FROZEN_STATES_OE: frozenset[str] = frozenset(
    {
        EstatusOrdenEstacion.EN_TRANSMISION.value,
        EstatusOrdenEstacion.EN_REVISION.value,
        EstatusOrdenEstacion.CERRADA.value,
        EstatusOrdenEstacion.CANCELADA.value,
    }
)


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
            "duracion_spot IN ('20s', '30s', '60s')",
            name="ck_orden_estacion_duracion_spot",
        ),
        # ADR-102: nullable (filas viejas, sembradas antes de esta fase, no lo tienen);
        # `OrdenEstacionCreate` sí lo exige para las capturas nuevas.
        CheckConstraint(
            "producto_tarifa IS NULL OR producto_tarifa IN "
            "('spot', 'mencion', 'control_remoto', 'patrocinio')",
            name="ck_orden_estacion_producto_tarifa",
        ),
        # ADR-101 (petición del usuario): se quitó el candado que impedía que
        # `precio_spot` superara `OrdenCliente.precio_unitario` — ahora el margen OIR
        # (`porcentaje_participacion_oir`/`importe_oir`/`iva_oir`/`total_oir`) puede ser
        # NEGATIVO cuando eso pasa (la estación cuesta más de lo que se le cobró al
        # cliente). El tope superior de 100% sigue aplicando (matemáticamente no puede
        # superarse con `precio_spot >= 0`). Se revisará más adelante si el negocio
        # quiere limitar el negativo en vez de permitirlo tal cual.
        CheckConstraint(
            "porcentaje_participacion_oir <= 100",
            name="ck_orden_estacion_pct_oir",
        ),
        # Auditoría de migración a RDS: las 8 columnas de dinero de OrdenEstacion no
        # tenían CHECK — omisión de la misma pasada que sí cubrió orden_cliente e
        # incidencia. `precio_spot`/`importe_estacion` y el lado "emisora" nunca son
        # legítimamente negativos; el lado "oir" SÍ puede serlo desde ADR-101 (ver
        # arriba), así que no lleva CHECK de signo.
        CheckConstraint("precio_spot >= 0", name="ck_orden_estacion_precio_spot"),
        # ADR-068: spots que se asignan/transmiten igual que cualquier otro pero no se
        # cobran a la estación — análogo a `cantidad_spots_bonificables` de OrdenCliente
        # (ADR-067), pero a nivel de esta OI. No hay CHECK "<= spots asignados": ese total
        # no es una columna propia (se agrega sobre `OrdenEstacionDia`, tabla hija), así
        # que esa validación vive en el servicio, no en una constraint de una sola tabla.
        CheckConstraint(
            "cantidad_spots_bonificables >= 0", name="ck_orden_estacion_spots_bonificables"
        ),
        CheckConstraint("importe_estacion >= 0", name="ck_orden_estacion_importe_estacion"),
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
    # ADR-102: producto de TARIFA (spot/mención/control remoto/patrocinio), elegido por
    # estación — NO confundir con `producto` de arriba ("Campaña", texto libre heredado
    # de la OC). Nullable: filas sembradas antes de esta fase no lo tienen.
    producto_tarifa: Mapped[str | None] = mapped_column(Unicode(20), default=None)

    estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("estacion.estacion_id", name="fk_orden_estacion_estacion", ondelete="NO ACTION"),
        index=True,
    )
    # Derivado: heredado de Estacion.plaza_id al crear la OE (mismo patrón que ADR-005).
    plaza_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plaza.plaza_id", name="fk_orden_estacion_plaza", ondelete="NO ACTION"),
        index=True,
    )

    # ADR-106: capturada POR ESTACIÓN (ya no heredada de OrdenCliente.duracion_spot —
    # ver docstring del módulo).
    duracion_spot: Mapped[str] = mapped_column(Unicode(10))
    precio_spot: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Spots bonificables de esta OI (ADR-067/ADR-068): se transmiten y cuentan para el
    # balance de spots de la OC igual que cualquier otro, pero no se cobran a la
    # estación. Reducen `importe_estacion` (ver fórmula abajo), no `spots_asignados`.
    cantidad_spots_bonificables: Mapped[int] = mapped_column(default=0)
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


# ── Material a Transmitir: audios (ADR-103) ──────────────────────────────────────
class OrdenEstacionAudio(Base):
    """Un archivo de audio subido para esta OE ("Material a Transmitir"). `orden` (0,
    1, 2...) fija el orden de subida — el `orden=0` es el DEFAULT que usa cualquier día
    sin override propio (ver `OrdenEstacionDia.orden_estacion_audio_id`); si solo hay
    un audio, ese es el de todos los días. Altas/bajas van por endpoints DEDICADOS
    (`POST`/`DELETE /ordenes/estaciones/{id}/audios`), no por el `update()` genérico de
    la OE — a diferencia de `reporte_programados_ref`/`reporte_reales_ref` (una
    referencia que se reemplaza), aquí hay una LISTA con altas/bajas independientes;
    reemplazarla completa en cada EDICIÓN (como sí hace `dias`) invalidaría los
    `orden_estacion_audio_id` que ya hubiera asignados por día.

    ADR-109 (petición del usuario): SÍ se puede sembrar una lista inicial en `create()`
    — desde `OrdenEstacionCreate.audios`, refs ya subidos a S3 en la captura (antes de
    que la OE existiera) vía `POST /ordenes/material-staging`. Esto NO contradice el
    razonamiento de arriba: al crear no hay ningún override por día todavía que se
    pueda invalidar (esos solo existen para una OE que YA tenía días con overrides
    asignados, imposible antes de que la OE misma exista)."""

    __tablename__ = "orden_estacion_audio"
    __table_args__ = (
        UniqueConstraint(
            "orden_estacion_id", "orden", name="uq_orden_estacion_audio_oe_orden"
        ),
    )

    orden_estacion_audio_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # Sin `index=True`: redundante con `uq_orden_estacion_audio_oe_orden` (columna
    # líder) — mismo criterio que `OrdenEstacionDia.orden_estacion_id`, abajo.
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_orden_estacion_audio_orden_estacion",
            ondelete="NO ACTION",
        )
    )
    ref: Mapped[str] = mapped_column(Unicode(500))
    nombre_archivo: Mapped[str] = mapped_column(Unicode(150))
    orden: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


# ── Evidencias de lo Transmitido: audios (ADR-119) ────────────────────────────────
class OrdenEstacionEvidencia(Base):
    """Un archivo de audio subido como evidencia de lo REALMENTE transmitido — captura
    libre en "Capturar Reales" (2.2→2.3), sin relación con `OrdenEstacionAudio`
    ("Material a Transmitir", lo que se IBA a transmitir, capturado antes/durante). Sin
    concepto de "default" ni override por día (a diferencia de `OrdenEstacionAudio`): es
    una lista plana, sin `orden`, ordenada por `created_at`.

    ADR-119 (petición del usuario): reemplaza a `OrdenEstacion.testigos_url`/
    `testigos_ubicacion_alterna` en la pantalla de captura — esas 2 columnas NO se
    eliminan (se preserva cualquier dato ya capturado en RDS), simplemente dejan de
    leerse/escribirse en el flujo normal (`OrdenEstacionRealesIn` ya no las acepta)."""

    __tablename__ = "orden_estacion_evidencia"

    orden_estacion_evidencia_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_orden_estacion_evidencia_orden_estacion",
            ondelete="NO ACTION",
        ),
        index=True,
    )
    ref: Mapped[str] = mapped_column(Unicode(500))
    nombre_archivo: Mapped[str] = mapped_column(Unicode(150))
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


class OrdenEstacionFormatoReal(Base):
    """Un archivo de "Formato de Horarios Reales" — captura libre en "Capturar Reales"
    (2.2→2.3), lista plana como `OrdenEstacionEvidencia` (sin `orden`, ordenada por
    `created_at`), pero acepta CUALQUIER formato (PDF, Excel, TXT, audio...) salvo
    ejecutables/scripts (ADR-123, lista negra — ver `leer_adjunto_libre`)."""

    __tablename__ = "orden_estacion_formato_real"

    orden_estacion_formato_real_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid4
    )
    orden_estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "orden_estacion.orden_estacion_id",
            name="fk_orden_estacion_formato_real_orden_estacion",
            ondelete="NO ACTION",
        ),
        index=True,
    )
    ref: Mapped[str] = mapped_column(Unicode(500))
    nombre_archivo: Mapped[str] = mapped_column(Unicode(150))
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)


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
        # ADR-108/ADR-112: desde que "Horario de transmisión" es un solo valor (no un
        # rango), el frontend manda siempre `hora_inicio == hora_fin` — relajado de `>`
        # a `>=` (antes de ADR-108 sí era un rango de verdad, con `hora_fin` estrictamente
        # posterior).
        CheckConstraint("hora_fin >= hora_inicio", name="ck_orden_estacion_dia_horas"),
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
    # ADR-103: NULL = este día usa el audio DEFAULT (`orden=0` de `OrdenEstacionAudio`,
    # o el único que haya); con valor = este día transmite un audio distinto — "solo
    # las excepciones", mismo criterio que `spots_programados`/`OrdenEstacionRealesIn`.
    orden_estacion_audio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "orden_estacion_audio.orden_estacion_audio_id",
            name="fk_orden_estacion_dia_audio",
            ondelete="NO ACTION",
        ),
        default=None,
    )
    # ADR-104 (petición del usuario) — "Cancelar transmisión": un día puntual se puede
    # cancelar en CUALQUIER momento (sin importar el sub-estado de la OE). `True` implica
    # que ya existe una `Verificacion` con `spots_verificados=0` para este día (creada al
    # cancelar) y una `Incidencia` tipo `spot_no_emitido` — este día queda EXCLUIDO de las
    # sumas que recalculan los importes de la OE y el balance de spots de la OC.
    cancelada: Mapped[bool] = mapped_column(default=False)

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
    producto_tarifa: ProductoTarifa | None = None
    estacion_id: uuid.UUID
    plaza_id: uuid.UUID
    duracion_spot: str
    precio_spot: Decimal
    cantidad_spots_bonificables: int
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
    # ADR-103: NULL = usa el audio DEFAULT de "Material a Transmitir" (ver
    # OrdenEstacionAudioRead.orden == 0, o el único que haya).
    orden_estacion_audio_id: uuid.UUID | None = None
    # ADR-104: `True` = este día ya se canceló (ver `OrdenEstacionService.cancelar_dia`).
    cancelada: bool
    created_at: datetime
    updated_at: datetime | None = None


class OrdenEstacionAudioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden_estacion_audio_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    nombre_archivo: str
    orden: int
    created_at: datetime


class OrdenEstacionEvidenciaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden_estacion_evidencia_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    nombre_archivo: str
    created_at: datetime


class OrdenEstacionFormatoRealRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden_estacion_formato_real_id: uuid.UUID
    orden_estacion_id: uuid.UUID
    nombre_archivo: str
    created_at: datetime


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
    # ADR-111: referencia (`ref`) a uno de los `OrdenEstacionCreate.audios` de ESTA misma
    # solicitud — sustituye el default (`audios[0]`) para este día puntual. Solo tiene
    # sentido en el alta (los audios ni siquiera tienen `orden_estacion_audio_id` real
    # todavía); `None` = usa el default.
    audio_staging_ref: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _valida_horas(self) -> OrdenEstacionDiaCreate:
        # ADR-108: "Horario de transmisión" pasó de ser un rango a un solo valor — el
        # frontend manda SIEMPRE `hora_inicio == hora_fin` (mismo campo, dos columnas del
        # modelo sin cambio de esquema). Antes de ADR-108 se exigía estrictamente mayor
        # (un rango de verdad); ahora solo se rechaza si `hora_fin` queda ANTES.
        if self.hora_fin < self.hora_inicio:
            raise ValueError("hora_fin no puede ser anterior a hora_inicio.")
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


class OrdenEstacionAudioStagedIn(BaseModel):
    """ADR-109: un audio YA subido a S3 (vía `POST /ordenes/material-staging`, ANTES de
    que exista esta OE) — `ref` es la clave que devolvió esa subida. Al crear la OE, el
    servicio crea la fila `OrdenEstacionAudio` real con este `ref`/`nombre_archivo`, en
    el orden en que vienen en la lista (el primero = `orden=0` = default)."""

    ref: str = Field(min_length=1, max_length=500)
    nombre_archivo: str = Field(min_length=1, max_length=150)


class OrdenEstacionCreate(BaseModel):
    orden_id: uuid.UUID
    estacion_id: uuid.UUID
    producto_tarifa: ProductoTarifa
    # ADR-106: capturada por estación (ya no heredada de OrdenCliente.duracion_spot).
    duracion_spot: DuracionSpot
    precio_spot: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    # ADR-068: se valida contra los spots asignados de esta OI en el servicio (esa suma
    # no se conoce a nivel de schema, depende de `dias`).
    cantidad_spots_bonificables: int = Field(default=0, ge=0)
    observaciones_estacion: str | None = Field(default=None, max_length=2000)
    dias: list[OrdenEstacionDiaCreate] = Field(min_length=1)
    # ADR-102: transitorio (NO es columna) — requerido SOLO si `precio_spot` no coincide
    # con la tarifa activa encontrada para (estación, tipo_señal, duración, producto_tarifa).
    motivo_cambio_tarifa: str | None = Field(default=None, max_length=500)
    # ADR-109: "Material a Transmitir" elegido DURANTE la captura (antes de que exista un
    # id real) — ver `OrdenEstacionAudioStagedIn`. Opcional: se puede seguir subiendo
    # material DESPUÉS por el endpoint dedicado de siempre (`POST .../audios`).
    audios: list[OrdenEstacionAudioStagedIn] = Field(default_factory=list)
    # ADR-121: "Reporte del afiliado" ya no se captura en un paso 2.2 separado (que se
    # salta) — se puede adjuntar desde el alta, o corregir después en `update()` mientras
    # la OE siga en 'asignada' (editable). Mismo campo/columna que usaba
    # `OrdenEstacionProgramadosIn`, sin cambio de esquema.
    reporte_programados_ref: str | None = Field(default=None, max_length=500)


class OrdenEstacionUpdate(BaseModel):
    """Corrección de una OE que TODAVÍA no empezó a transmitir (`FROZEN_STATES_OE`).
    Mismos campos que `OrdenEstacionCreate` salvo `orden_id`/`estacion_id` (no se
    reasigna la OE a otra OC ni a otra estación por esta vía — sería, en la práctica,
    otra OE distinta). Todos opcionales: se manda solo lo que se corrige."""

    model_config = ConfigDict(extra="forbid")

    producto_tarifa: ProductoTarifa | None = None
    duracion_spot: DuracionSpot | None = None
    precio_spot: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    cantidad_spots_bonificables: int | None = Field(default=None, ge=0)
    observaciones_estacion: str | None = Field(default=None, max_length=2000)
    dias: list[OrdenEstacionDiaCreate] | None = Field(default=None, min_length=1)
    motivo_cambio_tarifa: str | None = Field(default=None, max_length=500)
    reporte_programados_ref: str | None = Field(default=None, max_length=500)


class OrdenEstacionDiaAudioIn(BaseModel):
    """ADR-103: asigna (o quita, con `null`) el audio de un día PUNTUAL — independiente
    de `dias`/`OrdenEstacionUpdate` a propósito (ver docstring de `OrdenEstacionAudio`:
    un reemplazo completo de `dias` invalidaría estos overrides)."""

    orden_estacion_audio_id: uuid.UUID | None = None


class OrdenEstacionDiaCancelarIn(BaseModel):
    """ADR-104: cancela un día puntual — en CUALQUIER momento, sin importar el
    sub-estado de la OE. `motivo` es obligatorio y queda en la `Incidencia` generada."""

    motivo: str = Field(min_length=1, max_length=500)


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
    sin incidencia).

    ADR-119 (petición del usuario): ya NO acepta `testigos_url`/
    `testigos_ubicacion_alterna` — la pantalla de captura los reemplazó por "Evidencias
    de lo Transmitido" (`OrdenEstacionEvidencia`, endpoints dedicados, mismo patrón que
    "Material a Transmitir"). Las 2 columnas siguen existiendo en `OrdenEstacion`
    (se preserva cualquier dato ya capturado en RDS) — simplemente ya no se escriben
    desde este flujo."""

    dias: list[OrdenEstacionDiaRealIn] = Field(default_factory=list)
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

    def listar_audios(self, orden_estacion_id: uuid.UUID) -> Sequence[OrdenEstacionAudio]:
        stmt = (
            select(OrdenEstacionAudio)
            .where(OrdenEstacionAudio.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionAudio.orden)
        )
        return self.db.scalars(stmt).all()

    def listar_evidencias(self, orden_estacion_id: uuid.UUID) -> Sequence[OrdenEstacionEvidencia]:
        stmt = (
            select(OrdenEstacionEvidencia)
            .where(OrdenEstacionEvidencia.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionEvidencia.created_at)
        )
        return self.db.scalars(stmt).all()

    def listar_formatos_reales(
        self, orden_estacion_id: uuid.UUID
    ) -> Sequence[OrdenEstacionFormatoReal]:
        stmt = (
            select(OrdenEstacionFormatoReal)
            .where(OrdenEstacionFormatoReal.orden_estacion_id == orden_estacion_id)
            .order_by(OrdenEstacionFormatoReal.created_at)
        )
        return self.db.scalars(stmt).all()


# ── Servicio ──────────────────────────────────────────────────────────────────
class OrdenEstacionService(
    BaseService[OrdenEstacion, OrdenEstacionCreate, OrdenEstacionUpdate, OrdenEstacionRead]
):
    """`create` asigna una estación a una OrdenCliente (Ventas). Las transiciones
    2.1→2.2→2.3 (`avanzar_programados`/`avanzar_reales`) son métodos dedicados, no
    `update` genérico: cada una tiene su propia forma de entrada y efectos (generación
    de `Verificacion`/`Incidencia`, cascada de estatus a la OC). `update()` sí existe,
    pero acotado a corregir errores de captura ANTES de transmitir (`FROZEN_STATES_OE`)
    — no es un canal para editar libremente en cualquier momento."""

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

    # ── ADR-103: Material a Transmitir (audios) ──────────────────────────────────────
    def audios(self, orden_estacion_id: uuid.UUID) -> Sequence[OrdenEstacionAudioRead]:
        self._get_or_404(orden_estacion_id)
        return [
            OrdenEstacionAudioRead.model_validate(a)
            for a in self._repo.listar_audios(orden_estacion_id)
        ]

    def agregar_audio(
        self,
        orden_estacion_id: uuid.UUID,
        archivo: UploadFile,
        usuario: CurrentUser,
        almacenamiento: AlmacenamientoPort,
    ) -> OrdenEstacionAudioRead:
        db = self._repo.db
        self._get_or_404(orden_estacion_id)

        contenido, nombre_sano, extension = leer_adjunto(
            archivo,
            max_bytes=settings.s3_max_audio_bytes,
            extensiones_permitidas=EXTENSIONES_AUDIO_ORDENES,
        )
        siguiente_orden = (
            db.scalar(
                select(func.coalesce(func.max(OrdenEstacionAudio.orden), -1)).where(
                    OrdenEstacionAudio.orden_estacion_id == orden_estacion_id
                )
            )
            + 1
        )
        clave = almacenamiento.subir(
            prefijo=f"orden_estacion/audios/{orden_estacion_id}/",
            nombre_archivo=f"{uuid4().hex}_{nombre_sano}",
            contenido=contenido,
            content_type=content_type_de_extension(extension),
        )
        obj = OrdenEstacionAudio(
            orden_estacion_audio_id=uuid4(),
            orden_estacion_id=orden_estacion_id,
            ref=clave,
            nombre_archivo=nombre_sano,
            orden=siguiente_orden,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return OrdenEstacionAudioRead.model_validate(obj)

    def _get_audio_or_404(
        self, db: Session, orden_estacion_id: uuid.UUID, audio_id: uuid.UUID
    ) -> OrdenEstacionAudio:
        obj = db.get(OrdenEstacionAudio, audio_id)
        if obj is None or obj.orden_estacion_id != orden_estacion_id:
            raise NotFoundError(
                "Audio no encontrado para esta orden estación.",
                detalles={"orden_estacion_audio_id": str(audio_id)},
            )
        return obj

    def obtener_audio(
        self, orden_estacion_id: uuid.UUID, audio_id: uuid.UUID
    ) -> OrdenEstacionAudio:
        """Fila cruda (no el schema `Read`): el router la usa para descargar de S3 con
        su `ref`/`nombre_archivo` reales."""
        self._get_or_404(orden_estacion_id)
        return self._get_audio_or_404(self._repo.db, orden_estacion_id, audio_id)

    def eliminar_audio(
        self, orden_estacion_id: uuid.UUID, audio_id: uuid.UUID, usuario: CurrentUser
    ) -> None:
        """El objeto en S3 NO se borra (mismo trade-off aceptado que el resto de los
        adjuntos de Órdenes, ADR-042: "subir uno nuevo simplemente reemplaza la
        referencia", aquí "borrar la fila simplemente deja de referenciarlo"). Los días
        que apuntaban a este audio quedan sin override (vuelven al default)."""
        db = self._repo.db
        self._get_or_404(orden_estacion_id)
        obj = self._get_audio_or_404(db, orden_estacion_id, audio_id)

        db.execute(
            OrdenEstacionDia.__table__.update()
            .where(OrdenEstacionDia.orden_estacion_audio_id == audio_id)
            .values(orden_estacion_audio_id=None)
        )
        orden_eliminado = obj.orden
        db.delete(obj)
        # `flush()` explícito: el DELETE de arriba debe llegar a la base ANTES del
        # UPDATE crudo de abajo — si dos filas compitieran momentáneamente por el mismo
        # `orden` (la que se está borrando y la que se está corriendo hacia atrás),
        # `uq_orden_estacion_audio_oe_orden` lo rechazaría con IntegrityError.
        db.flush()
        # Renumera los que quedan detrás para que "el primero" (orden=0) nunca quede
        # vacío si justo ese era el que se borró — el nuevo orden=0 pasa a ser el
        # default automáticamente.
        db.execute(
            OrdenEstacionAudio.__table__.update()
            .where(
                OrdenEstacionAudio.orden_estacion_id == orden_estacion_id,
                OrdenEstacionAudio.orden > orden_eliminado,
            )
            .values(orden=OrdenEstacionAudio.orden - 1)
        )
        db.commit()

    def asignar_audio_dia(
        self,
        orden_estacion_id: uuid.UUID,
        dia_id: uuid.UUID,
        data: OrdenEstacionDiaAudioIn,
        usuario: CurrentUser,
    ) -> OrdenEstacionDiaRead:
        db = self._repo.db
        self._get_or_404(orden_estacion_id)
        dia = db.get(OrdenEstacionDia, dia_id)
        if dia is None or dia.orden_estacion_id != orden_estacion_id:
            raise NotFoundError(
                "Día no encontrado para esta orden estación.",
                detalles={"orden_estacion_dia_id": str(dia_id)},
            )
        if data.orden_estacion_audio_id is not None:
            self._get_audio_or_404(db, orden_estacion_id, data.orden_estacion_audio_id)

        dia.orden_estacion_audio_id = data.orden_estacion_audio_id
        db.commit()
        db.refresh(dia)
        return OrdenEstacionDiaRead.model_validate(dia)

    # ── ADR-119: Evidencias de lo Transmitido (audios, "Capturar Reales") ────────────
    def evidencias(self, orden_estacion_id: uuid.UUID) -> Sequence[OrdenEstacionEvidenciaRead]:
        self._get_or_404(orden_estacion_id)
        return [
            OrdenEstacionEvidenciaRead.model_validate(e)
            for e in self._repo.listar_evidencias(orden_estacion_id)
        ]

    def agregar_evidencia(
        self,
        orden_estacion_id: uuid.UUID,
        archivo: UploadFile,
        usuario: CurrentUser,
        almacenamiento: AlmacenamientoPort,
    ) -> OrdenEstacionEvidenciaRead:
        db = self._repo.db
        self._get_or_404(orden_estacion_id)

        contenido, nombre_sano, extension = leer_adjunto(
            archivo,
            max_bytes=settings.s3_max_audio_bytes,
            extensiones_permitidas=EXTENSIONES_AUDIO_ORDENES,
        )
        clave = almacenamiento.subir(
            prefijo=f"orden_estacion/evidencias/{orden_estacion_id}/",
            nombre_archivo=f"{uuid4().hex}_{nombre_sano}",
            contenido=contenido,
            content_type=content_type_de_extension(extension),
        )
        obj = OrdenEstacionEvidencia(
            orden_estacion_evidencia_id=uuid4(),
            orden_estacion_id=orden_estacion_id,
            ref=clave,
            nombre_archivo=nombre_sano,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return OrdenEstacionEvidenciaRead.model_validate(obj)

    def _get_evidencia_or_404(
        self, db: Session, orden_estacion_id: uuid.UUID, evidencia_id: uuid.UUID
    ) -> OrdenEstacionEvidencia:
        obj = db.get(OrdenEstacionEvidencia, evidencia_id)
        if obj is None or obj.orden_estacion_id != orden_estacion_id:
            raise NotFoundError(
                "Evidencia no encontrada para esta orden estación.",
                detalles={"orden_estacion_evidencia_id": str(evidencia_id)},
            )
        return obj

    def obtener_evidencia(
        self, orden_estacion_id: uuid.UUID, evidencia_id: uuid.UUID
    ) -> OrdenEstacionEvidencia:
        """Fila cruda (no el schema `Read`): el router la usa para descargar de S3 con
        su `ref`/`nombre_archivo` reales."""
        self._get_or_404(orden_estacion_id)
        return self._get_evidencia_or_404(self._repo.db, orden_estacion_id, evidencia_id)

    def eliminar_evidencia(
        self, orden_estacion_id: uuid.UUID, evidencia_id: uuid.UUID, usuario: CurrentUser
    ) -> None:
        """El objeto en S3 NO se borra (mismo trade-off aceptado que el resto de los
        adjuntos de Órdenes, ADR-042). Sin `orden`/default que renumerar (a diferencia de
        `eliminar_audio`): es una lista plana, borrar una fila no afecta a las demás."""
        db = self._repo.db
        self._get_or_404(orden_estacion_id)
        obj = self._get_evidencia_or_404(db, orden_estacion_id, evidencia_id)
        db.delete(obj)
        db.commit()

    # ── ADR-123: Formato de Horarios Reales (cualquier formato, "Capturar Reales") ──
    def formatos_reales(
        self, orden_estacion_id: uuid.UUID
    ) -> Sequence[OrdenEstacionFormatoRealRead]:
        self._get_or_404(orden_estacion_id)
        return [
            OrdenEstacionFormatoRealRead.model_validate(f)
            for f in self._repo.listar_formatos_reales(orden_estacion_id)
        ]

    def agregar_formato_real(
        self,
        orden_estacion_id: uuid.UUID,
        archivo: UploadFile,
        usuario: CurrentUser,
        almacenamiento: AlmacenamientoPort,
    ) -> OrdenEstacionFormatoRealRead:
        db = self._repo.db
        self._get_or_404(orden_estacion_id)

        contenido, nombre_sano, extension = leer_adjunto_libre(
            archivo, max_bytes=settings.s3_max_formato_real_bytes
        )
        clave = almacenamiento.subir(
            prefijo=f"orden_estacion/formatos_reales/{orden_estacion_id}/",
            nombre_archivo=f"{uuid4().hex}_{nombre_sano}",
            contenido=contenido,
            content_type=content_type_de_extension(extension),
        )
        obj = OrdenEstacionFormatoReal(
            orden_estacion_formato_real_id=uuid4(),
            orden_estacion_id=orden_estacion_id,
            ref=clave,
            nombre_archivo=nombre_sano,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return OrdenEstacionFormatoRealRead.model_validate(obj)

    def _get_formato_real_or_404(
        self, db: Session, orden_estacion_id: uuid.UUID, formato_real_id: uuid.UUID
    ) -> OrdenEstacionFormatoReal:
        obj = db.get(OrdenEstacionFormatoReal, formato_real_id)
        if obj is None or obj.orden_estacion_id != orden_estacion_id:
            raise NotFoundError(
                "Formato de horarios reales no encontrado para esta orden estación.",
                detalles={"orden_estacion_formato_real_id": str(formato_real_id)},
            )
        return obj

    def obtener_formato_real(
        self, orden_estacion_id: uuid.UUID, formato_real_id: uuid.UUID
    ) -> OrdenEstacionFormatoReal:
        """Fila cruda (no el schema `Read`): el router la usa para descargar de S3 con
        su `ref`/`nombre_archivo` reales."""
        self._get_or_404(orden_estacion_id)
        return self._get_formato_real_or_404(self._repo.db, orden_estacion_id, formato_real_id)

    def eliminar_formato_real(
        self, orden_estacion_id: uuid.UUID, formato_real_id: uuid.UUID, usuario: CurrentUser
    ) -> None:
        """El objeto en S3 NO se borra (mismo trade-off aceptado que el resto de los
        adjuntos de Órdenes, ADR-042). Lista plana: borrar una fila no afecta a las demás."""
        db = self._repo.db
        self._get_or_404(orden_estacion_id)
        obj = self._get_formato_real_or_404(db, orden_estacion_id, formato_real_id)
        db.delete(obj)
        db.commit()

    # ── ADR-104: "Cancelar transmisión" de un día puntual ────────────────────────────
    def cancelar_dia(
        self,
        orden_estacion_id: uuid.UUID,
        dia_id: uuid.UUID,
        data: OrdenEstacionDiaCancelarIn,
        usuario: CurrentUser,
    ) -> OrdenEstacionRead:
        """En CUALQUIER momento (sin candado de `estatus`, decisión explícita del
        usuario). Reutiliza el mecanismo YA existente de Verificacion+Incidencia
        (`avanzar_reales`): crea una `Verificacion` con `spots_verificados=0` para este
        día — por eso un día que YA tiene Verificacion (cancelado antes, o ya pasó por el
        flujo normal 2.2→2.3) no se puede volver a cancelar
        (`uq_verificacion_orden_estacion_dia` lo impediría de todos modos). Genera una
        `Incidencia` tipo `spot_no_emitido` (spec: prevista para alta manual, hasta ahora
        sin ningún flujo que la generara) y recalcula los importes de la OE excluyendo
        este día — libera su cupo del balance de spots de la OC."""
        from app.modules.ordenes.incidencia import Incidencia, ResolucionIncidencia, TipoIncidencia
        from app.modules.ordenes.orden_cliente import OrdenCliente
        from app.modules.ordenes.verificacion import Verificacion

        db = self._repo.db
        obj = self._get_or_404(orden_estacion_id)
        dia = db.get(OrdenEstacionDia, dia_id)
        if dia is None or dia.orden_estacion_id != orden_estacion_id:
            raise NotFoundError(
                "Día no encontrado para esta orden estación.",
                detalles={"orden_estacion_dia_id": str(dia_id)},
            )
        if dia.cancelada:
            raise StateTransitionError(
                "Este día ya está cancelado.", detalles={"orden_estacion_dia_id": str(dia_id)}
            )
        ya_verificado = db.scalar(
            select(Verificacion.verificacion_id).where(
                Verificacion.orden_estacion_dia_id == dia_id
            )
        )
        if ya_verificado is not None:
            raise StateTransitionError(
                "Este día ya tiene una verificación registrada — no se puede cancelar.",
                detalles={"orden_estacion_dia_id": str(dia_id)},
            )

        oc = db.get(OrdenCliente, obj.orden_id)
        if oc is None:  # pragma: no cover — la FK de la OE lo garantiza
            raise DomainError("La OrdenCliente de esta orden estación no existe.")

        usuario_id = resolver_usuario_id(db, usuario.username)
        programado_efectivo = (
            dia.spots_programados if dia.spots_programados is not None else dia.spots_asignados
        )

        verificacion = Verificacion(
            verificacion_id=uuid4(),
            orden_estacion_dia_id=dia.orden_estacion_dia_id,
            spots_verificados=0,
            fecha_verificacion=date.today(),
            notas_verificacion=f"Transmisión cancelada: {data.motivo}",
            reconciliada=True,
            created_by=usuario_id,
        )
        db.add(verificacion)
        # Mismo motivo que `avanzar_reales`: sin `relationship()` entre Verificacion e
        # Incidencia, hace falta un flush explícito para que la FK de la Incidencia
        # encuentre la Verificacion ya insertada dentro de la misma transacción.
        db.flush()

        diferencia = 0 - programado_efectivo
        db.add(
            Incidencia(
                incidencia_id=uuid4(),
                verificacion_id=verificacion.verificacion_id,
                orden_estacion_id=obj.orden_estacion_id,
                tipo_incidencia=TipoIncidencia.SPOT_NO_EMITIDO.value,
                spots_ordenados=programado_efectivo,
                spots_ejecutados=0,
                diferencia_spots=diferencia,
                descripcion_incidencia=data.motivo,
                fecha_incidencia=dia.fecha_transmision,
                resolucion=ResolucionIncidencia.PENDIENTE.value,
                monto_ajuste=(Decimal(diferencia) * obj.precio_spot).quantize(CENTAVOS),
            )
        )

        dia.cancelada = True
        db.flush()

        nuevos = (
            db.scalar(
                select(func.coalesce(func.sum(OrdenEstacionDia.spots_asignados), 0)).where(
                    OrdenEstacionDia.orden_estacion_id == orden_estacion_id,
                    OrdenEstacionDia.cancelada == False,  # noqa: E712
                )
            )
            or 0
        )
        if obj.cantidad_spots_bonificables > nuevos:
            raise DomainError(
                "No se puede cancelar: los spots bonificables ya capturados exceden los "
                "spots restantes tras la cancelación. Ajusta los spots bonificables primero.",
                detalles={
                    "spots_restantes": nuevos,
                    "cantidad_spots_bonificables": obj.cantidad_spots_bonificables,
                },
            )

        pct_oir = Decimal("0")
        if oc.precio_unitario > 0:
            pct_oir = (
                (oc.precio_unitario - obj.precio_spot) / oc.precio_unitario * Decimal(100)
            ).quantize(Decimal("0.1"))
        spots_facturables = nuevos - obj.cantidad_spots_bonificables
        importe_estacion = (Decimal(spots_facturables) * obj.precio_spot).quantize(CENTAVOS)
        importe_oir = (importe_estacion * pct_oir / Decimal(100)).quantize(CENTAVOS)
        iva_oir = (importe_oir * IVA_RATE).quantize(CENTAVOS)
        importe_emisora = importe_estacion - importe_oir
        iva_emisora = (importe_emisora * IVA_RATE).quantize(CENTAVOS)

        obj.importe_estacion = importe_estacion
        obj.porcentaje_participacion_oir = pct_oir
        obj.importe_oir = importe_oir
        obj.iva_oir = iva_oir
        obj.total_oir = importe_oir + iva_oir
        obj.importe_emisora = importe_emisora
        obj.iva_emisora = iva_emisora
        obj.total_emisora = importe_emisora + iva_emisora

        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── ADR-102: tarifa sugerida del catálogo + auditoría condicional ────────────────
    def _tarifa_sugerida(
        self, db: Session, *, estacion: Estacion, duracion_spot: str, producto_tarifa: str | None
    ) -> TarifaPlaza | None:
        """Tarifa ACTIVA para (estación, tipo de señal, duración, producto), o `None` si
        no hay ninguna capturada — en ese caso no hay nada contra qué comparar/auditar."""
        if producto_tarifa is None:
            return None
        tarifa_repo = TarifaRepository(db, TarifaPlaza)
        return tarifa_repo.existe_duplicado_activo(
            estacion_id=estacion.estacion_id,
            tipo_senal=estacion.tipo_senal,
            duracion_spot=duracion_spot,
            producto=producto_tarifa,
        )

    def _auditar_precio_spot_si_difiere(
        self,
        db: Session,
        *,
        orden_estacion_id: uuid.UUID,
        tarifa: TarifaPlaza | None,
        precio_spot: Decimal,
        motivo: str | None,
        usuario: CurrentUser,
    ) -> None:
        """`precio_spot` sigue siendo de captura libre (Ventas) — a diferencia del
        parámetro sensible de `TarifaPlaza` (ADR-099, solo Admin), aquí NO hay candado de
        permiso. Se audita en `LogCambioParametro` solo cuando el valor final no coincide
        con la tarifa sugerida, exigiendo `motivo_cambio_tarifa` en ese caso — mismo
        criterio (sin `field_permissions`) que `OrdenClienteService.actualizar_comisiones`."""
        if tarifa is None or precio_spot == tarifa.tarifa_neta:
            return
        if not (motivo and motivo.strip()):
            raise DomainError(
                "Se requiere 'motivo_cambio_tarifa': el precio por spot no coincide con "
                "la tarifa sugerida del catálogo.",
                detalles={
                    "tarifa_sugerida": str(tarifa.tarifa_neta),
                    "precio_spot": str(precio_spot),
                },
            )
        audit.log_cambio_parametro(
            db=db,
            entidad=self.entidad,
            entidad_id=orden_estacion_id,
            campo="precio_spot",
            anterior=tarifa.tarifa_neta,
            nuevo=precio_spot,
            usuario=usuario,
            motivo=motivo,
        )

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
            # `en_verificacion` se alcanza automáticamente en cuanto la ÚLTIMA OE que
            # existe EN ESE MOMENTO cierra (avanzar_reales) — no cuando de verdad ya no
            # queda ningún spot de la OC por asignar. Si esa primera OE no agotó el
            # total_spots de la OC, hay que poder seguir agregando OE para lo que falta;
            # bloquearlo aquí dejaría spots comprados sin ninguna forma de asignarlos.
            # Sigue bloqueado desde `orden_cerrada` en adelante (facturada/cobrada/
            # cancelada): ahí sí es un estado asentado, no un efecto colateral de cuántas
            # OE se crearon antes.
            EstatusOrden.EN_VERIFICACION.value,
        ):
            raise StateTransitionError(
                "Solo se pueden asignar estaciones a una orden en 'capturada', "
                "'en_transmision' o 'en_verificacion'.",
                detalles={"estatus_orden": oc.estatus_orden},
            )
        estacion = db.get(Estacion, data.estacion_id)
        if estacion is None:
            raise NotFoundError("Estacion no encontrada.", detalles={"id": str(data.estacion_id)})

        refs_staging = {a.ref for a in data.audios}
        for dia in data.dias:
            if not (oc.fecha_inicio_campania <= dia.fecha_transmision <= oc.fecha_fin_campania):
                raise DomainError(
                    "Hay días fuera del rango de campaña de la orden.",
                    detalles={
                        "fecha": str(dia.fecha_transmision),
                        "campania": [str(oc.fecha_inicio_campania), str(oc.fecha_fin_campania)],
                    },
                )
            if dia.audio_staging_ref is not None and dia.audio_staging_ref not in refs_staging:
                raise DomainError(
                    "audio_staging_ref no corresponde a ninguno de los audios de esta solicitud.",
                    detalles={"audio_staging_ref": dia.audio_staging_ref},
                )

        hermanas_ids = db.scalars(
            select(OrdenEstacion.orden_estacion_id).where(OrdenEstacion.orden_id == oc.orden_id)
        ).all()
        asignados_previos = 0
        if hermanas_ids:
            asignados_previos = (
                db.scalar(
                    select(func.coalesce(func.sum(OrdenEstacionDia.spots_asignados), 0)).where(
                        OrdenEstacionDia.orden_estacion_id.in_(hermanas_ids),
                        # ADR-104: un día cancelado libera su cupo — no cuenta contra el
                        # balance de spots de la OC para futuras asignaciones.
                        OrdenEstacionDia.cancelada == False,  # noqa: E712
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
        # ADR-068: los bonificables siguen contando como asignados para el balance de
        # arriba (spec: se transmiten igual) — solo dejan de cobrarse, más abajo.
        if data.cantidad_spots_bonificables > nuevos:
            raise DomainError(
                "Los spots bonificables no pueden exceder los spots asignados de esta "
                "orden estación.",
                detalles={
                    "spots_asignados": nuevos,
                    "cantidad_spots_bonificables": data.cantidad_spots_bonificables,
                },
            )

        # % de participación OIR: CALCULADO (ya no lo captura el formulario, ver plan de
        # la Tanda 5) = (precio_unitario_OC − precio_spot) / precio_unitario_OC × 100.
        pct_oir = Decimal("0")
        if oc.precio_unitario > 0:
            pct_oir = (
                (oc.precio_unitario - data.precio_spot) / oc.precio_unitario * Decimal(100)
            ).quantize(Decimal("0.1"))

        spots_facturables = nuevos - data.cantidad_spots_bonificables
        importe_estacion = (Decimal(spots_facturables) * data.precio_spot).quantize(CENTAVOS)
        importe_oir = (importe_estacion * pct_oir / Decimal(100)).quantize(CENTAVOS)
        iva_oir = (importe_oir * IVA_RATE).quantize(CENTAVOS)
        importe_emisora = importe_estacion - importe_oir
        iva_emisora = (importe_emisora * IVA_RATE).quantize(CENTAVOS)

        letra = chr(65 + len(hermanas_ids))
        folio = oc.folio_orden.replace("OC-", "OE-") + letra

        # ADR-102: tarifa sugerida del catálogo para esta combinación — auditoría
        # condicional (sin candado de permiso) si `precio_spot` no coincide.
        orden_estacion_id = uuid4()
        tarifa = self._tarifa_sugerida(
            db,
            estacion=estacion,
            duracion_spot=data.duracion_spot,
            producto_tarifa=data.producto_tarifa,
        )
        self._auditar_precio_spot_si_difiere(
            db,
            orden_estacion_id=orden_estacion_id,
            tarifa=tarifa,
            precio_spot=data.precio_spot,
            motivo=data.motivo_cambio_tarifa,
            usuario=usuario,
        )

        obj = OrdenEstacion(
            orden_estacion_id=orden_estacion_id,
            folio_orden_estacion=folio,
            orden_id=oc.orden_id,
            contrato_id=oc.contrato_id,
            anunciante_id=oc.anunciante_id,
            vendedor_id=oc.vendedor_principal_id,
            agencia_id=oc.agencia_id,
            categoria_id=oc.categoria_id,
            producto=oc.producto,
            producto_tarifa=data.producto_tarifa,
            estacion_id=estacion.estacion_id,
            plaza_id=estacion.plaza_id,
            duracion_spot=data.duracion_spot,
            precio_spot=data.precio_spot,
            cantidad_spots_bonificables=data.cantidad_spots_bonificables,
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
            reporte_programados_ref=data.reporte_programados_ref,
            created_by=resolver_usuario_id(db, usuario.username),
        )
        db.add(obj)

        # ADR-109: material a transmitir sembrado durante la captura (ya subido a S3
        # vía /material-staging, antes de que esta OE existiera) — se crean las filas
        # reales en el mismo orden en que llegaron (el primero = orden=0 = default).
        # Se crean ANTES que los días (ADR-111) para poder resolver
        # `audio_staging_ref` → `orden_estacion_audio_id` real al armar cada día.
        ref_a_audio_id: dict[str, uuid.UUID] = {}
        for indice, audio in enumerate(data.audios):
            audio_id = uuid4()
            ref_a_audio_id[audio.ref] = audio_id
            db.add(
                OrdenEstacionAudio(
                    orden_estacion_audio_id=audio_id,
                    orden_estacion_id=obj.orden_estacion_id,
                    ref=audio.ref,
                    nombre_archivo=audio.nombre_archivo,
                    orden=indice,
                )
            )
        # `flush()` explícito: sin `relationship()` declarada entre ambos modelos, el
        # unit-of-work no garantiza que el INSERT de `orden_estacion_audio` preceda al
        # de `orden_estacion_dia` (que la referencia por FK) dentro del mismo flush.
        db.flush()

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
                    orden_estacion_audio_id=(
                        ref_a_audio_id.get(dia.audio_staging_ref)
                        if dia.audio_staging_ref
                        else None
                    ),
                )
            )
        if oc.estatus_orden == EstatusOrden.CAPTURADA.value:
            oc.estatus_orden = EstatusOrden.EN_TRANSMISION.value

        db.commit()
        db.refresh(obj)
        return self._to_read(obj)

    # ── edición (corrección de errores de captura, antes de transmitir) ────────────
    def update(
        self, orden_estacion_id: uuid.UUID, data: OrdenEstacionUpdate, usuario: CurrentUser
    ) -> OrdenEstacionRead:
        """Revalida TODO lo que ya valida `create()` (días dentro de la campaña, balance
        de spots de la OC) y recalcula % OIR e importes — en la práctica es lo mismo que
        un alta nueva, porque hasta 'asignada' la OE no ha dejado ningún rastro fuera de
        sí misma. 409 si ya está en `FROZEN_STATES_OE`."""
        from app.modules.ordenes.orden_cliente import OrdenCliente

        db = self._repo.db
        obj = self._get_or_404(orden_estacion_id)
        if obj.estatus in FROZEN_STATES_OE:
            raise StateTransitionError(
                f"No se puede editar una orden estación en estado '{obj.estatus}'.",
                detalles={"estatus": obj.estatus},
            )
        oc = db.get(OrdenCliente, obj.orden_id)
        if oc is None:  # pragma: no cover — la FK de la OE lo garantiza
            raise DomainError("La OrdenCliente de esta orden estación no existe.")

        campos = data.model_fields_set
        precio_spot = data.precio_spot if "precio_spot" in campos else obj.precio_spot

        dias_nuevos = data.dias if "dias" in campos else None
        # ADR-104: un día cancelado tiene una Verificacion/Incidencia enganchada — no se
        # puede borrar/recrear (violaría la FK). El reemplazo completo de `dias` de abajo
        # los deja INTACTOS: se filtran tanto de lo que se borra como de lo que llega en
        # el payload (el frontend puede seguir mandándolos de vuelta sin que se dupliquen).
        fechas_canceladas = {
            d.fecha_transmision
            for d in self._repo.listar_dias(obj.orden_estacion_id)
            if d.cancelada
        }
        if dias_nuevos is not None:
            dias_nuevos = [d for d in dias_nuevos if d.fecha_transmision not in fechas_canceladas]
            for dia in dias_nuevos:
                if not (oc.fecha_inicio_campania <= dia.fecha_transmision <= oc.fecha_fin_campania):
                    raise DomainError(
                        "Hay días fuera del rango de campaña de la orden.",
                        detalles={
                            "fecha": str(dia.fecha_transmision),
                            "campania": [str(oc.fecha_inicio_campania), str(oc.fecha_fin_campania)],
                        },
                    )
            nuevos = sum(d.spots_asignados for d in dias_nuevos)
        else:
            nuevos = (
                db.scalar(
                    select(func.coalesce(func.sum(OrdenEstacionDia.spots_asignados), 0)).where(
                        OrdenEstacionDia.orden_estacion_id == obj.orden_estacion_id,
                        # ADR-104: un día cancelado ya no cuenta para los importes de
                        # esta misma OE.
                        OrdenEstacionDia.cancelada == False,  # noqa: E712
                    )
                )
                or 0
            )

        # Balance de spots de la OC: las OE HERMANAS, sin contar esta misma (que se está
        # recalculando aparte, con `nuevos`).
        hermanas_ids = db.scalars(
            select(OrdenEstacion.orden_estacion_id).where(
                OrdenEstacion.orden_id == oc.orden_id,
                OrdenEstacion.orden_estacion_id != obj.orden_estacion_id,
            )
        ).all()
        asignados_otras = 0
        if hermanas_ids:
            asignados_otras = (
                db.scalar(
                    select(func.coalesce(func.sum(OrdenEstacionDia.spots_asignados), 0)).where(
                        OrdenEstacionDia.orden_estacion_id.in_(hermanas_ids),
                        OrdenEstacionDia.cancelada == False,  # noqa: E712
                    )
                )
                or 0
            )
        if asignados_otras + nuevos > oc.total_spots:
            raise DomainError(
                "Excede el total de spots de la orden.",
                detalles={
                    "total_oc": oc.total_spots,
                    "otras_oe": asignados_otras,
                    "nuevos": nuevos,
                },
            )

        cantidad_spots_bonificables = (
            data.cantidad_spots_bonificables
            if "cantidad_spots_bonificables" in campos
            else obj.cantidad_spots_bonificables
        )
        if cantidad_spots_bonificables > nuevos:
            raise DomainError(
                "Los spots bonificables no pueden exceder los spots asignados de esta "
                "orden estación.",
                detalles={
                    "spots_asignados": nuevos,
                    "cantidad_spots_bonificables": cantidad_spots_bonificables,
                },
            )

        pct_oir = Decimal("0")
        if oc.precio_unitario > 0:
            pct_oir = (
                (oc.precio_unitario - precio_spot) / oc.precio_unitario * Decimal(100)
            ).quantize(Decimal("0.1"))
        spots_facturables = nuevos - cantidad_spots_bonificables
        importe_estacion = (Decimal(spots_facturables) * precio_spot).quantize(CENTAVOS)
        importe_oir = (importe_estacion * pct_oir / Decimal(100)).quantize(CENTAVOS)
        iva_oir = (importe_oir * IVA_RATE).quantize(CENTAVOS)
        importe_emisora = importe_estacion - importe_oir
        iva_emisora = (importe_emisora * IVA_RATE).quantize(CENTAVOS)

        # ADR-102: tarifa sugerida del catálogo — auditoría condicional (sin candado de
        # permiso) si el `precio_spot` efectivo no coincide.
        producto_tarifa = (
            data.producto_tarifa if "producto_tarifa" in campos else obj.producto_tarifa
        )
        duracion_spot = data.duracion_spot if "duracion_spot" in campos else obj.duracion_spot
        estacion = db.get(Estacion, obj.estacion_id)
        tarifa = self._tarifa_sugerida(
            db,
            estacion=estacion,
            duracion_spot=duracion_spot,
            producto_tarifa=producto_tarifa,
        )
        self._auditar_precio_spot_si_difiere(
            db,
            orden_estacion_id=obj.orden_estacion_id,
            tarifa=tarifa,
            precio_spot=precio_spot,
            motivo=data.motivo_cambio_tarifa,
            usuario=usuario,
        )

        obj.producto_tarifa = producto_tarifa
        obj.duracion_spot = duracion_spot
        obj.precio_spot = precio_spot
        obj.cantidad_spots_bonificables = cantidad_spots_bonificables
        obj.importe_estacion = importe_estacion
        obj.porcentaje_participacion_oir = pct_oir
        obj.importe_oir = importe_oir
        obj.iva_oir = iva_oir
        obj.total_oir = importe_oir + iva_oir
        obj.importe_emisora = importe_emisora
        obj.iva_emisora = iva_emisora
        obj.total_emisora = importe_emisora + iva_emisora
        if "observaciones_estacion" in campos:
            obj.observaciones_estacion = data.observaciones_estacion
        if "reporte_programados_ref" in campos:
            obj.reporte_programados_ref = data.reporte_programados_ref

        if dias_nuevos is not None:
            # Reemplazo completo (mismo criterio que el combo de días al dar de alta):
            # más simple y menos propenso a error que un diff campo por campo contra lo
            # que ya existía, y a estas alturas (antes de transmitir) no hay nada que
            # referencie un `orden_estacion_dia_id` en particular todavía — EXCEPTO los
            # días ya CANCELADOS (ADR-104), que sí tienen una Verificacion enganchada y
            # se excluyen tanto del borrado como de la inserción (ver arriba).
            db.execute(
                delete(OrdenEstacionDia).where(
                    OrdenEstacionDia.orden_estacion_id == obj.orden_estacion_id,
                    OrdenEstacionDia.cancelada == False,  # noqa: E712
                )
            )
            for dia in dias_nuevos:
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
        # ADR-121: "Capturar Programados" (2.2) ya no es un paso manual obligatorio — los
        # datos que capturaba (spots_programados, reporte del afiliado) ya se capturan
        # desde el alta/edición de la OE. Reales ahora se puede avanzar directo desde
        # 'asignada' (flujo nuevo) — 'en_transmision' se conserva como precondición válida
        # por compatibilidad con cualquier OE que sí haya pasado por el endpoint manual
        # de siempre (`avanzar_programados`, que sigue existiendo sin cambios).
        if obj.estatus not in (
            EstatusOrdenEstacion.ASIGNADA.value,
            EstatusOrdenEstacion.EN_TRANSMISION.value,
        ):
            raise StateTransitionError(
                "Solo se puede avanzar a reales desde 'asignada' o 'en_transmision'.",
                detalles={"estatus": obj.estatus},
            )
        db = self._repo.db
        overrides = {d.fecha_transmision: d.spots_verificados for d in input_.dias}
        dias = self._repo.listar_dias(orden_estacion_id)
        usuario_id = resolver_usuario_id(db, usuario.username)
        hoy = date.today()

        for dia in dias:
            # ADR-104: un día cancelado ya tiene su propia Verificacion (creada al
            # cancelar) — `uq_verificacion_orden_estacion_dia` rechazaría una segunda.
            if dia.cancelada:
                continue
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


@router_estaciones.get(
    "/{item_id}/historial-tarifa", response_model=list[audit.LogCambioParametroRead]
)
def historial_tarifa_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> Sequence[audit.LogCambioParametroRead]:
    """Historial de veces que `precio_spot` se apartó de la tarifa sugerida del catálogo
    (ADR-102) — mismo endpoint/formato que `GET /catalogos/tarifas/{id}/historial`."""
    return svc.historial(item_id)


# ── Material a Transmitir: audios (ADR-103) ──────────────────────────────────────
@router_estaciones.get("/{item_id}/audios", response_model=list[OrdenEstacionAudioRead])
def listar_audios_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> Sequence[OrdenEstacionAudioRead]:
    """Audios subidos para esta OE, ordenados (`orden=0` es el default)."""
    return svc.audios(item_id)


@router_estaciones.post("/{item_id}/audios", response_model=OrdenEstacionAudioRead, status_code=201)
def agregar_audio_orden_estacion(
    item_id: uuid.UUID,
    archivo: UploadFile = File(...),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> OrdenEstacionAudioRead:
    """Sube un audio de "Material a Transmitir" (mp3/wav/ogg, ≤ `S3_MAX_AUDIO_BYTES`) y
    lo agrega a la lista de esta OE — 404 si la OE no existe. El primero subido
    (`orden=0`) es el default para los días sin override propio (ADR-103)."""
    return svc.agregar_audio(item_id, archivo, usuario, almacenamiento)


@router_estaciones.get("/{item_id}/audios/{audio_id}/archivo")
def descargar_audio_orden_estacion(
    item_id: uuid.UUID,
    audio_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> Response:
    audio = svc.obtener_audio(item_id, audio_id)
    contenido = almacenamiento.obtener(audio.ref)
    extension = audio.nombre_archivo.rsplit(".", 1)[-1] if "." in audio.nombre_archivo else ""
    return Response(
        content=contenido,
        media_type=content_type_de_extension(extension),
        headers={"Content-Disposition": f'attachment; filename="{audio.nombre_archivo}"'},
    )


@router_estaciones.delete("/{item_id}/audios/{audio_id}", status_code=204)
def eliminar_audio_orden_estacion(
    item_id: uuid.UUID,
    audio_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> None:
    """Quita un audio de la lista (el objeto en S3 no se borra, ver docstring del
    servicio). Cualquier día que lo tuviera asignado vuelve al audio default."""
    svc.eliminar_audio(item_id, audio_id, usuario)


@router_estaciones.put("/{item_id}/dias/{dia_id}/audio", response_model=OrdenEstacionDiaRead)
def asignar_audio_dia_orden_estacion(
    item_id: uuid.UUID,
    dia_id: uuid.UUID,
    payload: OrdenEstacionDiaAudioIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionDiaRead:
    """Asigna (o quita, con `orden_estacion_audio_id: null`) el audio de UN día puntual
    — independiente de `dias`/`PUT /{item_id}` (ver docstring de `OrdenEstacionAudio`)."""
    return svc.asignar_audio_dia(item_id, dia_id, payload, usuario)


@router_estaciones.get(
    "/{item_id}/evidencias", response_model=list[OrdenEstacionEvidenciaRead]
)
def listar_evidencias_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> Sequence[OrdenEstacionEvidenciaRead]:
    """Evidencias de lo REALMENTE transmitido para esta OE (ADR-119) — lista plana, sin
    orden ni default (a diferencia de "Material a Transmitir")."""
    return svc.evidencias(item_id)


@router_estaciones.post(
    "/{item_id}/evidencias", response_model=OrdenEstacionEvidenciaRead, status_code=201
)
def agregar_evidencia_orden_estacion(
    item_id: uuid.UUID,
    archivo: UploadFile = File(...),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> OrdenEstacionEvidenciaRead:
    """Sube una evidencia de lo transmitido (mp3/wav/ogg, ≤ `S3_MAX_AUDIO_BYTES`) y la
    agrega a la lista de esta OE — 404 si la OE no existe."""
    return svc.agregar_evidencia(item_id, archivo, usuario, almacenamiento)


@router_estaciones.get("/{item_id}/evidencias/{evidencia_id}/archivo")
def descargar_evidencia_orden_estacion(
    item_id: uuid.UUID,
    evidencia_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> Response:
    evidencia = svc.obtener_evidencia(item_id, evidencia_id)
    contenido = almacenamiento.obtener(evidencia.ref)
    extension = (
        evidencia.nombre_archivo.rsplit(".", 1)[-1] if "." in evidencia.nombre_archivo else ""
    )
    return Response(
        content=contenido,
        media_type=content_type_de_extension(extension),
        headers={"Content-Disposition": f'attachment; filename="{evidencia.nombre_archivo}"'},
    )


@router_estaciones.delete("/{item_id}/evidencias/{evidencia_id}", status_code=204)
def eliminar_evidencia_orden_estacion(
    item_id: uuid.UUID,
    evidencia_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> None:
    """Quita una evidencia de la lista (el objeto en S3 no se borra, ver docstring del
    servicio)."""
    svc.eliminar_evidencia(item_id, evidencia_id, usuario)


@router_estaciones.get(
    "/{item_id}/formatos-reales", response_model=list[OrdenEstacionFormatoRealRead]
)
def listar_formatos_reales_orden_estacion(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> Sequence[OrdenEstacionFormatoRealRead]:
    """"Formato de Horarios Reales" de esta OE (ADR-123) — lista plana, cualquier
    formato salvo ejecutables/scripts."""
    return svc.formatos_reales(item_id)


@router_estaciones.post(
    "/{item_id}/formatos-reales", response_model=OrdenEstacionFormatoRealRead, status_code=201
)
def agregar_formato_real_orden_estacion(
    item_id: uuid.UUID,
    archivo: UploadFile = File(...),
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> OrdenEstacionFormatoRealRead:
    """Sube un archivo de "Formato de Horarios Reales" (cualquier formato salvo
    ejecutables/scripts, ≤ `S3_MAX_FORMATO_REAL_BYTES`) y lo agrega a la lista de esta
    OE — 404 si la OE no existe."""
    return svc.agregar_formato_real(item_id, archivo, usuario, almacenamiento)


@router_estaciones.get("/{item_id}/formatos-reales/{formato_real_id}/archivo")
def descargar_formato_real_orden_estacion(
    item_id: uuid.UUID,
    formato_real_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:leer")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
    almacenamiento: AlmacenamientoPort = Depends(get_almacenamiento),
) -> Response:
    formato_real = svc.obtener_formato_real(item_id, formato_real_id)
    contenido = almacenamiento.obtener(formato_real.ref)
    extension = (
        formato_real.nombre_archivo.rsplit(".", 1)[-1]
        if "." in formato_real.nombre_archivo
        else ""
    )
    return Response(
        content=contenido,
        media_type=content_type_de_extension(extension),
        headers={
            "Content-Disposition": f'attachment; filename="{formato_real.nombre_archivo}"'
        },
    )


@router_estaciones.delete("/{item_id}/formatos-reales/{formato_real_id}", status_code=204)
def eliminar_formato_real_orden_estacion(
    item_id: uuid.UUID,
    formato_real_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> None:
    """Quita un archivo de la lista (el objeto en S3 no se borra, ver docstring del
    servicio)."""
    svc.eliminar_formato_real(item_id, formato_real_id, usuario)


@router_estaciones.post(
    "/{item_id}/dias/{dia_id}/cancelar", response_model=OrdenEstacionRead
)
def cancelar_dia_orden_estacion(
    item_id: uuid.UUID,
    dia_id: uuid.UUID,
    payload: OrdenEstacionDiaCancelarIn,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    """"Cancelar transmisión" de un día puntual (ADR-104) — en cualquier momento, sin
    importar el sub-estado de la OE. Body: `{motivo}` (obligatorio). Genera una
    `Verificacion` (0 spots) + `Incidencia` (`spot_no_emitido`) para ese día y recalcula
    los importes de la OE excluyéndolo. 409 si el día ya está cancelado o ya tiene una
    verificación registrada (ya pasó por el flujo normal 2.2→2.3)."""
    return svc.cancelar_dia(item_id, dia_id, payload, usuario)


# ── Escritura (Tanda 5) ────────────────────────────────────────────────────────
@router_estaciones.post("", response_model=OrdenEstacionRead, status_code=201)
def crear_orden_estacion(
    payload: OrdenEstacionCreate,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:crear")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    """Asigna una estación a una OrdenCliente (Ventas). Hereda de la OC (anunciante,
    vendedor, agencia, categoría, producto, contrato, duración de spot) y de la Estación
    (plaza); calcula % de participación OIR e importes. **ADR-101:** `precio_spot` puede
    superar la tarifa cliente de la OC (el margen OIR se vuelve negativo). **ADR-102:**
    si `precio_spot` no coincide con la tarifa activa del catálogo para
    (estación, tipo_señal, duración, `producto_tarifa`), exige `motivo_cambio_tarifa` y lo
    audita — sin bloquear la captura. 400 si excede el balance de spots de la orden."""
    return svc.create(payload, usuario)


@router_estaciones.put("/{item_id}", response_model=OrdenEstacionRead)
def editar_orden_estacion(
    item_id: uuid.UUID,
    payload: OrdenEstacionUpdate,
    usuario: CurrentUser = Depends(requiere_permiso("ordenes:editar")),
    svc: OrdenEstacionService = Depends(get_orden_estacion_service),
) -> OrdenEstacionRead:
    """Corrige tarifa/días/observaciones de una OE en 'borrador' o 'asignada' (antes de
    transmitir). Revalida como si fuera un alta nueva: días dentro de la campaña, balance
    de spots, tarifa del catálogo (ADR-102, ver `crear_orden_estacion`). 409 si ya avanzó
    a 'en_transmision' o después (`FROZEN_STATES_OE`)."""
    return svc.update(item_id, payload, usuario)


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
