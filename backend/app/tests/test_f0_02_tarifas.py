"""Pruebas del catálogo F0-02 (TarifaPlaza) sobre SQLite.

Se ejercitan las REGLAS de negocio (capa de servicio) sin depender de SQL Server / red:
campo calculado `tarifa_neta`, validación de vigencia, detección de solapamiento (incl.
bordes inclusivos y exclusión de la propia tarifa al editar), enriquecimiento con datos de
plaza y el filtro derivado Vigentes/Expiradas. El DDL real (UNIQUEIDENTIFIER, NUMERIC,
DATE, CHECK, índices) se valida contra RDS con `alembic upgrade`, no aquí.

La portabilidad a SQL Server del filtro booleano/de fechas del solapamiento se fija con un
guard que compila la consulta con el dialecto mssql (ver ADR-014).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, or_, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.plaza import Plaza
from app.modules.catalogos.tarifa import (
    DuracionSpot,
    TarifaListParams,
    TarifaPlaza,
    TarifaPlazaCreate,
    TarifaPlazaRead,
    TarifaPlazaUpdate,
    TarifaRepository,
    TarifaService,
    TipoSenal,
    calcular_tarifa_neta,
)

USUARIO = CurrentUser(username="tester", area=Area.ADMIN)


@pytest.fixture
def sqlite_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def contexto(sqlite_session: Session) -> tuple[TarifaService, Plaza]:
    db = sqlite_session
    plaza_repo = BaseRepository(db, Plaza, search_columns=[Plaza.nombre_plaza])
    # Sin search_columns: la búsqueda `q` se resuelve con JOIN a plaza en _apply_filters.
    tarifa_repo = TarifaRepository(db, TarifaPlaza)
    svc = TarifaService(tarifa_repo, plaza_repo=plaza_repo)
    plaza = plaza_repo.create({"nombre_plaza": "CDMX", "estado": "Ciudad de México"})
    return svc, plaza


def _crear_plaza(svc: TarifaService, nombre: str) -> Plaza:
    # El servicio expone su repo de plazas; se usa para crear una segunda plaza en pruebas.
    return svc._plaza_repo.create({"nombre_plaza": nombre, "estado": nombre})


# ── helpers ─────────────────────────────────────────────────────────────────────
def _tarifa(
    svc: TarifaService,
    plaza_id: uuid.UUID,
    *,
    tipo: str = "fm",
    dur: str = "30s",
    bruta: str = "9000",
    desc: str = "10",
    desde: date = date(2025, 1, 1),
    hasta: date = date(2025, 12, 31),
    notas: str | None = None,
) -> TarifaPlazaRead:
    return svc.create(
        TarifaPlazaCreate(
            plaza_id=plaza_id,
            tipo_senal=TipoSenal(tipo),
            duracion_spot=DuracionSpot(dur),
            tarifa_bruta=Decimal(bruta),
            descuento_pct=Decimal(desc),
            vigencia_desde=desde,
            vigencia_hasta=hasta,
            notas=notas,
        ),
        USUARIO,
    )


# ── Campo calculado ───────────────────────────────────────────────────────────
def test_tarifa_neta_calculada(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id, bruta="9000", desc="10")
    assert t.tarifa_neta == Decimal("8100.00")


def test_tarifa_neta_redondeo_medio_arriba() -> None:
    # 100 * (1 - 33.335/100) = 66.665 → ROUND_HALF_UP → 66.67
    assert calcular_tarifa_neta(Decimal("100"), Decimal("33.335")) == Decimal("66.67")


def test_tarifa_neta_no_esta_en_los_schemas_de_entrada() -> None:
    # El campo calculado NO se acepta del cliente: no existe en Create/Update.
    assert "tarifa_neta" not in TarifaPlazaCreate.model_fields
    assert "tarifa_neta" not in TarifaPlazaUpdate.model_fields


def test_tarifa_neta_se_recalcula_al_editar(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id, bruta="9000", desc="10")  # neta 8100
    upd = svc.update(t.tarifa_plaza_id, TarifaPlazaUpdate(descuento_pct=Decimal("20")), USUARIO)
    assert upd.tarifa_neta == Decimal("7200.00")


# ── Vigencia ────────────────────────────────────────────────────────────────────
def test_vigencia_invertida_rechazada_en_create() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            plaza_id=uuid.uuid4(),
            tipo_senal=TipoSenal.FM,
            duracion_spot=DuracionSpot.S30,
            tarifa_bruta=Decimal("100"),
            descuento_pct=Decimal("0"),
            vigencia_desde=date(2025, 12, 31),
            vigencia_hasta=date(2025, 1, 1),
        )


def test_vigencia_invertida_rechazada_en_update_parcial(
    contexto: tuple[TarifaService, Plaza]
) -> None:
    # Solo se cambia `vigencia_hasta` a una fecha anterior al `vigencia_desde` existente:
    # la validación cruzada la hace el SERVICIO con valores efectivos (no el schema).
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id, desde=date(2025, 6, 1), hasta=date(2025, 12, 31))
    with pytest.raises(DomainError):
        svc.update(
            t.tarifa_plaza_id, TarifaPlazaUpdate(vigencia_hasta=date(2025, 1, 1)), USUARIO
        )


# ── Solapamiento ──────────────────────────────────────────────────────────────
def test_solapamiento_rechazado(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 6, 30))
    with pytest.raises(ConflictError):
        _tarifa(svc, plaza.plaza_id, desde=date(2025, 3, 1), hasta=date(2025, 9, 30))


def test_solapamiento_adyacente_un_dia_rechazado(
    contexto: tuple[TarifaService, Plaza]
) -> None:
    # Bordes INCLUSIVOS: tocarse en un solo día (30-jun / 30-jun) cuenta como solape.
    svc, plaza = contexto
    _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 6, 30))
    with pytest.raises(ConflictError):
        _tarifa(svc, plaza.plaza_id, desde=date(2025, 6, 30), hasta=date(2025, 12, 31))


def test_sin_solapamiento_dias_contiguos_ok(
    contexto: tuple[TarifaService, Plaza]
) -> None:
    svc, plaza = contexto
    _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 6, 30))
    t2 = _tarifa(svc, plaza.plaza_id, desde=date(2025, 7, 1), hasta=date(2025, 12, 31))
    assert t2.tarifa_plaza_id is not None


def test_distinta_combinacion_no_solapa(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    _tarifa(svc, plaza.plaza_id, tipo="fm", dur="30s")
    # Mismo periodo y plaza, pero distinta señal / duración → no hay solape.
    t_am = _tarifa(svc, plaza.plaza_id, tipo="am", dur="30s")
    t_60 = _tarifa(svc, plaza.plaza_id, tipo="fm", dur="60s")
    assert t_am.tarifa_plaza_id and t_60.tarifa_plaza_id


def test_solapa_pero_la_existente_esta_inactiva_ok(
    contexto: tuple[TarifaService, Plaza]
) -> None:
    svc, plaza = contexto
    t1 = _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 12, 31))
    svc.cambiar_estado(t1.tarifa_plaza_id, activo=False, usuario=USUARIO)
    # La inactiva no bloquea: se puede crear otra activa que cubra el mismo rango.
    t2 = _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 12, 31))
    assert t2.tarifa_plaza_id is not None


def test_update_no_choca_consigo_misma(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 12, 31))
    # Editar la misma tarifa (cambia notas, mismo rango) NO debe verse como solape propio.
    upd = svc.update(t.tarifa_plaza_id, TarifaPlazaUpdate(notas="ajuste"), USUARIO)
    assert upd.notas == "ajuste"


def test_reactivar_con_solapamiento_rechazado(
    contexto: tuple[TarifaService, Plaza]
) -> None:
    svc, plaza = contexto
    a = _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 12, 31))
    svc.cambiar_estado(a.tarifa_plaza_id, activo=False, usuario=USUARIO)
    # Con A inactiva, B cubre el mismo rango sin conflicto.
    _tarifa(svc, plaza.plaza_id, desde=date(2025, 1, 1), hasta=date(2025, 12, 31))
    # Reactivar A ahora chocaría con B.
    with pytest.raises(ConflictError):
        svc.cambiar_estado(a.tarifa_plaza_id, activo=True, usuario=USUARIO)


# ── Dependencia de Plaza ────────────────────────────────────────────────────────
def test_plaza_inexistente_rechazada(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, _ = contexto
    with pytest.raises(NotFoundError):
        _tarifa(svc, uuid.uuid4())


# ── ENUMs ─────────────────────────────────────────────────────────────────────
def test_tipo_senal_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            plaza_id=uuid.uuid4(),
            tipo_senal="xx",
            duracion_spot=DuracionSpot.S30,
            tarifa_bruta=Decimal("100"),
            vigencia_desde=date(2025, 1, 1),
            vigencia_hasta=date(2025, 12, 31),
        )


def test_duracion_spot_invalida_rechazada() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            plaza_id=uuid.uuid4(),
            tipo_senal=TipoSenal.FM,
            duracion_spot="45s",
            tarifa_bruta=Decimal("100"),
            vigencia_desde=date(2025, 1, 1),
            vigencia_hasta=date(2025, 12, 31),
        )


def test_descuento_fuera_de_rango_rechazado() -> None:
    with pytest.raises(ValidationError):
        TarifaPlazaCreate(
            plaza_id=uuid.uuid4(),
            tipo_senal=TipoSenal.FM,
            duracion_spot=DuracionSpot.S30,
            tarifa_bruta=Decimal("100"),
            descuento_pct=Decimal("120"),
            vigencia_desde=date(2025, 1, 1),
            vigencia_hasta=date(2025, 12, 31),
        )


# ── Enriquecimiento + baja lógica + filtros ──────────────────────────────────────
def test_enriquecimiento_plaza(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id)
    leido = svc.get(t.tarifa_plaza_id)
    assert leido.plaza_nombre == "CDMX"
    assert leido.plaza_estado == "Ciudad de México"


def test_baja_logica(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id)
    baja = svc.cambiar_estado(t.tarifa_plaza_id, activo=False, usuario=USUARIO)
    assert baja.activo is False
    assert svc.list(TarifaListParams(activo=False)).total == 1
    assert svc.list(TarifaListParams(activo=True)).total == 0


def test_created_by_se_guarda(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    t = _tarifa(svc, plaza.plaza_id)
    assert t.created_by == "tester"


def test_filtro_por_plaza(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    otra = _crear_plaza(svc, "León")
    _tarifa(svc, plaza.plaza_id, tipo="fm")
    _tarifa(svc, plaza.plaza_id, tipo="am")
    _tarifa(svc, otra.plaza_id, tipo="fm")

    solo_cdmx = svc.list(TarifaListParams(plaza_id=plaza.plaza_id))
    assert solo_cdmx.total == 2
    assert all(t.plaza_id == plaza.plaza_id for t in solo_cdmx.items)


def test_filtro_plaza_mas_vigente(contexto: tuple[TarifaService, Plaza]) -> None:
    # Alimenta la sección "Tarifas vigentes" del panel de Plaza: plaza + activo + vigente.
    svc, plaza = contexto
    hoy = date(2026, 7, 8)
    _tarifa(svc, plaza.plaza_id, tipo="fm", desde=date(2026, 1, 1), hasta=date(2026, 12, 31))
    expirada = _tarifa(
        svc, plaza.plaza_id, tipo="am", desde=date(2024, 1, 1), hasta=date(2024, 12, 31)
    )
    svc.cambiar_estado(expirada.tarifa_plaza_id, activo=False, usuario=USUARIO)

    vigentes = svc.list(
        TarifaListParams(plaza_id=plaza.plaza_id, activo=True, vigencia="vigente", hoy=hoy)
    )
    assert vigentes.total == 1
    assert vigentes.items[0].tipo_senal == "fm"


def test_filtro_vigencia_vigente_expirada(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, plaza = contexto
    hoy = date(2026, 7, 8)
    # Vigente: termina en el futuro. Expirada: terminó en el pasado. (Distinta duración
    # para no solapar entre sí.)
    _tarifa(svc, plaza.plaza_id, dur="30s", desde=date(2026, 1, 1), hasta=date(2026, 12, 31))
    _tarifa(svc, plaza.plaza_id, dur="60s", desde=date(2024, 1, 1), hasta=date(2024, 12, 31))

    vigentes = svc.list(TarifaListParams(vigencia="vigente", hoy=hoy))
    expiradas = svc.list(TarifaListParams(vigencia="expirada", hoy=hoy))
    todas = svc.list(TarifaListParams(vigencia="todas", hoy=hoy))
    assert vigentes.total == 1
    assert expiradas.total == 1
    assert todas.total == 2


# ── Búsqueda `q` (nombre/estado de plaza + notas, vía JOIN) ───────────────────────
def test_busqueda_q_por_nombre_de_plaza(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, cdmx = contexto  # "CDMX" / "Ciudad de México"
    leon = _crear_plaza(svc, "León")
    _tarifa(svc, cdmx.plaza_id, tipo="fm")
    _tarifa(svc, leon.plaza_id, tipo="fm")

    res = svc.list(TarifaListParams(q="león"))  # parcial + case-insensitive
    assert res.total == 1
    assert res.items[0].plaza_id == leon.plaza_id


def test_busqueda_q_por_estado_de_plaza(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, cdmx = contexto  # estado "Ciudad de México"
    _tarifa(svc, cdmx.plaza_id, tipo="fm")
    res = svc.list(TarifaListParams(q="méxico"))
    assert res.total == 1
    assert res.items[0].plaza_id == cdmx.plaza_id


def test_busqueda_q_por_notas(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, cdmx = contexto
    _tarifa(svc, cdmx.plaza_id, tipo="fm", notas="Temporada alta")
    _tarifa(svc, cdmx.plaza_id, tipo="am", notas=None)
    res = svc.list(TarifaListParams(q="temporada"))
    assert res.total == 1
    assert res.items[0].notas == "Temporada alta"


def test_busqueda_q_sin_coincidencia(contexto: tuple[TarifaService, Plaza]) -> None:
    svc, cdmx = contexto
    _tarifa(svc, cdmx.plaza_id, tipo="fm", notas="general")
    assert svc.list(TarifaListParams(q="zzz-no-existe")).total == 0


def test_busqueda_q_join_compila_para_sqlserver() -> None:
    """La búsqueda `q` hace JOIN a plaza y usa `ilike` (portable: `lower() LIKE lower()` en
    SQL Server), no operadores no portables. Guard a nivel de dialecto (ver ADR-014)."""
    patron = "%cdmx%"
    stmt = (
        select(TarifaPlaza)
        .join(Plaza, TarifaPlaza.plaza_id == Plaza.plaza_id)
        .where(
            or_(
                Plaza.nombre_plaza.ilike(patron),
                Plaza.estado.ilike(patron),
                TarifaPlaza.notas.ilike(patron),
            )
        )
    )
    sql = str(stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[no-untyped-call]
    assert "JOIN" in sql.upper()
    assert "LIKE" in sql.upper()
    assert "lower(" in sql.lower()  # ilike → lower(col) LIKE lower(patrón)


# ── Portabilidad a SQL Server (regresión ADR-014) ────────────────────────────────
def test_solapamiento_filtro_compila_para_sqlserver() -> None:
    """El filtro de solapamiento usa `activo == True` → debe rendir `activo = 1` en SQL
    Server (nunca `IS 1`, inválido), y comparar fechas con parámetros, sin funciones del
    motor. Fija el criterio a nivel de dialecto (ver ADR-014)."""
    stmt = select(TarifaPlaza).where(
        TarifaPlaza.activo == True,  # noqa: E712
        TarifaPlaza.vigencia_desde <= date(2025, 12, 31),
        TarifaPlaza.vigencia_hasta >= date(2025, 1, 1),
    )
    dialecto = mssql.dialect()  # type: ignore[no-untyped-call]
    sql = str(stmt.compile(dialect=dialecto, compile_kwargs={"literal_binds": True}))
    assert "activo = 1" in sql
    assert "IS 1" not in sql and "IS 0" not in sql
