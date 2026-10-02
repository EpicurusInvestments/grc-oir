"""Catálogo TarifaPlaza (F0-02).

Tarifa de referencia por **estación + tipo de señal + duración de spot + producto**, con
un campo CALCULADO (`tarifa_neta`). Se sugiere al capturar órdenes (F1). Monta la base de
F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`) y añade sus reglas en la capa de
servicio:

- **Campo calculado (spec):** `tarifa_neta = tarifa_bruta * (1 - descuento_pct / 100)`.
  Lo calcula el servicio con `Decimal` y se persiste; NO se acepta en el request (no está
  en los schemas Create/Update).
- **Sin duplicado activo:** para la misma combinación (estación + tipo_senal +
  duracion_spot + producto) no puede existir otra tarifa ACTIVA → 409 `conflicto`.
- **`created_by`:** se guarda el username (texto), no FK: la tabla `Usuario` llega en F0-04
  (decisión E-2).

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
  reactivación, mismo criterio que antes).

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
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from math import ceil
from typing import Any
from uuid import uuid4

from fastapi import Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_serializer
from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, Unicode, or_, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core import audit
from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError, NotFoundError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.estacion import Estacion
from app.shared.base_repository import BaseRepository
from app.shared.base_service import BaseService
from app.shared.crud_router import build_crud_router
from app.shared.enums import DuracionSpot
from app.shared.schemas import CatalogoReadBase, ListParams, Page


class TipoSenal(StrEnum):
    FM = "fm"
    AM = "am"
    TV = "tv"


class ProductoTarifa(StrEnum):
    SPOT = "spot"
    MENCION = "mencion"
    CONTROL_REMOTO = "control_remoto"
    PATROCINIO = "patrocinio"


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
        CheckConstraint("tipo_senal IN ('fm', 'am', 'tv')", name="ck_tarifa_plaza_tipo_senal"),
        CheckConstraint(
            "duracion_spot IN ('20s', '30s', '60s')",
            name="ck_tarifa_plaza_duracion_spot",
        ),
        CheckConstraint(
            "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
            name="ck_tarifa_plaza_producto",
        ),
        CheckConstraint(
            "descuento_pct >= 0 AND descuento_pct <= 100",
            name="ck_tarifa_plaza_descuento_pct",
        ),
        # Acelera el filtrado por combinación y la consulta de "sin duplicado activo".
        Index("ix_tarifa_plaza_combo", "estacion_id", "tipo_senal", "duracion_spot", "producto"),
    )

    tarifa_plaza_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    estacion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("estacion.estacion_id"), index=True
    )
    tipo_senal: Mapped[str] = mapped_column(Unicode(4))
    duracion_spot: Mapped[str] = mapped_column(Unicode(10))
    producto: Mapped[str] = mapped_column(Unicode(20))
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
    estacion_id: uuid.UUID
    tipo_senal: TipoSenal
    duracion_spot: DuracionSpot
    producto: ProductoTarifa
    tarifa_bruta: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    descuento_pct: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2
    )
    notas: str | None = Field(default=None, max_length=500)


class TarifaPlazaUpdate(BaseModel):
    estacion_id: uuid.UUID | None = None
    tipo_senal: TipoSenal | None = None
    duracion_spot: DuracionSpot | None = None
    producto: ProductoTarifa | None = None
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

    estacion_id: uuid.UUID | None = None
    tipo_senal: TipoSenal | None = None
    duracion_spot: DuracionSpot | None = None
    producto: ProductoTarifa | None = None


class TarifaPlazaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    tarifa_plaza_id: uuid.UUID
    estacion_id: uuid.UUID
    tipo_senal: TipoSenal
    duracion_spot: DuracionSpot
    producto: ProductoTarifa
    tarifa_bruta: Decimal
    descuento_pct: Decimal
    tarifa_neta: Decimal  # Calculado por el servicio (solo lectura)
    notas: str | None = None
    created_by: str | None = None
    # Derivado (solo lectura; NO se acepta en Create/Update):
    estacion_nombre: str | None = None  # nombre_estacion de la estación referenciada

    # Los montos viajan como STRING para preservar la precisión Decimal (decisión E-4).
    @field_serializer("tarifa_bruta", "descuento_pct", "tarifa_neta")
    def _serializa_decimal(self, valor: Decimal) -> str:
        return str(valor)


# ── Repositorio ───────────────────────────────────────────────────────────────
class TarifaRepository(BaseRepository[TarifaPlaza]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        # La base aplica `activo`; `q` NO (search_columns vacío) porque la búsqueda de
        # tarifas abarca campos de la ESTACIÓN (nombre/siglas) además de notas → requiere JOIN.
        stmt = super()._apply_filters(stmt, params)
        q = (getattr(params, "q", None) or "").strip()
        if q:
            patron = f"%{q}%"
            # Un solo JOIN con estación (relación N:1, no duplica filas). Coincidencia
            # parcial case-insensitive en cualquiera de los tres campos. `ilike` es
            # portable a SQL Server (compila a lower(...) LIKE lower(...)); `siglas` puede
            # ser NULL y simplemente no coincide.
            stmt = stmt.join(Estacion, TarifaPlaza.estacion_id == Estacion.estacion_id).where(
                or_(
                    Estacion.nombre_estacion.ilike(patron),
                    Estacion.siglas.ilike(patron),
                    TarifaPlaza.notas.ilike(patron),
                )
            )
        for campo in ("estacion_id", "tipo_senal", "duracion_spot", "producto"):
            valor = getattr(params, campo, None)
            if valor is not None:
                stmt = stmt.where(getattr(TarifaPlaza, campo) == valor)
        return stmt

    def existe_duplicado_activo(
        self,
        *,
        estacion_id: uuid.UUID,
        tipo_senal: str,
        duracion_spot: str,
        producto: str,
        excluir_id: uuid.UUID | None = None,
    ) -> TarifaPlaza | None:
        """Devuelve la primera tarifa ACTIVA con la misma combinación (estación + tipo de
        señal + duración + producto), o None."""
        stmt = select(TarifaPlaza).where(
            TarifaPlaza.estacion_id == estacion_id,
            TarifaPlaza.tipo_senal == tipo_senal,
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


# ── Servicio ──────────────────────────────────────────────────────────────────
class TarifaService(
    BaseService[TarifaPlaza, TarifaPlazaCreate, TarifaPlazaUpdate, TarifaPlazaRead]
):
    read_schema = TarifaPlazaRead
    entidad = "TarifaPlaza"

    def __init__(self, repo: TarifaRepository, *, estacion_repo: BaseRepository[Estacion]) -> None:
        super().__init__(repo)
        self._tarifa_repo = repo
        self._estacion_repo = estacion_repo

    # ── enriquecimiento (estacion_nombre) ───────────────────────────────────────
    def _read(self, obj: TarifaPlaza, estacion_nombre: str | None) -> TarifaPlazaRead:
        return TarifaPlazaRead.model_validate(obj).model_copy(
            update={"estacion_nombre": estacion_nombre}
        )

    def _to_read(self, obj: TarifaPlaza) -> TarifaPlazaRead:
        nombre = self._tarifa_repo.nombres_de_estaciones([obj.estacion_id]).get(obj.estacion_id)
        return self._read(obj, nombre)

    def list(self, params: ListParams) -> Page[TarifaPlazaRead]:
        # Enriquecimiento por LOTE: 2 consultas por página (lista + nombres de estación).
        items, total = self.repo.list(params)
        nombres = self._tarifa_repo.nombres_de_estaciones([t.estacion_id for t in items])
        return Page[TarifaPlazaRead](
            items=[self._read(t, nombres.get(t.estacion_id)) for t in items],
            total=total,
            page=params.page,
            size=params.size,
            pages=ceil(total / params.size) if params.size else 0,
        )

    # ── reglas de negocio ────────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        self._verificar_estacion(payload["estacion_id"])
        payload["tarifa_neta"] = calcular_tarifa_neta(
            payload["tarifa_bruta"], payload["descuento_pct"]
        )
        payload["created_by"] = usuario.username
        # Una tarifa se crea ACTIVA → siempre se valida el duplicado.
        self._verificar_sin_duplicado_activo(
            estacion_id=payload["estacion_id"],
            tipo_senal=payload["tipo_senal"],
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

        if "estacion_id" in payload:
            self._verificar_estacion(payload["estacion_id"])

        # Valores EFECTIVOS: lo que trae el payload o, si no, el valor actual del registro.
        estacion_id = payload.get("estacion_id", obj.estacion_id)
        tipo_senal = payload.get("tipo_senal", obj.tipo_senal)
        duracion_spot = payload.get("duracion_spot", obj.duracion_spot)
        producto = payload.get("producto", obj.producto)
        bruta = payload.get("tarifa_bruta", obj.tarifa_bruta)
        descuento = payload.get("descuento_pct", obj.descuento_pct)

        # Recalcular siempre la neta a partir de los valores efectivos (nunca del cliente).
        payload["tarifa_neta"] = calcular_tarifa_neta(bruta, descuento)

        # Solo tiene sentido revalidar el duplicado si la tarifa está ACTIVA.
        if obj.activo:
            self._verificar_sin_duplicado_activo(
                estacion_id=estacion_id,
                tipo_senal=tipo_senal,
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
            self._verificar_sin_duplicado_activo(
                estacion_id=obj.estacion_id,
                tipo_senal=obj.tipo_senal,
                duracion_spot=obj.duracion_spot,
                producto=obj.producto,
                excluir_id=obj.tarifa_plaza_id,
            )
        # TarifaPlaza no tiene dependientes: la baja lógica no se bloquea (no usa `forzar`).
        return self._to_read(self.repo.set_activo(obj, activo))

    # ── helpers ──────────────────────────────────────────────────────────────────
    def _verificar_estacion(self, estacion_id: uuid.UUID) -> None:
        if self._estacion_repo.get(estacion_id) is None:
            raise NotFoundError(
                "Estación no encontrada para la tarifa.",
                detalles={"estacion_id": str(estacion_id)},
            )

    def _verificar_sin_duplicado_activo(
        self,
        *,
        estacion_id: uuid.UUID,
        tipo_senal: str,
        duracion_spot: str,
        producto: str,
        excluir_id: uuid.UUID | None,
    ) -> None:
        conflicto = self._tarifa_repo.existe_duplicado_activo(
            estacion_id=estacion_id,
            tipo_senal=tipo_senal,
            duracion_spot=duracion_spot,
            producto=producto,
            excluir_id=excluir_id,
        )
        if conflicto is not None:
            raise ConflictError(
                "Ya existe una tarifa activa para esta estación con el mismo tipo de "
                "señal, duración y producto.",
                detalles={"tarifa_en_conflicto": str(conflicto.tarifa_plaza_id)},
            )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_tarifa_service(db: Session = Depends(get_db)) -> TarifaService:
    # Sin `search_columns`: la búsqueda `q` se maneja en TarifaRepository._apply_filters con
    # un JOIN a estacion (abarca nombre/siglas de la estación + notas).
    repo = TarifaRepository(db, TarifaPlaza)
    return TarifaService(repo, estacion_repo=BaseRepository(db, Estacion))


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
# `estacion_id`/`tipo_senal`/`duracion_spot`/`producto` para encontrar la tarifa ACTIVA de
# una combinación exacta. Se retira SOLO esa ruta y se registra una equivalente con esos
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
    q: str | None = Query(None, description="Búsqueda por nombre/siglas de estación o notas"),
    estacion_id: uuid.UUID | None = Query(None, description="Filtra por estación"),
    tipo_senal: TipoSenal | None = Query(None, description="Filtra por tipo de señal"),
    duracion_spot: DuracionSpot | None = Query(None, description="Filtra por duración de spot"),
    producto: ProductoTarifa | None = Query(None, description="Filtra por producto"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: TarifaService = Depends(get_tarifa_service),
) -> Page[TarifaPlazaRead]:
    return svc.list(
        TarifaListParams(
            page=page,
            size=size,
            activo=activo,
            q=q,
            estacion_id=estacion_id,
            tipo_senal=tipo_senal,
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
