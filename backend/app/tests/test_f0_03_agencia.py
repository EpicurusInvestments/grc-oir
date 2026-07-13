"""Pruebas del catálogo F0-03 · Agencia + mecanismo de auditoría (SQLite).

Se ejercitan las REGLAS de negocio (capa de servicio) sin depender de SQL Server / red:
unicidad de `nombre_agencia` (case-insensitive), validación de RFC, baja lógica y —lo más
importante de este módulo— la **auditoría de parámetros sensibles**:

- cambiar `porcentaje_comision_agencia_default` genera UNA fila en `LogCambioParametro`;
- el alta también audita (anterior=None) sin exigir motivo;
- modificar el % sin `motivo_cambio` → 400;
- un usuario no-Admin → 403 (permiso por campo);
- editar un campo NO sensible no genera bitácora.

El DDL real (UNIQUEIDENTIFIER, NUMERIC, DATETIME2, CHECK, índice único) se valida contra
RDS con `alembic upgrade`, no aquí. La portabilidad del filtro booleano se fija con un
guard que compila con el dialecto mssql (ADR-014).
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import LogCambioParametro
from app.core.db import Base, get_db
from app.core.errors import (
    ConflictError,
    DomainError,
    PermissionDeniedError,
    register_error_handlers,
)
from app.core.security import Area, CurrentUser
from app.modules.catalogos.agencia import (
    Agencia,
    AgenciaCreate,
    AgenciaRead,
    AgenciaRepository,
    AgenciaService,
    AgenciaUpdate,
)
from app.modules.catalogos.schemas import ListParams

ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")
VENTAS = CurrentUser(username="vendedor", area=Area.VENTAS, ip="127.0.0.1")


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
def svc(sqlite_session: Session) -> AgenciaService:
    from app.modules.catalogos.anunciante import Anunciante, AnuncianteRepository

    repo = AgenciaRepository(
        sqlite_session, Agencia, search_columns=[Agencia.nombre_agencia, Agencia.rfc_agencia]
    )
    return AgenciaService(
        repo, anunciante_repo=AnuncianteRepository(sqlite_session, Anunciante)
    )


# ── helpers ───────────────────────────────────────────────────────────────────
def _crear(
    svc: AgenciaService,
    *,
    nombre: str = "Publicidad Total",
    rfc: str = "PTO950101ABC",
    comision: str = "0",
    usuario: CurrentUser = ADMIN,
) -> AgenciaRead:
    return svc.create(
        AgenciaCreate(
            nombre_agencia=nombre,
            rfc_agencia=rfc,
            porcentaje_comision_agencia_default=Decimal(comision),
        ),
        usuario,
    )


def _logs(db: Session, campo: str | None = None) -> list[LogCambioParametro]:
    stmt = select(LogCambioParametro)
    if campo is not None:
        stmt = stmt.where(LogCambioParametro.campo == campo)
    return list(db.scalars(stmt).all())


# ── Unicidad de nombre ──────────────────────────────────────────────────────────
def test_nombre_unico_rechazado(svc: AgenciaService) -> None:
    _crear(svc, nombre="ACME Media", rfc="AME950101AB1")
    with pytest.raises(ConflictError):
        _crear(svc, nombre="ACME Media", rfc="AME960202CD2")


def test_nombre_unico_case_insensitive(svc: AgenciaService) -> None:
    _crear(svc, nombre="ACME Media", rfc="AME950101AB1")
    with pytest.raises(ConflictError):
        _crear(svc, nombre="acme   media", rfc="AME960202CD2")  # espacios + minúsculas


def test_nombre_se_normaliza_en_espacios(svc: AgenciaService) -> None:
    a = _crear(svc, nombre="  Publicidad   Total  ", rfc="PTO950101AB1")
    assert a.nombre_agencia == "Publicidad Total"


# ── RFC ─────────────────────────────────────────────────────────────────────────
def test_rfc_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        AgenciaCreate(nombre_agencia="X", rfc_agencia="NO-RFC")


def test_rfc_se_normaliza_a_mayusculas(svc: AgenciaService) -> None:
    a = _crear(svc, rfc="pto950101abc")
    assert a.rfc_agencia == "PTO950101ABC"


# ── Auditoría en el ALTA (anterior=None, sin exigir motivo) ───────────────────────
def test_alta_audita_con_anterior_none(svc: AgenciaService, sqlite_session: Session) -> None:
    a = _crear(svc, comision="15")
    logs = _logs(sqlite_session, campo="porcentaje_comision_agencia_default")
    assert len(logs) == 1
    assert logs[0].entidad == "Agencia"
    assert logs[0].entidad_id == str(a.agencia_id)
    assert logs[0].valor_anterior is None
    assert logs[0].valor_nuevo == "15"
    assert logs[0].usuario == "tester"


# ── Auditoría en la EDICIÓN del % sensible ────────────────────────────────────────
def test_editar_comision_con_motivo_audita(svc: AgenciaService, sqlite_session: Session) -> None:
    a = _crear(svc, comision="10")
    svc.update(
        a.agencia_id,
        AgenciaUpdate(
            porcentaje_comision_agencia_default=Decimal("12.5"),
            motivo_cambio="Renegociación anual",
        ),
        ADMIN,
    )
    logs = _logs(sqlite_session, campo="porcentaje_comision_agencia_default")
    # Uno del alta + uno de la edición.
    assert len(logs) == 2
    edicion = [log for log in logs if log.valor_anterior is not None][0]
    assert edicion.valor_anterior == "10.00"
    assert edicion.valor_nuevo == "12.5"
    assert edicion.motivo_cambio == "Renegociación anual"


def test_editar_comision_sin_motivo_rechazado(svc: AgenciaService) -> None:
    a = _crear(svc, comision="10")
    with pytest.raises(DomainError):
        svc.update(
            a.agencia_id,
            AgenciaUpdate(porcentaje_comision_agencia_default=Decimal("12")),
            ADMIN,
        )


def test_editar_comision_no_admin_rechazado(svc: AgenciaService) -> None:
    a = _crear(svc, comision="10")
    with pytest.raises(PermissionDeniedError):
        svc.update(
            a.agencia_id,
            AgenciaUpdate(
                porcentaje_comision_agencia_default=Decimal("12"),
                motivo_cambio="intento no autorizado",
            ),
            VENTAS,
        )


def test_editar_mismo_valor_no_audita(svc: AgenciaService, sqlite_session: Session) -> None:
    a = _crear(svc, comision="10")
    # Mismo valor (10 == 10.00): no hay cambio → no exige motivo ni audita.
    svc.update(
        a.agencia_id,
        AgenciaUpdate(porcentaje_comision_agencia_default=Decimal("10.00")),
        ADMIN,
    )
    logs = _logs(sqlite_session, campo="porcentaje_comision_agencia_default")
    assert len(logs) == 1  # solo el del alta


def test_editar_campo_no_sensible_no_audita(svc: AgenciaService, sqlite_session: Session) -> None:
    a = _crear(svc, comision="10")
    svc.update(a.agencia_id, AgenciaUpdate(contacto_nombre="Nueva persona"), ADMIN)
    logs = _logs(sqlite_session)
    assert len(logs) == 1  # solo el del alta; el cambio de contacto no se audita


def test_motivo_cambio_no_es_columna(svc: AgenciaService) -> None:
    # `motivo_cambio` es transitorio: se consume en el servicio y no se persiste.
    assert not hasattr(Agencia, "motivo_cambio")
    assert "motivo_cambio" not in AgenciaCreate.model_fields


# ── Baja lógica + filtros ─────────────────────────────────────────────────────────
def test_baja_logica(svc: AgenciaService) -> None:
    a = _crear(svc)
    baja = svc.cambiar_estado(a.agencia_id, activo=False, usuario=ADMIN)
    assert baja.activo is False
    assert svc.list(ListParams(activo=False)).total == 1
    assert svc.list(ListParams(activo=True)).total == 0


def test_busqueda_por_nombre_y_rfc(svc: AgenciaService) -> None:
    _crear(svc, nombre="Medios del Norte", rfc="MNO950101AB1")
    _crear(svc, nombre="Sur Publicidad", rfc="SPU960202CD2")
    assert svc.list(ListParams(q="norte")).total == 1
    assert svc.list(ListParams(q="SPU")).total == 1


# ── Portabilidad a SQL Server (regresión ADR-014) ────────────────────────────────
def test_filtro_activo_compila_para_sqlserver() -> None:
    """El filtro por `activo` debe rendir `activo = 1` en SQL Server (nunca `IS 1`)."""
    stmt = select(Agencia).where(Agencia.activo == True)  # noqa: E712
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "activo = 1" in sql
    assert "IS 1" not in sql


def test_unicidad_nombre_usa_lower_portable() -> None:
    """La verificación de unicidad usa LOWER(...) (portable a SQL Server y SQLite)."""
    stmt = select(Agencia).where(func.lower(Agencia.nombre_agencia) == "acme media")
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "lower(" in sql.lower()


# ── Errores de validación a nivel HTTP (regresión: RFC inválido daba 500) ─────────
@pytest.fixture
def client() -> Iterator[TestClient]:
    """App mínima con el router de Agencia + los handlers de error centrales, sobre SQLite.

    Sirve para validar el CONTRATO HTTP (códigos de estado y sobre de error), en particular
    que un dato mal formado devuelva 422 legible y no un 500.
    """
    from app.modules.catalogos.agencia import router as agencia_router

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(agencia_router, prefix="/api/v1/catalogos")

    def _override_db() -> Iterator[Session]:
        s = session_local()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        yield TestClient(app)  # X-Dev-Area default (admin) → escritura permitida
    finally:
        Base.metadata.drop_all(engine)


HEADERS_ADMIN = {"X-Dev-User": "dev.admin", "X-Dev-Area": "admin"}
BASE = "/api/v1/catalogos/agencias"


def test_post_rfc_invalido_da_422(client: TestClient) -> None:
    r = client.post(
        BASE,
        headers=HEADERS_ADMIN,
        json={"nombre_agencia": "X", "rfc_agencia": "stringstring"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "validacion"


def test_put_rfc_invalido_da_422_no_500(client: TestClient) -> None:
    # Alta válida primero.
    alta = client.post(
        BASE,
        headers=HEADERS_ADMIN,
        json={"nombre_agencia": "Publicidad Total", "rfc_agencia": "PTO950101ABC"},
    )
    assert alta.status_code == 201
    agencia_id = alta.json()["agencia_id"]

    # PUT con RFC mal formado: DEBE ser 422 legible, nunca 500 (regresión del handler).
    r = client.put(
        f"{BASE}/{agencia_id}",
        headers=HEADERS_ADMIN,
        json={"rfc_agencia": "stringstring"},
    )
    assert r.status_code == 422
    cuerpo = r.json()
    assert cuerpo["error"]["codigo"] == "validacion"
    # El mensaje humano del validador viaja en el detalle (msg), y el sobre es serializable.
    detalles = cuerpo["error"]["detalles"]
    assert any("RFC" in (d.get("msg") or "") for d in detalles)
