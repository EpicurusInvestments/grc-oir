"""Catálogo TarifaPlaza (F0-02).

Tarifa de referencia por **estación + duración de spot + producto**, con un campo
CALCULADO (`tarifa_neta`). Se sugiere al capturar órdenes (F1). Monta la base de F0-00
(`BaseRepository`/`BaseService`/`build_crud_router`) y añade sus reglas en la capa de
servicio:

- **Campo calculado (spec):** `tarifa_neta = tarifa_bruta * (1 - descuento_pct / 100)`.
  Lo calcula el servicio con `Decimal` y se persiste; NO se acepta en el request (no está
  en los schemas Create/Update).
- **Sin duplicado activo:** para la misma combinación (estación + duracion_spot +
  producto) no puede existir otra tarifa ACTIVA → 409 `conflicto`.
- **`created_by`:** se guarda el username (texto), no FK: la tabla `Usuario` llega en F0-04
  (decisión E-2).

**ADR-158 (petición del usuario):** se elimina `tipo_senal` de `TarifaPlaza` por
completo — es una propiedad de la ESTACIÓN (`Estacion.tipo_senal`, ya existente), no de
la tarifa; mantenerla aquí duplicada permitía capturar un tipo de señal distinto al de
la estación seleccionada (inconsistencia de datos sin ningún beneficio, ya que tanto el
chequeo de "sin duplicado activo" como la sugerencia de tarifa al capturar una OE
(`_tarifa_sugerida`, `orden_estacion.py`) YA filtraban también por `estacion_id` — el
tipo de señal nunca aportaba nada que `estacion_id` no determinara ya por sí solo. La
combinación de unicidad pasa de (estación+tipo_senal+duracion_spot+producto) a
(estación+duracion_spot+producto). En el formulario, la etiqueta "Duración del spot"
pasa a ser simplemente "Duración".

**ADR-166 (petición del usuario):** `producto` y `duracion_spot` dejan de ser los
CHECK/enum cerrados `ProductoTarifa`/`DuracionSpot` y pasan a TEXTO LIBRE — se conectan
al catálogo `DuracionSpotCatalogo` ("Producto Duración", ADR-159/164/165): el formulario
ahora elige "Producto" y "Duración" de ese catálogo en vez de un selector fijo. Regla de
negocio propia de Tarifa (NO del catálogo): el literal `SIN_RESULTADO` ("sin resultado",
el default del catálogo cuando no se captura una duración real) NO es una duración
válida aquí — el servicio lo rechaza con un error de dominio claro, tanto en alta como en
edición, para que no se pueda guardar una tarifa sin una duración real capturada en el
catálogo. Los valores ya existentes (el enum anterior) siguen siendo válidos, solo dejan
de ser los únicos posibles. Pendiente, a propósito, para una petición futura: conectar
también Órdenes (`OrdenEstacionForm.tsx` sigue con su propio selector fijo por ahora) —
mientras tanto, cualquier producto/duración NUEVO capturado solo aquí no será "sugerido"
en Órdenes hasta que esa pantalla también se conecte al catálogo.

**ADR-097 (petición del usuario, reemplaza el diseño original de F0-02/ADR-015):**
- Se elimina `plaza_id` → se reemplaza por `estacion_id` (FK a `Estacion`, ADR-094): la
  pantalla ya no captura "Plaza", captura "Nombre de la emisora". Junto con este cambio,
  la búsqueda derivada de `plaza_nombre`/`plaza_estado` se reemplaza por `estacion_nombre`.
- Se eliminan `vigencia_desde`/`vigencia_hasta` por completo — el negocio ya NO maneja
  tarifas con vigencia. Con ellas se elimina la validación de solapamiento de fechas y el
  filtro derivado Vigentes/Expiradas (y con él, la necesidad de reemplazar la ruta
  `listar` genérica: la búsqueda por JOIN sigue viviendo en `_apply_filters`, pero ya no
  hace falta ningún query param extra, así que el CRUD genérico de `build_crud_router`
  alcanza sin overrides).
- Se agrega `producto` (entidad NUEVA, fuera de la spec BD v2): `spot│mencion│
  control_remoto│patrocinio` — selector justo debajo de la emisora.
- La regla "sin solapamiento" (basada en fechas) se reemplaza por "sin duplicado activo"
  para la misma combinación estación+tipo_senal+duracion_spot+producto (incluida en
  reactivación, mismo criterio que antes). `tipo_senal` se retiró después, ver ADR-158.

**ADR-099 (petición del usuario) — `tarifa_bruta`/`descuento_pct` como PARÁMETROS
SENSIBLES:** cada cambio a estos dos campos se registra en `LogCambioParametro` (usuario,
fecha, valor anterior, valor nuevo), mismo mecanismo que Agencia/Vendedor/Contrato
(`audit.registrar_cambio_sensible`, ADR-016) — permiso por campo (hoy: solo Admin, mismo
placeholder de F0 que el resto) + `motivo_cambio` (transitorio, no es columna) requerido
si el valor efectivamente cambia en una edición. El alta también audita
(`anterior=None`), sin exigir motivo (es la captura inicial). `GET
/catalogos/tarifas/{id}/historial` expone el historial (ADR-021, mismo endpoint que los
demás catálogos con campos sensibles).

Portabilidad SQL Server: las comparaciones booleanas usan `== True` (→ `activo = 1`), nunca
la variante booleana de `.is_` (ver ADR-014).

**ADR-177 (petición del usuario):** se agrega `anunciante_id` (FK a `Anunciante`) — la
llave de "sin duplicado activo" pasa de (estación+duración+producto) a (ANUNCIANTE+
estación+duración+producto); en el formulario, Anunciante es el PRIMER campo, antes de
"Nombre de la emisora". Es obligatorio para TODA tarifa nueva (`TarifaPlazaCreate.
anunciante_id`, sin default) — pero la columna en sí es NULLABLE a nivel de base: las 5
tarifas que ya existían antes de este cambio no tienen (ni se les puede adivinar) un
Anunciante real, así que la migración las desactiva en vez de inventarles uno (quedan
visibles con el filtro "Inactivas"; si hiciera falta reactivar alguna, el `Update` exige
asignarle su Anunciante real primero). La lista ahora se ordena por
Anunciante → Emisora → Producto → Duración (nombres, no IDs — requiere JOIN con
`Anunciante`/`Estacion`). La búsqueda `?q` se extiende para incluir también el nombre del
anunciante (antes solo emisora/notas). La sugerencia de tarifa al capturar una Orden de
Transmisión (`_tarifa_sugerida`, `orden_estacion.py`) también se actualiza para exigir
el mismo Anunciante de la Orden de Servicio — antes de este ADR esa combinación era
válida sin importar el anunciante; ahora, con Anunciante en la llave, una tarifa sin el
anunciante correcto simplemente no es la misma tarifa.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Unicode, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.anunciante import Anunciante
from app.modules.catalogos.duracion_spot_catalogo import SIN_RESULTADO
from app.modules.catalogos.estacion import Estacion
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.schemas import CatalogoReadBase, ListParams, Page

CENTAVOS = Decimal("0.01")

# Parámetros sensibles (ADR-099): cada cambio se registra en LogCambioParametro.
CAMPO_TARIFA_BRUTA = "tarifa_bruta"
CAMPO_DESCUENTO_PCT = "descuento_pct"


def calcular_tarifa_neta(tarifa_bruta: Decimal, descuento_pct: Decimal) -> Decimal:
    """Fórmula de la spec: `neta = bruta * (1 - descuento/100)`, con Decimal a 2 decimales."""
    factor = (Decimal(100) - descuento_pct) / Decimal(100)
    return (tarifa_bruta * factor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


# ── Modelo ──────────────────────────────────────────────────────────────────────
class TarifaPlaza(Base):
    __tablename__ = "tarifa_plaza"
    __table_args__ = (
        CheckConstraint(
            "descuento_pct >= 0 AND descuento_pct <= 100",
            name="ck_tarifa_plaza_descuento_pct",
        ),
        # Acelera el filtrado por combinación y la consulta de "sin duplicado activo".
        # ADR-177: Anunciante se agrega COMO PRIMER campo de la llave.
        Index(
            "ix_tarifa_plaza_combo", "anunciante_id", "estacion_id", "duracion_spot", "producto"
        ),
    )

    tarifa_plaza_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    # ADR-177 (petición del usuario): NULLABLE a nivel de columna — las tarifas
    # capturadas ANTES de este ADR no tienen (ni se les puede adivinar) un Anunciante
    # real; la migración las desactiva en vez de inventarles uno. `TarifaPlazaCreate`
    # SÍ lo exige (sin default) para toda tarifa nueva de aquí en adelante.
    anunciante_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anunciante.anunciante_id"), index=True, default=None
    )
    estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("estacion.estacion_id"), index=True
    )
    # ADR-166 (petición del usuario): texto libre — ya NO los CHECK/enum
    # `DuracionSpot`/`ProductoTarifa`; se capturan eligiendo del catálogo
    # `DuracionSpotCatalogo` ("Producto Duración"). Mismo ancho que ese catálogo (60).
    duracion_spot: Mapped[str] = mapped_column(Unicode(60))
    producto: Mapped[str] = mapped_column(Unicode(60))
    tarifa_bruta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    descuento_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    # Calculado por el servicio (no se acepta del cliente) y persistido.
    tarifa_neta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    notas: Mapped[str | None] = mapped_column(Unicode(500), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    # Username del capturista (texto, no FK: no hay tabla Usuario hasta F0-04). Ver E-2.
    created_by: Mapped[str | None] = mapped_column(Unicode(150), default=None)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class TarifaPlazaCreate(BaseModel):
    # ADR-177: obligatorio (sin default) para toda tarifa nueva — ver nota de la
    # columna en el modelo sobre por qué la columna en sí es nullable.
    anunciante_id: uuid.UUID
    estacion_id: uuid.UUID
    duracion_spot: str = Field(min_length=1, max_length=60)
    producto: str = Field(min_length=1, max_length=60)
    tarifa_bruta: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    descuento_pct: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2
    )
    notas: str | None = Field(default=None, max_length=500)


class TarifaPlazaUpdate(BaseModel):
    # Opcional: omitir = no cambiar (mismo criterio que `estacion_id`). Un registro
    # legado sin Anunciante (ADR-177) puede editarse sin forzar a capturarlo todavía —
    # pero si se reactiva o se cambia cualquier parte de la llave, "sin duplicado
    # activo" sí exige que el valor EFECTIVO (el que quede tras la edición) no sea nulo
    # para poder compararse de forma determinista (ver `_verificar_sin_duplicado_activo`).
    anunciante_id: uuid.UUID | None = None
    estacion_id: uuid.UUID | None = None
    duracion_spot: str | None = Field(default=None, min_length=1, max_length=60)
    producto: str | None = Field(default=None, min_length=1, max_length=60)
    tarifa_bruta: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    descuento_pct: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    notas: str | None = Field(default=None, max_length=500)
    # Transitorio (NO es columna): requerido si se modifica `tarifa_bruta`/`descuento_pct`
    # (ADR-099). El servicio lo consume y lo retira del payload antes de escribir en la BD.
    motivo_cambio: str | None = Field(default=None, max_length=500)


class TarifaListParams(ListParams):
    """`ListParams` + filtros propios (ADR-102, Fase 2 de Órdenes): F1 los usa para
    encontrar la tarifa ACTIVA de una combinación exacta y sugerir `precio_spot` al
    asignar una estación."""

    anunciante_id: uuid.UUID | None = None
    estacion_id: uuid.UUID | None = None
    duracion_spot: str | None = None
    producto: str | None = None


class TarifaPlazaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    tarifa_plaza_id: uuid.UUID
    # ADR-177: `None` solo en las tarifas capturadas ANTES de este ADR (desactivadas
    # por la migración) — toda tarifa nueva siempre lo trae.
    anunciante_id: uuid.UUID | None = None
    estacion_id: uuid.UUID
    duracion_spot: str
    producto: str
    tarifa_bruta: Decimal
    descuento_pct: Decimal
    tarifa_neta: Decimal  # Calculado por el servicio (solo lectura)
    notas: str | None = None
    created_by: str | None = None
    # Derivados (solo lectura; NO se aceptan en Create/Update):
    estacion_nombre: str | None = None  # nombre_estacion de la estación referenciada
    anunciante_nombre: str | None = None  # nombre_comercial del anunciante referenciado

    # Los montos viajan como STRING para preservar la precisión Decimal (decisión E-4).
    @field_serializer("tarifa_bruta", "descuento_pct", "tarifa_neta")
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


# ── Repositorio ───────────────────────────────────────────────────────────────
class TarifaRepository(BaseRepository[TarifaPlaza]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # La base aplica `activo`; `q`/el orden NO (search_columns vacío) porque abarcan
        # campos de ANUNCIANTE/ESTACIÓN además de notas → requieren JOIN.
        stmt = super()._apply_filters(stmt, params)
        # ADR-177: JOIN siempre presente (no solo cuando hay `q`) — hace falta para
        # poder ORDENAR por nombre de Anunciante/Estación (`default_order_by`), no solo
        # para buscar. `outerjoin` en Anunciante: las 5 tarifas legado (ADR-177,
        # `anunciante_id IS NULL`) no deben desaparecer del listado por un INNER JOIN.
        stmt = stmt.outerjoin(
            Anunciante, TarifaPlaza.anunciante_id == Anunciante.anunciante_id
        ).join(Estacion, TarifaPlaza.estacion_id == Estacion.estacion_id)
        q = (getattr(params, "q", None) or "").strip()
        if q:
            patron = f"%{q}%"
            # Coincidencia parcial case-insensitive en cualquiera de los campos.
            # `ilike` es portable a SQL Server (compila a lower(...) LIKE lower(...));
            # `siglas`/`Anunciante.nombre_comercial` (legado) pueden ser NULL y
            # simplemente no coinciden.
            stmt = stmt.where(
                or_(
                    Anunciante.nombre_comercial.ilike(patron),
                    Estacion.nombre_estacion.ilike(patron),
                    Estacion.siglas.ilike(patron),
                    TarifaPlaza.notas.ilike(patron),
                )
            )
        for campo in ("anunciante_id", "estacion_id", "duracion_spot", "producto"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(TarifaPlaza, campo) == valor)
        return stmt

    def existe_duplicado_activo(
        self,
        *,
        anunciante_id: uuid.UUID | None,
        estacion_id: uuid.UUID,
        duracion_spot: str,
        producto: str,
        excluir_id: uuid.UUID | None = None,
    ) -> TarifaPlaza | None:
        """Devuelve la primera tarifa ACTIVA con la misma combinación (ANUNCIANTE +
        estación + duración + producto, ADR-177), o None. `anunciante_id=None` se
        compara con `IS NULL` (SQLAlchemy lo resuelve solo con `==`) — caso de las
        tarifas legado, ver docstring del módulo."""
        stmt = select(TarifaPlaza).where(
            TarifaPlaza.anunciante_id == anunciante_id,
            TarifaPlaza.estacion_id == estacion_id,
            TarifaPlaza.duracion_spot == duracion_spot,
            TarifaPlaza.producto == producto,
            TarifaPlaza.activo == True,  # noqa: E712  (portable a SQL Server; ver ADR-014)
        )
        if excluir_id is not None:
            stmt = stmt.where(TarifaPlaza.tarifa_plaza_id != excluir_id)
        return self.db.scalars(stmt).first()

    def nombres_de_estaciones(
        self, estacion_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """Nombre de estación por id, en UNA consulta (evita N+1 al enriquecer)."""
        if not estacion_ids:
            return {}
        rows = self.db.execute(
            select(Estacion.estacion_id, Estacion.nombre_estacion).where(
                Estacion.estacion_id.in_(set(estacion_ids))
            )
        ).all()
        return {row[0]: row[1] for row in rows}

    def nombres_de_anunciantes(
        self, anunciante_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """ADR-177: nombre de anunciante por id, en UNA consulta (evita N+1). Los `None`
        (tarifas legado sin anunciante) ya se filtran antes de llamar esto."""
        if not anunciante_ids:
            return {}
        rows = self.db.execute(
            select(Anunciante.anunciante_id, Anunciante.nombre_comercial).where(
                Anunciante.anunciante_id.in_(set(anunciante_ids))
            )
        ).all()
        return {row[0]: row[1] for row in rows}


# ── Servicio ──────────────────────────────────────────────────────────────────
class TarifaService(
    BaseService[TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate, TarifaPlazaRead]
):
    read_schema = TarifaPlazaRead
    entidad = "TarifaPlaza"

    def __init__(
        self,
        repo: TarifaRepository,
        *,
        estacion_repo: BaseRepository[Estacion],
        anunciante_repo: BaseRepository[Anunciante],
    ) -> None:
        super().__init__(repo)
        self._tarifa_repo = repo
        self._estacion_repo = estacion_repo
        self._anunciante_repo = anunciante_repo

    # ── enriquecimiento (estacion_nombre/anunciante_nombre) ─────────────────────
    def _read(
        self, obj: TarifaPlaza, estacion_nombre: str | None, anunciante_nombre: str | None
    ) -> TarifaPlazaRead:
        return TarifaPlazaRead.model_validate(obj).model_copy(
            update={"estacion_nombre": estacion_nombre, "anunciante_nombre": anunciante_nombre}
        )

    def _to_read(self, obj: TarifaPlaza) -> TarifaPlazaRead:
        nombre_estacion = self._tarifa_repo.nombres_de_estaciones([obj.estacion_id]).get(
            obj.estacion_id
        )
        nombre_anunciante = (
            self._tarifa_repo.nombres_de_anunciantes([obj.anunciante_id]).get(obj.anunciante_id)
            if obj.anunciante_id is not None
            else None
        )
        return self._read(obj, nombre_estacion, nombre_anunciante)

    def list(self, params: ListParams) -> Page[TarifaPlazaRead]:
        # Enriquecimiento por LOTE: 3 consultas por página (lista + nombres de estación +
        # nombres de anunciante).
        items, total = self.repo.list(params)
        nombres_estacion = self._tarifa_repo.nombres_de_estaciones([t.estacion_id for t in items])
        nombres_anunciante = self._tarifa_repo.nombres_de_anunciantes(
            [t.anunciante_id for t in items if t.anunciante_id is not None]
        )
        return Page[TarifaPlazaRead](
            items=[
                self._read(
                    t,
                    nombres_estacion.get(t.estacion_id),
                    nombres_anunciante.get(t.anunciante_id) if t.anunciante_id else None,
                )
                for t in items
            ],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    # ── reglas de negocio ────────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_duracion_no_sin_resultado(payload["duracion_spot"])
        self._verificar_anunciante(payload["anunciante_id"])
        self._verificar_estacion(payload["estacion_id"])
        payload["tarifa_neta"] = calcular_tarifa_neta(
            payload["tarifa_bruta"], payload["descuento_pct"]
        )
        payload["created_by"] = usuario.username
        # Una tarifa se crea ACTIVA → siempre se valida el duplicado.
        self._verificar_sin_duplicado_activo(
            anunciante_id=payload["anunciante_id"],
            estacion_id=payload["estacion_id"],
            duracion_spot=payload["duracion_spot"],
            producto=payload["producto"],
            excluir_id=None,
        )
        # PK explícita para poder auditar el ALTA con el id real (anterior=None).
        payload["tarifa_plaza_id"] = uuid4()
        for campo in (CAMPO_TARIFA_BRUTA, CAMPO_DESCUENTO_PCT):
            audit.registrar_cambio_sensible(
                db=self._tarifa_repo.db,
                entidad=self.entidad,
                entidad_id=payload["tarifa_plaza_id"],
                campo=campo,
                anterior=None,
                nuevo=payload[campo],
                usuario=usuario,
                motivo=None,
                requiere_motivo=False,  # en el alta no se exige motivo (captura inicial)
            )

    def _pre_update(self, obj: TarifaPlaza, payload: dict[str, Any], usuario: CurrentUser) -> None:
        motivo = payload.pop("motivo_cambio", None)  # transitorio: nunca llega a la BD

        if "duracion_spot" in payload:
            self._verificar_duracion_no_sin_resultado(payload["duracion_spot"])
        if "anunciante_id" in payload and payload["anunciante_id"] is not None:
            self._verificar_anunciante(payload["anunciante_id"])
        if "estacion_id" in payload:
            self._verificar_estacion(payload["estacion_id"])

        # Valores EFECTIVOS: lo que trae el payload o, si no, el valor actual del registro.
        anunciante_id = payload.get("anunciante_id", obj.anunciante_id)
        estacion_id = payload.get("estacion_id", obj.estacion_id)
        duracion_spot = payload.get("duracion_spot", obj.duracion_spot)
        producto = payload.get("producto", obj.producto)
        bruta = payload.get("tarifa_bruta", obj.tarifa_bruta)
        descuento = payload.get("descuento_pct", obj.descuento_pct)

        # Recalcular siempre la neta a partir de los valores efectivos (nunca del cliente).
        payload["tarifa_neta"] = calcular_tarifa_neta(bruta, descuento)

        # Solo tiene sentido revalidar el duplicado si la tarifa está ACTIVA. ADR-177:
        # una tarifa legado (sin anunciante) que se SIGUE editando mientras está
        # inactiva no se bloquea aquí — pero no puede REACTIVARSE sin anunciante (ver
        # `cambiar_estado`).
        if obj.activo:
            self._verificar_sin_duplicado_activo(
                anunciante_id=anunciante_id,
                estacion_id=estacion_id,
                duracion_spot=duracion_spot,
                producto=producto,
                excluir_id=obj.tarifa_plaza_id,
            )

        # Parámetros sensibles (ADR-099): un registro por campo que de verdad cambió.
        for campo in (CAMPO_TARIFA_BRUTA, CAMPO_DESCUENTO_PCT):
            if campo in payload and payload[campo] != getattr(obj, campo):
                audit.registrar_cambio_sensible(
                    db=self._tarifa_repo.db,
                    entidad=self.entidad,
                    entidad_id=obj.tarifa_plaza_id,
                    campo=campo,
                    anterior=getattr(obj, campo),
                    nuevo=payload[campo],
                    usuario=usuario,
                    motivo=motivo,
                    requiere_motivo=True,
                )

    def cambiar_estado(
        self, id_: Any, activo: bool, usuario: CurrentUser, forzar: bool = False
    ) -> TarifaPlazaRead:
        obj = self._get_or_404(id_)
        # Al REACTIVAR, revalidar el duplicado (otra tarifa pudo tomar esa combinación).
        if activo and not obj.activo:
            # ADR-177: una tarifa legado (de antes de este ADR) no puede reactivarse sin
            # Anunciante — editarla primero para asignárselo.
            if obj.anunciante_id is None:
                raise DomainError(
                    "Esta tarifa no tiene Anunciante capturado (es de antes de este "
                    "campo) — edítala para asignarle uno antes de poder activarla.",
                    detalles={"tarifa_plaza_id": str(obj.tarifa_plaza_id)},
                )
            self._verificar_sin_duplicado_activo(
                anunciante_id=obj.anunciante_id,
                estacion_id=obj.estacion_id,
                duracion_spot=obj.duracion_spot,
                producto=obj.producto,
                excluir_id=obj.tarifa_plaza_id,
            )
        # TarifaPlaza no tiene dependientes: la baja lógica no se bloquea (no usa `forzar`).
        return self._to_read(self.repo.set_activo(obj, activo))

    # ── helpers ──────────────────────────────────────────────────────────────────
    def _verificar_duracion_no_sin_resultado(self, duracion_spot: str) -> None:
        """ADR-166 (petición del usuario): a diferencia del catálogo `DuracionSpotCatalogo`
        (donde SIN_RESULTADO es un default válido, ADR-165), aquí es obligatorio elegir una
        duración REAL — el usuario debe ir al catálogo "Producto Duración" a darla de alta."""
        if duracion_spot.strip().lower() == SIN_RESULTADO:
            raise DomainError(
                "No se puede guardar la tarifa con la duración «sin resultado». Ve al "
                "catálogo Producto Duración y da de alta una duración real para este "
                "producto antes de continuar.",
                detalles={"duracion_spot": duracion_spot},
            )

    def _verificar_estacion(self, estacion_id: uuid.UUID) -> None:
        if self._estacion_repo.get(estacion_id) is None:
            raise NotFoundError(
                "Estación no encontrada para la tarifa.",
                detalles={"estacion_id": str(estacion_id)},
            )

    def _verificar_anunciante(self, anunciante_id: uuid.UUID) -> None:
        if self._anunciante_repo.get(anunciante_id) is None:
            raise NotFoundError(
                "Anunciante no encontrado para la tarifa.",
                detalles={"anunciante_id": str(anunciante_id)},
            )

    def _verificar_sin_duplicado_activo(
        self,
        *,
        anunciante_id: uuid.UUID | None,
        estacion_id: uuid.UUID,
        duracion_spot: str,
        producto: str,
        excluir_id: uuid.UUID | None,
    ) -> None:
        conflicto = self._tarifa_repo.existe_duplicado_activo(
            anunciante_id=anunciante_id,
            estacion_id=estacion_id,
            duracion_spot=duracion_spot,
            producto=producto,
            excluir_id=excluir_id,
        )
        if conflicto is not None:
            raise ConflictError(
                "Ya existe una tarifa activa para este anunciante, estación, "
                "duración y producto.",
                detalles={"tarifa_en_conflicto": str(conflicto.tarifa_plaza_id)},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_tarifa_service(db: Session = Depends(get_db)) -> TarifaService:
    # Sin `search_columns`: la búsqueda `q` se maneja en TarifaRepository._apply_filters con
    # un JOIN a anunciante/estacion (abarca nombre del anunciante, nombre/siglas de la
    # estación, y notas). ADR-177: `default_order_by` ordena por NOMBRE (no por id) —
    # Anunciante → Emisora → Producto → Duración, requiere el mismo JOIN (siempre
    # presente en `_apply_filters`, no solo cuando hay `q`).
    repo = TarifaRepository(
        db,
        TarifaPlaza,
        default_order_by=[
            Anunciante.nombre_comercial,
            Estacion.nombre_estacion,
            TarifaPlaza.producto,
            TarifaPlaza.duracion_spot,
        ],
    )
    return TarifaService(
        repo,
        estacion_repo=BaseRepository(db, Estacion),
        anunciante_repo=BaseRepository(db, Anunciante),
    )


router = build_crud_router(
    prefix="/tarifas",
    tags=["catalogos:tarifas"],
    permiso_base="catalogos",
    read_schema=TarifaPlazaRead,
    create_schema=TarifaPlazaCreate,
    update_schema=TarifaPlazaUpdate,
    get_service=get_tarifa_service,
    id_type=uuid.UUID,
)


# La factory arma un `listar` genérico; F1 (Fase 2) necesita ADEMÁS los filtros
# `estacion_id`/`duracion_spot`/`producto` para encontrar la tarifa ACTIVA de una
# combinación exacta. Se retira SOLO esa ruta y se registra una equivalente con esos
# query params, sin tocar `crud_router.py` (mismo patrón que Estación/Anunciante/Contrato,
# ADR-015 E-3) — evita además el problema de colisión de rutas que tuvo `/vobo` antes de
# ADR-100 (un `GET /tarifas/buscar` agregado DESPUÉS de `/{item_id}` sería interceptado
# por esa ruta genérica).
router.routes = [r for r in router.routes if getattr(r, "name", None) != "listar"]


@router.get("", response_model=Page[TarifaPlazaRead])
def listar_tarifas(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todas, true=activas, false=inactivas"),
    q: str | None = Query(
        None, description="Búsqueda por nombre de anunciante, nombre/siglas de estación o notas"
    ),
    anunciante_id: uuid.UUID | None = Query(None, description="Filtra por anunciante"),
    estacion_id: uuid.UUID | None = Query(None, description="Filtra por estación"),
    duracion_spot: str | None = Query(None, description="Filtra por duración de spot"),
    producto: str | None = Query(None, description="Filtra por producto"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: TarifaService = Depends(get_tarifa_service),
) -> Page[TarifaPlazaRead]:
    return svc.list(
        TarifaListParams(
            page=page,
            size=size,
            activo=activo,
            q=q,
            anunciante_id=anunciante_id,
            estacion_id=estacion_id,
            duracion_spot=duracion_spot,
            producto=producto,
        )
    )


@router.get("/{item_id}/historial", response_model=list[audit.LogCambioParametroRead])
def historial_tarifa(
    item_id: uuid.UUID,
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: TarifaService = Depends(get_tarifa_service),
) -> list[audit.LogCambioParametroRead]:
    """Historial de cambios de `tarifa_bruta`/`descuento_pct` (parámetros sensibles,
    ADR-099)."""
    return list(svc.historial(item_id))
