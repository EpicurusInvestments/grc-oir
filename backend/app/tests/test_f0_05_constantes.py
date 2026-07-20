"""Pruebas F0-05 · ConstantesSistema + CuentaContable (SQLite).

Se ejercitan las reglas de servicio y la costura HTTP sin depender de SQL Server / red:

- ConstantesSistema: unicidad `(grupo, clave)` case-insensitive (misma clave en distinto
  grupo SÍ se permite), filtro por grupo, conteos por grupo, baja lógica, grupo inválido.
- CuentaContable: unicidad `codigo_cuenta` CI, `tipo_cuenta` inválido, baja lógica.
- HTTP: RBAC (admin escribe; ventas lee, 403 al crear) y que la ruta estática `/conteos`
  no la eclipse la dinámica `/{item_id}`.

El DDL real (CHECK de grupo/tipo, índices únicos, NVARCHAR, DATETIME2) se valida contra RDS
con `alembic upgrade`. Los guards de dialecto fijan la portabilidad a SQL Server (ADR-014).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, create_engine, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import ConflictError, register_error_handlers
from app.core.security import Area, CurrentUser
from app.modules.catalogos.constantes_sistema import (
    ConstanteSistema,
    ConstanteSistemaCreate,
    ConstanteSistemaRepository,
    ConstanteSistemaService,
    ConstanteSistemaUpdate,
    GrupoConstante,
)
from app.modules.catalogos.constantes_sistema import router as constantes_router
from app.modules.catalogos.cuenta_contable import (
    CuentaContable,
    CuentaContableCreate,
    CuentaContableRepository,
    CuentaContableService,
    CuentaContableUpdate,
    TipoCuenta,
)
from app.modules.catalogos.cuenta_contable import router as cuenta_router
from app.modules.catalogos.schemas import ListParams

ADMIN = CurrentUser(username="tester", area=Area.ADMIN, ip="127.0.0.1")


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


# ══════════════════════════════════════════════════════════════════════════════
# ConstantesSistema
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def const_svc(db: Session) -> ConstanteSistemaService:
    repo = ConstanteSistemaRepository(
        db,
        ConstanteSistema,
        search_columns=[
            ConstanteSistema.clave,
            ConstanteSistema.descripcion,
            ConstanteSistema.grupo,
        ],
    )
    return ConstanteSistemaService(repo)


def _const(
    svc: ConstanteSistemaService,
    *,
    grupo: GrupoConstante = GrupoConstante.USO_CFDI,
    clave: str = "G03",
    descripcion: str = "Gastos en general",
    valor: str | None = None,
) -> Any:
    return svc.create(
        ConstanteSistemaCreate(grupo=grupo, clave=clave, descripcion=descripcion, valor=valor),
        ADMIN,
    )


def test_const_grupo_clave_unico_ci(const_svc: ConstanteSistemaService) -> None:
    _const(const_svc, grupo=GrupoConstante.USO_CFDI, clave="G03")
    with pytest.raises(ConflictError):
        _const(const_svc, grupo=GrupoConstante.USO_CFDI, clave=" g03 ")  # CI + espacios


def test_const_misma_clave_distinto_grupo_permitida(const_svc: ConstanteSistemaService) -> None:
    # "01" existe como FormaPago (Efectivo) y podría existir en otro grupo: no colisiona.
    _const(const_svc, grupo=GrupoConstante.FORMA_PAGO, clave="01", descripcion="Efectivo")
    otra = _const(
        const_svc, grupo=GrupoConstante.MONEDA_SAT, clave="01", descripcion="Solo prueba"
    )
    assert otra.clave == "01"


def test_const_grupo_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        ConstanteSistemaCreate(grupo="NoEsGrupo", clave="X", descripcion="Y")


def test_const_filtro_por_grupo(const_svc: ConstanteSistemaService) -> None:
    _const(const_svc, grupo=GrupoConstante.USO_CFDI, clave="G01", descripcion="Adquisición")
    _const(const_svc, grupo=GrupoConstante.USO_CFDI, clave="G03", descripcion="Gastos")
    _const(const_svc, grupo=GrupoConstante.MONEDA_SAT, clave="MXN", descripcion="Peso")

    from app.modules.catalogos.constantes_sistema import ConstantesListParams

    solo_uso = const_svc.list(ConstantesListParams(grupo=GrupoConstante.USO_CFDI))
    assert solo_uso.total == 2
    todos = const_svc.list(ConstantesListParams())
    assert todos.total == 3


def test_const_conteos_incluye_todos_los_grupos(const_svc: ConstanteSistemaService) -> None:
    _const(const_svc, grupo=GrupoConstante.USO_CFDI, clave="G01", descripcion="Adquisición")
    _const(const_svc, grupo=GrupoConstante.USO_CFDI, clave="G03", descripcion="Gastos")

    conteos = {c.grupo: c.total for c in const_svc.conteos(solo_activos=True)}
    assert len(conteos) == len(GrupoConstante)  # los 9 grupos, aunque tengan 0
    assert conteos[GrupoConstante.USO_CFDI] == 2
    assert conteos[GrupoConstante.SERIE] == 0


def test_const_update_solo_descripcion_y_valor(const_svc: ConstanteSistemaService) -> None:
    c = _const(const_svc, clave="G03", descripcion="Gastos", valor=None)
    upd = const_svc.update(
        c.constante_sistema_id,
        ConstanteSistemaUpdate(descripcion="Gastos en general", valor="X"),
        ADMIN,
    )
    assert upd.descripcion == "Gastos en general"
    assert upd.valor == "X"
    assert upd.clave == "G03"  # la clave no cambia por edición


def test_const_baja_logica(const_svc: ConstanteSistemaService) -> None:
    c = _const(const_svc)
    baja = const_svc.cambiar_estado(c.constante_sistema_id, activo=False, usuario=ADMIN)
    assert baja.activo is False
    assert const_svc.list(ListParams(activo=False)).total == 1


# ══════════════════════════════════════════════════════════════════════════════
# CuentaContable
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def cuenta_svc(db: Session) -> CuentaContableService:
    repo = CuentaContableRepository(
        db,
        CuentaContable,
        search_columns=[CuentaContable.codigo_cuenta, CuentaContable.nombre_cuenta],
    )
    return CuentaContableService(repo)


def _cuenta(
    svc: CuentaContableService,
    *,
    codigo: str = "4000-001",
    nombre: str = "Ingresos por publicidad",
    tipo: TipoCuenta = TipoCuenta.INGRESO,
) -> Any:
    return svc.create(
        CuentaContableCreate(codigo_cuenta=codigo, nombre_cuenta=nombre, tipo_cuenta=tipo),
        ADMIN,
    )


def test_cuenta_codigo_unico_ci(cuenta_svc: CuentaContableService) -> None:
    _cuenta(cuenta_svc, codigo="4000-001")
    with pytest.raises(ConflictError):
        _cuenta(cuenta_svc, codigo=" 4000-001 ", nombre="Otra")


def test_cuenta_tipo_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        CuentaContableCreate(codigo_cuenta="1", nombre_cuenta="X", tipo_cuenta="patrimonio")


def test_cuenta_update_tipo(cuenta_svc: CuentaContableService) -> None:
    c = _cuenta(cuenta_svc, tipo=TipoCuenta.INGRESO)
    upd = cuenta_svc.update(
        c.cuenta_contable_id, CuentaContableUpdate(tipo_cuenta=TipoCuenta.GASTO), ADMIN
    )
    assert upd.tipo_cuenta == TipoCuenta.GASTO


def test_cuenta_baja_logica(cuenta_svc: CuentaContableService) -> None:
    c = _cuenta(cuenta_svc)
    baja = cuenta_svc.cambiar_estado(c.cuenta_contable_id, activo=False, usuario=ADMIN)
    assert baja.activo is False


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: RBAC + orden de rutas (/conteos vs /{item_id})
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(constantes_router, prefix="/api/v1/catalogos")
    app.include_router(cuenta_router, prefix="/api/v1/catalogos")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def test_http_admin_crea_constante(client: TestClient) -> None:
    r = client.post(
        "/api/v1/catalogos/constantes",
        json={"grupo": "UsoCFDI", "clave": "G03", "descripcion": "Gastos en general"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 201
    assert r.json()["grupo"] == "UsoCFDI"


def test_http_ventas_lee_pero_no_crea(client: TestClient) -> None:
    assert client.get("/api/v1/catalogos/constantes", headers=_hdr("ventas")).status_code == 200
    r = client.post(
        "/api/v1/catalogos/constantes",
        json={"grupo": "UsoCFDI", "clave": "G01", "descripcion": "Adquisición"},
        headers=_hdr("ventas"),
    )
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "sin_permiso"


def test_http_conteos_no_lo_eclipsa_item_id(client: TestClient) -> None:
    # /conteos es estática y debe resolverse antes que /{item_id} (UUID). 200, no 422.
    r = client.get("/api/v1/catalogos/constantes/conteos", headers=_hdr("admin"))
    assert r.status_code == 200
    grupos = {c["grupo"] for c in r.json()}
    assert grupos == {g.value for g in GrupoConstante}


def test_http_filtro_grupo_en_lista(client: TestClient) -> None:
    for clave, grupo in [("G01", "UsoCFDI"), ("G03", "UsoCFDI"), ("MXN", "MonedaSAT")]:
        client.post(
            "/api/v1/catalogos/constantes",
            json={"grupo": grupo, "clave": clave, "descripcion": clave},
            headers=_hdr("admin"),
        )
    r = client.get(
        "/api/v1/catalogos/constantes", params={"grupo": "UsoCFDI"}, headers=_hdr("admin")
    )
    assert r.status_code == 200
    assert r.json()["total"] == 2


def test_http_cuenta_tipo_invalido_422(client: TestClient) -> None:
    r = client.post(
        "/api/v1/catalogos/cuentas-contables",
        json={"codigo_cuenta": "1", "nombre_cuenta": "X", "tipo_cuenta": "patrimonio"},
        headers=_hdr("admin"),
    )
    assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# Portabilidad a SQL Server (regresión ADR-014/017) + fidelidad de los CHECK
# ══════════════════════════════════════════════════════════════════════════════
def test_const_filtro_activo_compila_para_sqlserver() -> None:
    stmt = select(ConstanteSistema).where(ConstanteSistema.activo == True)  # noqa: E712
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "activo = 1" in sql
    assert "IS 1" not in sql


def test_const_unicidad_usa_lower_portable() -> None:
    stmt = select(ConstanteSistema).where(func.lower(ConstanteSistema.clave) == "g03")
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "lower(" in sql.lower()


def test_check_grupo_incluye_los_9_grupos() -> None:
    tabla: Any = ConstanteSistema.__table__
    checks = [
        c
        for c in tabla.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_constantes_sistema_grupo"
    ]
    assert checks, "falta el CHECK ck_constantes_sistema_grupo"
    sqltext = str(checks[0].sqltext)
    for g in GrupoConstante:
        assert f"'{g.value}'" in sqltext


def test_check_tipo_cuenta_incluye_los_5_tipos() -> None:
    tabla: Any = CuentaContable.__table__
    checks = [
        c
        for c in tabla.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_cuenta_contable_tipo"
    ]
    assert checks, "falta el CHECK ck_cuenta_contable_tipo"
    sqltext = str(checks[0].sqltext)
    for t in TipoCuenta:
        assert f"'{t.value}'" in sqltext
