"""Pruebas F0-03 · Anunciante + Marca anidada (SQLite).

Cubren las reglas de servicio sin depender de SQL Server / red:
- alta vía agencia vs directo (`agencia_id` NULL) y filtro derivado Vía agencia / Directo;
- validación de agencia inexistente;
- **auditoría de `dias_credito_default`** (sensible): alta (anterior=None), edición con
  motivo, sin motivo → 400, no-Admin → 403;
- Marca anidada: alta/edición/listado por anunciante y validación de anunciante;
- baja con dependientes: anunciante con marcas activas y agencia con anunciantes activos
  (409 `dependencias_activas`, salvo `forzar`);
- enriquecimiento (`agencia_nombre`, `marcas_count`).

El DDL real se valida contra RDS con `alembic upgrade`. Portabilidad del filtro Directo
(`IS NULL`) fijada con un guard de dialecto mssql (ADR-014).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import LogCambioParametro
from app.core.db import Base
from app.core.errors import (
    DependenciasActivasError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import Area, CurrentUser
from app.modules.catalogos.agencia import Agencia, AgenciaCreate, AgenciaRepository, AgenciaService
from app.modules.catalogos.anunciante import (
    Anunciante,
    AnuncianteCreate,
    AnuncianteListParams,
    AnuncianteRead,
    AnuncianteRepository,
    AnuncianteService,
    AnuncianteUpdate,
    Marca,
    MarcaCreate,
    MarcaRepository,
    MarcaService,
)
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.schemas import ListParams

ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")
VENTAS = CurrentUser(username="vendedor", area=Area.VENTAS, ip="127.0.0.1")


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def anunciante_svc(db: Session) -> AnuncianteService:
    from app.modules.catalogos.contrato import Contrato, ContratoRepository

    repo = AnuncianteRepository(
        db,
        Anunciante,
        search_columns=[
            Anunciante.nombre_comercial,
            Anunciante.nombre_fiscal,
            Anunciante.rfc_anunciante,
        ],
    )
    return AnuncianteService(
        repo,
        agencia_repo=BaseRepository(db, Agencia),
        marca_repo=MarcaRepository(db, Marca),
        contrato_repo=ContratoRepository(db, Contrato),
    )


@pytest.fixture
def marca_svc(db: Session) -> MarcaService:
    repo = MarcaRepository(db, Marca, search_columns=[Marca.nombre_marca])
    return MarcaService(repo, anunciante_repo=AnuncianteRepository(db, Anunciante))


@pytest.fixture
def agencia_svc(db: Session) -> AgenciaService:
    repo = AgenciaRepository(db, Agencia, search_columns=[Agencia.nombre_agencia])
    return AgenciaService(repo, anunciante_repo=AnuncianteRepository(db, Anunciante))


# ── helpers ───────────────────────────────────────────────────────────────────
def _agencia(agencia_svc: AgenciaService, nombre: str = "ACME Media") -> uuid.UUID:
    a = agencia_svc.create(
        AgenciaCreate(nombre_agencia=nombre, rfc_agencia="AME950101AB1"), ADMIN
    )
    return a.agencia_id


def _anunciante(
    svc: AnuncianteService,
    *,
    agencia_id: uuid.UUID | None = None,
    nombre: str = "Refrescos SA",
    rfc: str = "RSA950101AB1",
    dias: int = 0,
) -> AnuncianteRead:
    return svc.create(
        AnuncianteCreate(
            agencia_id=agencia_id,
            nombre_comercial=nombre,
            nombre_fiscal=f"{nombre} de CV",
            rfc_anunciante=rfc,
            dias_credito_default=dias,
        ),
        ADMIN,
    )


def _logs(db: Session, campo: str) -> list[LogCambioParametro]:
    stmt = select(LogCambioParametro).where(LogCambioParametro.campo == campo)
    return list(db.scalars(stmt).all())


# ── Alta directo vs vía agencia ───────────────────────────────────────────────────
def test_alta_directo_sin_agencia(anunciante_svc: AnuncianteService) -> None:
    a = _anunciante(anunciante_svc, agencia_id=None)
    assert a.agencia_id is None
    assert a.agencia_nombre is None


def test_alta_via_agencia_enriquece_nombre(
    anunciante_svc: AnuncianteService, agencia_svc: AgenciaService
) -> None:
    ag = _agencia(agencia_svc)
    a = _anunciante(anunciante_svc, agencia_id=ag)
    assert a.agencia_id == ag
    assert a.agencia_nombre == "ACME Media"


def test_agencia_inexistente_rechazada(anunciante_svc: AnuncianteService) -> None:
    with pytest.raises(NotFoundError):
        _anunciante(anunciante_svc, agencia_id=uuid.uuid4())


# ── Filtro Vía agencia / Directo ──────────────────────────────────────────────────
def test_filtro_relacion(anunciante_svc: AnuncianteService, agencia_svc: AgenciaService) -> None:
    ag = _agencia(agencia_svc)
    _anunciante(anunciante_svc, agencia_id=ag, nombre="Con Agencia", rfc="CAG950101AB1")
    _anunciante(anunciante_svc, agencia_id=None, nombre="Directo Uno", rfc="DUN950101AB2")
    _anunciante(anunciante_svc, agencia_id=None, nombre="Directo Dos", rfc="DDO950101AB3")

    assert anunciante_svc.list(AnuncianteListParams(relacion="todas")).total == 3
    assert anunciante_svc.list(AnuncianteListParams(relacion="via_agencia")).total == 1
    assert anunciante_svc.list(AnuncianteListParams(relacion="directo")).total == 2


# ── Auditoría de dias_credito_default (sensible) ──────────────────────────────────
def test_alta_audita_dias_credito(anunciante_svc: AnuncianteService, db: Session) -> None:
    a = _anunciante(anunciante_svc, dias=30)
    logs = _logs(db, "dias_credito_default")
    assert len(logs) == 1
    assert logs[0].entidad == "Anunciante"
    assert logs[0].entidad_id == str(a.anunciante_id)
    assert logs[0].valor_anterior is None
    assert logs[0].valor_nuevo == "30"


def test_editar_dias_credito_con_motivo_audita(
    anunciante_svc: AnuncianteService, db: Session
) -> None:
    a = _anunciante(anunciante_svc, dias=30)
    anunciante_svc.update(
        a.anunciante_id, AnuncianteUpdate(dias_credito_default=45, motivo_cambio="Ajuste"), ADMIN
    )
    logs = _logs(db, "dias_credito_default")
    assert len(logs) == 2
    edicion = [log for log in logs if log.valor_anterior is not None][0]
    assert edicion.valor_anterior == "30"
    assert edicion.valor_nuevo == "45"
    assert edicion.motivo_cambio == "Ajuste"


def test_editar_dias_credito_sin_motivo_rechazado(anunciante_svc: AnuncianteService) -> None:
    a = _anunciante(anunciante_svc, dias=30)
    with pytest.raises(DomainError):
        anunciante_svc.update(a.anunciante_id, AnuncianteUpdate(dias_credito_default=45), ADMIN)


def test_editar_dias_credito_no_admin_rechazado(anunciante_svc: AnuncianteService) -> None:
    a = _anunciante(anunciante_svc, dias=30)
    with pytest.raises(PermissionDeniedError):
        anunciante_svc.update(
            a.anunciante_id, AnuncianteUpdate(dias_credito_default=45, motivo_cambio="x"), VENTAS
        )


def test_editar_no_sensible_no_audita(anunciante_svc: AnuncianteService, db: Session) -> None:
    a = _anunciante(anunciante_svc, dias=30)
    anunciante_svc.update(a.anunciante_id, AnuncianteUpdate(contacto_nombre="Nueva"), ADMIN)
    assert len(_logs(db, "dias_credito_default")) == 1  # solo el del alta


# ── Marca anidada ─────────────────────────────────────────────────────────────────
def test_marca_alta_y_listado_por_anunciante(
    anunciante_svc: AnuncianteService, marca_svc: MarcaService
) -> None:
    a = _anunciante(anunciante_svc)
    marca_svc.create(MarcaCreate(anunciante_id=a.anunciante_id, nombre_marca="Marca A"), ADMIN)
    marca_svc.create(MarcaCreate(anunciante_id=a.anunciante_id, nombre_marca="Marca B"), ADMIN)
    page = marca_svc.list_por_anunciante(a.anunciante_id, ListParams())
    assert page.total == 2
    assert {m.nombre_marca for m in page.items} == {"Marca A", "Marca B"}


def test_marca_anunciante_inexistente_rechazado(marca_svc: MarcaService) -> None:
    with pytest.raises(NotFoundError):
        marca_svc.create(MarcaCreate(anunciante_id=uuid.uuid4(), nombre_marca="X"), ADMIN)


def test_marcas_count_en_anunciante(
    anunciante_svc: AnuncianteService, marca_svc: MarcaService
) -> None:
    a = _anunciante(anunciante_svc)
    marca_svc.create(MarcaCreate(anunciante_id=a.anunciante_id, nombre_marca="M1"), ADMIN)
    assert anunciante_svc.get(a.anunciante_id).marcas_count == 1


# ── Baja con dependientes ─────────────────────────────────────────────────────────
def test_baja_anunciante_con_marcas_activas(
    anunciante_svc: AnuncianteService, marca_svc: MarcaService
) -> None:
    a = _anunciante(anunciante_svc)
    marca_svc.create(MarcaCreate(anunciante_id=a.anunciante_id, nombre_marca="M1"), ADMIN)
    with pytest.raises(DependenciasActivasError):
        anunciante_svc.cambiar_estado(a.anunciante_id, activo=False, usuario=ADMIN)
    # Con forzar se completa la baja.
    baja = anunciante_svc.cambiar_estado(a.anunciante_id, activo=False, usuario=ADMIN, forzar=True)
    assert baja.activo is False


def test_baja_agencia_con_anunciantes_activos(
    agencia_svc: AgenciaService, anunciante_svc: AnuncianteService
) -> None:
    ag = _agencia(agencia_svc)
    _anunciante(anunciante_svc, agencia_id=ag)
    with pytest.raises(DependenciasActivasError):
        agencia_svc.cambiar_estado(ag, activo=False, usuario=ADMIN)
    baja = agencia_svc.cambiar_estado(ag, activo=False, usuario=ADMIN, forzar=True)
    assert baja.activo is False


# ── Conteo y lista de anunciantes por agencia (columna + panel de Agencia) ────────
def test_agencia_anunciantes_count(
    agencia_svc: AgenciaService, anunciante_svc: AnuncianteService
) -> None:
    ag = _agencia(agencia_svc)
    _anunciante(anunciante_svc, agencia_id=ag, nombre="A1", rfc="AAA950101AB1")
    _anunciante(anunciante_svc, agencia_id=ag, nombre="A2", rfc="BBB950101AB2")
    _anunciante(anunciante_svc, agencia_id=None, nombre="Directo", rfc="DDD950101AB3")
    assert agencia_svc.get(ag).anunciantes_count == 2


def test_listar_anunciantes_por_agencia(
    agencia_svc: AgenciaService, anunciante_svc: AnuncianteService
) -> None:
    ag = _agencia(agencia_svc)
    _anunciante(anunciante_svc, agencia_id=ag, nombre="Con Agencia", rfc="CAG950101AB1")
    _anunciante(anunciante_svc, agencia_id=None, nombre="Directo", rfc="DIR950101AB2")
    page = anunciante_svc.list(AnuncianteListParams(agencia_id=ag))
    assert page.total == 1
    assert page.items[0].nombre_comercial == "Con Agencia"


# ── Portabilidad a SQL Server (regresión ADR-014) ────────────────────────────────
def test_filtro_directo_compila_is_null_para_sqlserver() -> None:
    """El filtro Directo usa `agencia_id IS NULL` (válido en SQL Server; ADR-014)."""
    stmt = select(Anunciante).where(Anunciante.agencia_id.is_(None))
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "IS NULL" in sql.upper()
