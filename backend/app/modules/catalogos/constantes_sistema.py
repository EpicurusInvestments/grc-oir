"""Catálogo ConstantesSistema (F0-05) — catálogos SAT/timbrador.

Último módulo de la Fase 0. Constantes fiscales HOMOGÉNEAS (grupo/clave/descripcion/valor)
que Facturación (F2) consume al **preparar** el archivo plano del timbrador (el sistema NO
timbra). Nueve grupos SAT/timbrador (incluye MetodoPago, diferido de F0-04 — ADR-022):
TipoComprobante, Serie, RegimenFiscal, ClaveProdServ, ClaveUnidad, UsoCFDI, FormaPago,
MetodoPago, MonedaSAT.

Monta la base de F0-00 (`BaseRepository`/`BaseService`/`build_crud_router`) y añade:
- **Unicidad natural `(grupo, clave)`** case-insensitive (una clave por grupo; la misma
  clave puede repetirse entre grupos). Verificada en el servicio con `func.lower(...)`
  (portable a SQL Server, coincide con el índice único bajo collation CI — ADR-017).
- **Filtro por `grupo`** en la lista (la pantalla tiene pills por grupo): se reemplaza SOLO
  la ruta `listar` de la factory, como en `tarifa.py` (ADR-015, decisión E-3).
- **Conteos por grupo** (`/constantes/conteos`) para las pills con su número.

RBAC: `permiso_base="catalogos"` → escritura solo Admin; lectura para todas las áreas
operativas (estas constantes son de solo lectura para el operador). La carga masiva CSV
llega en la Tanda 2. Portabilidad SQL Server: booleanos `== True` (ADR-014).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from fastapi import Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, Unicode, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.core.db import Base, datetime2, get_db
from app.core.errors import ConflictError
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos import importacion_csv
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.base_service import BaseService
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.catalogos.importacion_csv import (
    EstadoFila,
    FilaResultado,
    ModoDuplicados,
    ResultadoImportacion,
)
from app.modules.catalogos.schemas import CatalogoReadBase, ListParams, Page

# Columnas del CSV de importación de constantes (plan F0-05, sección C).
COLUMNAS_REQUERIDAS = ["grupo", "clave", "descripcion"]
COLUMNAS_OPCIONALES = ["valor", "activo"]


class GrupoConstante(StrEnum):
    """Grupos SAT/timbrador de la pantalla aprobada (fuente única de los valores válidos)."""

    TIPO_COMPROBANTE = "TipoComprobante"
    SERIE = "Serie"
    REGIMEN_FISCAL = "RegimenFiscal"
    CLAVE_PROD_SERV = "ClaveProdServ"
    CLAVE_UNIDAD = "ClaveUnidad"
    USO_CFDI = "UsoCFDI"
    FORMA_PAGO = "FormaPago"
    METODO_PAGO = "MetodoPago"
    MONEDA_SAT = "MonedaSAT"


# CHECK del `grupo` derivado del enum (una sola fuente de verdad para el DDL del modelo).
_GRUPOS_SQL = ", ".join(f"'{g.value}'" for g in GrupoConstante)


def _normaliza(valor: str) -> str:
    """Colapsa espacios internos y recorta extremos."""
    return " ".join(valor.split())


def _validar_fila(datos: dict[str, str]) -> tuple[dict[str, Any] | None, str | None]:
    """Valida y normaliza una fila cruda del CSV. Devuelve (payload, None) si es válida, o
    (None, motivo) si debe rechazarse (validación por fila del plan F0-05, sección C)."""
    grupo_raw = (datos.get("grupo") or "").strip()
    if not grupo_raw:
        return None, "El grupo es obligatorio."
    try:
        grupo = GrupoConstante(grupo_raw).value
    except ValueError:
        return None, f"Grupo inválido: '{grupo_raw}'."

    clave = _normaliza(datos.get("clave") or "")
    if not clave:
        return None, "La clave es obligatoria."
    if len(clave) > 100:
        return None, "La clave excede 100 caracteres."

    descripcion = _normaliza(datos.get("descripcion") or "")
    if not descripcion:
        return None, "La descripción es obligatoria."
    if len(descripcion) > 400:
        return None, "La descripción excede 400 caracteres."

    valor = _normaliza(datos.get("valor") or "") or None
    if valor is not None and len(valor) > 200:
        return None, "El valor excede 200 caracteres."

    activo, err = importacion_csv.parsear_activo(datos.get("activo") or "")
    if err is not None:
        return None, err

    return {
        "grupo": grupo,
        "clave": clave,
        "descripcion": descripcion,
        "valor": valor,
        "activo": activo,
    }, None


# ── Modelo ──────────────────────────────────────────────────────────────────────
class ConstanteSistema(Base):
    __tablename__ = "constantes_sistema"
    __table_args__ = (
        CheckConstraint(f"grupo IN ({_GRUPOS_SQL})", name="ck_constantes_sistema_grupo"),
        UniqueConstraint("grupo", "clave", name="uq_constantes_sistema_grupo_clave"),
    )

    constante_sistema_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid4)
    grupo: Mapped[str] = mapped_column(Unicode(40), index=True)
    clave: Mapped[str] = mapped_column(Unicode(100))
    descripcion: Mapped[str] = mapped_column(Unicode(400))
    # Valor configurable opcional (p.ej. '33' legacy del timbrador, o la serie 'D').
    valor: Mapped[str | None] = mapped_column(Unicode(200), default=None)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(datetime2(), default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        datetime2(), default=None, onupdate=datetime.now
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class ConstanteSistemaCreate(BaseModel):
    grupo: GrupoConstante
    clave: str = Field(min_length=1, max_length=100)
    descripcion: str = Field(min_length=1, max_length=400)
    valor: str | None = Field(default=None, max_length=200)


class ConstanteSistemaUpdate(BaseModel):
    # `grupo` y `clave` forman la identidad natural del registro: no se editan (se da de baja
    # y se crea otro). Solo se actualizan descripción y valor.
    descripcion: str | None = Field(default=None, min_length=1, max_length=400)
    valor: str | None = Field(default=None, max_length=200)


class ConstanteSistemaRead(CatalogoReadBase):
    model_config = ConfigDict(from_attributes=True)

    constante_sistema_id: uuid.UUID
    grupo: GrupoConstante
    clave: str
    descripcion: str
    valor: str | None = None


class ConteoGrupo(BaseModel):
    """Conteo de constantes por grupo (para las pills de la pantalla)."""

    grupo: GrupoConstante
    total: int


# ── Parámetros de lista (extienden los genéricos con el filtro por grupo) ─────────
class ConstantesListParams(ListParams):
    grupo: GrupoConstante | None = None


# ── Repositorio ───────────────────────────────────────────────────────────────
class ConstanteSistemaRepository(BaseRepository[ConstanteSistema]):
    def _apply_filters(self, stmt: Any, params: ListParams) -> Any:
        stmt = super()._apply_filters(stmt, params)  # activo + q (clave/descripcion/grupo)
        grupo = getattr(params, "grupo", None)
        if grupo is not None:
            stmt = stmt.where(ConstanteSistema.grupo == grupo)
        return stmt

    def get_by_grupo_clave(
        self, grupo: str, clave: str, excluir_id: uuid.UUID | None = None
    ) -> ConstanteSistema | None:
        # CI portable (LOWER): coincide con el índice único bajo collation CI (ADR-017).
        stmt = select(ConstanteSistema).where(
            ConstanteSistema.grupo == grupo,
            func.lower(ConstanteSistema.clave) == clave.lower(),
        )
        if excluir_id is not None:
            stmt = stmt.where(ConstanteSistema.constante_sistema_id != excluir_id)
        return self.db.scalars(stmt).first()

    def conteos_por_grupo(self, *, solo_activos: bool) -> dict[str, int]:
        stmt = select(ConstanteSistema.grupo, func.count()).group_by(ConstanteSistema.grupo)
        if solo_activos:
            stmt = stmt.where(ConstanteSistema.activo == True)  # noqa: E712  (portable, ADR-014)
        return {grupo: int(total) for grupo, total in self.db.execute(stmt).all()}

    def mapa_por_grupo_clave(self) -> dict[tuple[str, str], ConstanteSistema]:
        """Índice {(grupo, clave en minúsculas): obj} de TODO el catálogo, en una consulta.

        Lo usa la importación CSV para clasificar cada fila (crear vs actualizar) sin N+1;
        la tabla de constantes SAT es pequeña, así que precargarla es barato y más rápido.
        """
        objs = self.db.scalars(select(ConstanteSistema)).all()
        return {(o.grupo, o.clave.lower()): o for o in objs}


# ── Servicio ──────────────────────────────────────────────────────────────────
class ConstanteSistemaService(
    BaseService[
        ConstanteSistema,
        ConstanteSistemaCreate,
        ConstanteSistemaUpdate,
        ConstanteSistemaRead,
    ]
):
    read_schema = ConstanteSistemaRead
    entidad = "ConstanteSistema"

    def __init__(self, repo: ConstanteSistemaRepository) -> None:
        super().__init__(repo)
        self._const_repo = repo

    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        payload["grupo"] = GrupoConstante(payload["grupo"]).value
        payload["clave"] = _normaliza(payload["clave"])
        payload["descripcion"] = _normaliza(payload["descripcion"])
        if payload.get("valor") is not None:
            payload["valor"] = _normaliza(payload["valor"]) or None
        self._verificar_unico(payload["grupo"], payload["clave"], excluir_id=None)

    def _pre_update(
        self, obj: ConstanteSistema, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "descripcion" in payload and payload["descripcion"] is not None:
            payload["descripcion"] = _normaliza(payload["descripcion"])
        if "valor" in payload and payload["valor"] is not None:
            payload["valor"] = _normaliza(payload["valor"]) or None

    def _verificar_unico(
        self, grupo: str, clave: str, excluir_id: uuid.UUID | None
    ) -> None:
        if self._const_repo.get_by_grupo_clave(grupo, clave, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe una constante con clave «{clave}» en el grupo «{grupo}».",
                detalles={"grupo": grupo, "clave": clave},
            )

    def conteos(self, *, solo_activos: bool) -> list[ConteoGrupo]:
        conteos = self._const_repo.conteos_por_grupo(solo_activos=solo_activos)
        # Todos los grupos aparecen (con 0 si no tienen registros) para pintar las pills.
        return [
            ConteoGrupo(grupo=g, total=conteos.get(g.value, 0)) for g in GrupoConstante
        ]

    # ── Importación masiva CSV (plan F0-05, sección C) ──────────────────────────
    def importar_csv(
        self, contenido: bytes, *, commit: bool, modo: ModoDuplicados
    ) -> ResultadoImportacion:
        """Importa constantes desde un CSV. `commit=False` previsualiza (no escribe);
        `commit=True` aplica el subconjunto válido en UNA transacción (rollback total si
        falla). El reporte es idéntico en ambos modos (dry-run fiel).

        La validación estructural (columnas/tamaño/UTF-8) la hace `parsear_csv` y aborta con
        error de dominio (nada se aplica). Aquí va la validación por fila, la política de
        duplicados y la aplicación atómica.
        """
        filas = importacion_csv.parsear_csv(
            contenido,
            columnas_requeridas=COLUMNAS_REQUERIDAS,
            columnas_opcionales=COLUMNAS_OPCIONALES,
            max_filas=settings.import_csv_max_rows,
        )
        existentes = self._const_repo.mapa_por_grupo_clave()

        vistos: set[tuple[str, str]] = set()  # (grupo, clave en minúsculas) ya vistos en el archivo
        resultados: list[FilaResultado] = []
        ops_crear: list[dict[str, Any]] = []
        ops_actualizar: list[tuple[ConstanteSistema, dict[str, Any]]] = []
        creadas = actualizadas = omitidas = rechazadas = 0

        for fila in filas:
            payload, err = _validar_fila(fila.datos)
            if err is not None:
                rechazadas += 1
                resultados.append(
                    FilaResultado(
                        numero=fila.numero,
                        grupo=(fila.datos.get("grupo") or "").strip() or None,
                        clave=(fila.datos.get("clave") or "").strip() or None,
                        estado=EstadoFila.RECHAZADA,
                        motivo=err,
                    )
                )
                continue

            assert payload is not None
            grupo, clave = payload["grupo"], payload["clave"]
            key = (grupo, clave.lower())

            if key in vistos:
                rechazadas += 1
                resultados.append(
                    FilaResultado(
                        numero=fila.numero,
                        grupo=grupo,
                        clave=clave,
                        estado=EstadoFila.RECHAZADA,
                        motivo="Clave duplicada dentro del archivo.",
                    )
                )
                continue
            vistos.add(key)

            existente = existentes.get(key)
            if existente is None:
                creadas += 1
                ops_crear.append(payload)
                estado, motivo = EstadoFila.CREADA, None
            elif modo == ModoDuplicados.ACTUALIZAR:
                actualizadas += 1
                ops_actualizar.append((existente, payload))
                estado, motivo = EstadoFila.ACTUALIZADA, None
            elif modo == ModoDuplicados.OMITIR:
                omitidas += 1
                estado, motivo = EstadoFila.OMITIDA, "Ya existe; se conserva sin cambios."
            else:  # RECHAZAR
                rechazadas += 1
                estado, motivo = EstadoFila.RECHAZADA, "Ya existe en la BD (modo rechazar)."

            resultados.append(
                FilaResultado(
                    numero=fila.numero, grupo=grupo, clave=clave, estado=estado, motivo=motivo
                )
            )

        if commit and (ops_crear or ops_actualizar):
            db = self._const_repo.db
            try:
                for p in ops_crear:
                    db.add(ConstanteSistema(**p))
                for obj, p in ops_actualizar:
                    obj.descripcion = p["descripcion"]
                    obj.valor = p["valor"]
                    obj.activo = p["activo"]
                db.commit()
            except Exception:
                db.rollback()
                raise

        return ResultadoImportacion(
            commit=commit,
            total_filas=len(filas),
            creadas=creadas,
            actualizadas=actualizadas,
            omitidas=omitidas,
            rechazadas=rechazadas,
            errores_estructura=[],
            filas=resultados,
        )


# ── Dependencia + router ──────────────────────────────────────────────────────
def get_constante_service(db: Session = Depends(get_db)) -> ConstanteSistemaService:
    repo = ConstanteSistemaRepository(
        db,
        ConstanteSistema,
        search_columns=[
            ConstanteSistema.clave,
            ConstanteSistema.descripcion,
            ConstanteSistema.grupo,
        ],
        default_order_by=[ConstanteSistema.grupo, ConstanteSistema.clave],
    )
    return ConstanteSistemaService(repo)


router = build_crud_router(
    prefix="/constantes",
    tags=["catalogos:constantes"],
    permiso_base="catalogos",
    read_schema=ConstanteSistemaRead,
    create_schema=ConstanteSistemaCreate,
    update_schema=ConstanteSistemaUpdate,
    get_service=get_constante_service,
    id_type=uuid.UUID,
)

# La factory arma un `listar` genérico (page/size/activo/q). Constantes necesita ADEMÁS el
# filtro por `grupo` (pills de la pantalla). Se retira SOLO esa ruta y se registra una
# equivalente que acepta `grupo`, sin tocar `crud_router.py` (mismo patrón que tarifa.py).
router.routes = [r for r in router.routes if getattr(r, "name", None) != "listar"]


@router.get("", response_model=Page[ConstanteSistemaRead])
def listar_constantes(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    activo: bool | None = Query(None, description="None=todas, true=activas, false=inactivas"),
    q: str | None = Query(None, description="Búsqueda en clave, descripción o grupo"),
    grupo: GrupoConstante | None = Query(None, description="Filtra por grupo SAT/timbrador"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ConstanteSistemaService = Depends(get_constante_service),
) -> Page[ConstanteSistemaRead]:
    """Lista de constantes con filtros: grupo, activo/inactivo y búsqueda de texto."""
    return svc.list(
        ConstantesListParams(page=page, size=size, activo=activo, q=q, grupo=grupo)
    )


@router.get("/conteos", response_model=list[ConteoGrupo])
def conteos_constantes(
    solo_activos: bool = Query(True, description="true=solo activas (default), false=todas"),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:leer")),
    svc: ConstanteSistemaService = Depends(get_constante_service),
) -> list[ConteoGrupo]:
    """Conteo por grupo para las pills de la pantalla (todos los grupos, 0 si están vacíos)."""
    return svc.conteos(solo_activos=solo_activos)


@router.post("/importar", response_model=ResultadoImportacion)
def importar_constantes(
    archivo: UploadFile = File(
        ..., description="CSV con columnas: grupo, clave, descripcion, valor, activo"
    ),
    commit: bool = Form(
        False, description="false=previsualizar (default, no escribe); true=aplicar"
    ),
    modo_duplicados: ModoDuplicados = Form(
        ModoDuplicados.ACTUALIZAR,
        description="Qué hacer con claves ya existentes: actualizar (upsert) | omitir | rechazar",
    ),
    usuario: CurrentUser = Depends(requiere_permiso("catalogos:crear")),
    svc: ConstanteSistemaService = Depends(get_constante_service),
) -> ResultadoImportacion:
    """Carga masiva de constantes SAT/timbrador desde CSV (solo Admin).

    Flujo *dry-run → confirmar* (stateless): con `commit=false` se devuelve el reporte de qué
    se haría SIN escribir; el cliente re-sube el mismo archivo con `commit=true` para aplicar.
    El archivo se procesa en memoria y NO se persiste. Import PARCIAL: las filas válidas
    entran, las inválidas se reportan con su motivo; las válidas se aplican atómicamente.
    """
    contenido = importacion_csv.leer_upload(archivo, max_bytes=settings.import_csv_max_bytes)
    return svc.importar_csv(contenido, commit=commit, modo=modo_duplicados)


# La ruta ESTÁTICA `/conteos` debe evaluarse ANTES que la dinámica `/{item_id}` de la
# factory; si no, FastAPI intentaría parsear "conteos" como UUID (422). Se mueve al frente.
router.routes.sort(key=lambda r: 0 if getattr(r, "name", None) == "conteos_constantes" else 1)
