"""Pruebas F0-04 · EmpresaFacturadora · Vendedor · Categoria · modelo Usuario (SQLite).

Se ejercitan las reglas de servicio sin depender de SQL Server / red: unicidades (RFC de
empresa, nombre de categoría CI), validación de RFC, baja lógica y —lo importante— la
**auditoría del % sensible de Vendedor** reutilizando el mecanismo de F0-03. El DDL real
(CHECK de `area`, índices únicos, NVARCHAR(MAX), seed) se valida contra RDS con
`alembic upgrade`. Los guards de dialecto fijan la portabilidad a SQL Server (ADR-014/017).
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.audit import LogCambioParametro
from app.core.db import Base
from app.core.errors import ConflictError, DomainError, PermissionDeniedError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.categoria import (
    Categoria,
    CategoriaCreate,
    CategoriaRepository,
    CategoriaService,
)
from app.modules.catalogos.empresa_facturadora import (
    EmpresaFacturadora,
    EmpresaFacturadoraCreate,
    EmpresaFacturadoraRepository,
    EmpresaFacturadoraService,
)
from app.modules.catalogos.schemas import ListParams
from app.modules.catalogos.vendedor import (
    Vendedor,
    VendedorCreate,
    VendedorService,
    VendedorUpdate,
)
from app.modules.usuarios.models import Usuario

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


# ══════════════════════════════════════════════════════════════════════════════
# EmpresaFacturadora
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def empresa_svc(db: Session) -> EmpresaFacturadoraService:
    repo = EmpresaFacturadoraRepository(
        db,
        EmpresaFacturadora,
        search_columns=[EmpresaFacturadora.nombre_empresa, EmpresaFacturadora.rfc_empresa],
    )
    return EmpresaFacturadoraService(repo)


def _empresa(
    svc: EmpresaFacturadoraService,
    *,
    nombre: str = "Grupo Radio Centro",
    rfc: str = "GRC950101AB1",
) -> Any:
    return svc.create(
        EmpresaFacturadoraCreate(
            nombre_empresa=nombre, rfc_empresa=rfc, direccion_empresa="CDMX"
        ),
        ADMIN,
    )


def test_empresa_rfc_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        EmpresaFacturadoraCreate(nombre_empresa="X", rfc_empresa="NO-RFC")


def test_empresa_rfc_unico(empresa_svc: EmpresaFacturadoraService) -> None:
    _empresa(empresa_svc, nombre="Empresa A", rfc="AAA950101AB1")
    with pytest.raises(ConflictError):
        _empresa(empresa_svc, nombre="Empresa B", rfc="AAA950101AB1")


def test_empresa_baja_logica(empresa_svc: EmpresaFacturadoraService) -> None:
    e = _empresa(empresa_svc)
    baja = empresa_svc.cambiar_estado(e.empresa_facturadora_id, activo=False, usuario=ADMIN)
    assert baja.activo is False
    assert empresa_svc.list(ListParams(activo=False)).total == 1


# ══════════════════════════════════════════════════════════════════════════════
# Vendedor (parámetro sensible → auditoría, reutilizando el mecanismo de F0-03)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def vendedor_svc(db: Session) -> VendedorService:
    repo = BaseRepository(
        db, Vendedor, search_columns=[Vendedor.nombre_vendedor, Vendedor.email_vendedor]
    )
    return VendedorService(repo)


def _vendedor(
    svc: VendedorService, *, nombre: str = "Carmen Aristegui", comision: str = "0"
) -> Any:
    return svc.create(
        VendedorCreate(nombre_vendedor=nombre, porcentaje_comision_default=Decimal(comision)),
        ADMIN,
    )


def _logs(db: Session) -> list[LogCambioParametro]:
    stmt = select(LogCambioParametro).where(
        LogCambioParametro.campo == "porcentaje_comision_default"
    )
    return list(db.scalars(stmt).all())


def test_vendedor_alta_audita_anterior_none(vendedor_svc: VendedorService, db: Session) -> None:
    v = _vendedor(vendedor_svc, comision="5")
    logs = _logs(db)
    assert len(logs) == 1
    assert logs[0].entidad == "Vendedor"
    assert logs[0].entidad_id == str(v.vendedor_id)
    assert logs[0].valor_anterior is None
    assert logs[0].valor_nuevo == "5"


def test_vendedor_editar_con_motivo_audita(vendedor_svc: VendedorService, db: Session) -> None:
    v = _vendedor(vendedor_svc, comision="5")
    vendedor_svc.update(
        v.vendedor_id,
        VendedorUpdate(porcentaje_comision_default=Decimal("4.5"), motivo_cambio="Ajuste"),
        ADMIN,
    )
    logs = _logs(db)
    assert len(logs) == 2
    edicion = [log for log in logs if log.valor_anterior is not None][0]
    assert edicion.valor_anterior == "5.00"
    assert edicion.valor_nuevo == "4.5"
    assert edicion.motivo_cambio == "Ajuste"


def test_vendedor_editar_sin_motivo_rechazado(vendedor_svc: VendedorService) -> None:
    v = _vendedor(vendedor_svc, comision="5")
    with pytest.raises(DomainError):
        vendedor_svc.update(
            v.vendedor_id, VendedorUpdate(porcentaje_comision_default=Decimal("4")), ADMIN
        )


def test_vendedor_editar_no_admin_rechazado(vendedor_svc: VendedorService) -> None:
    v = _vendedor(vendedor_svc, comision="5")
    with pytest.raises(PermissionDeniedError):
        vendedor_svc.update(
            v.vendedor_id,
            VendedorUpdate(porcentaje_comision_default=Decimal("4"), motivo_cambio="x"),
            VENTAS,
        )


def test_vendedor_editar_no_sensible_no_audita(vendedor_svc: VendedorService, db: Session) -> None:
    v = _vendedor(vendedor_svc, comision="5")
    vendedor_svc.update(v.vendedor_id, VendedorUpdate(email_vendedor="c@grcoir.com"), ADMIN)
    assert len(_logs(db)) == 1  # solo el del alta


def test_vendedor_historial(vendedor_svc: VendedorService) -> None:
    v = _vendedor(vendedor_svc, comision="5")
    vendedor_svc.update(
        v.vendedor_id,
        VendedorUpdate(porcentaje_comision_default=Decimal("6"), motivo_cambio="subida"),
        ADMIN,
    )
    hist = vendedor_svc.historial(v.vendedor_id)
    assert len(hist) == 2
    assert all(h.entidad == "Vendedor" for h in hist)


# ══════════════════════════════════════════════════════════════════════════════
# Categoria (nombre único CI)
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def categoria_svc(db: Session) -> CategoriaService:
    repo = CategoriaRepository(db, Categoria, search_columns=[Categoria.nombre_categoria])
    return CategoriaService(repo)


def test_categoria_unica_case_insensitive(categoria_svc: CategoriaService) -> None:
    categoria_svc.create(CategoriaCreate(nombre_categoria="Automotriz"), ADMIN)
    with pytest.raises(ConflictError):
        categoria_svc.create(CategoriaCreate(nombre_categoria="  automotriz "), ADMIN)


def test_categoria_baja_logica(categoria_svc: CategoriaService) -> None:
    c = categoria_svc.create(CategoriaCreate(nombre_categoria="Retail"), ADMIN)
    baja = categoria_svc.cambiar_estado(c.categoria_id, activo=False, usuario=ADMIN)
    assert baja.activo is False


# ══════════════════════════════════════════════════════════════════════════════
# Usuario (modelo base)
# ══════════════════════════════════════════════════════════════════════════════
def test_usuario_modelo_mapea(db: Session) -> None:
    u = Usuario(
        nombre_usuario="dev.admin",
        email="dev.admin@grcoir.com",
        area="admin",
        activo=True,
    )
    db.add(u)
    db.commit()
    leido = db.scalars(select(Usuario).where(Usuario.email == "dev.admin@grcoir.com")).first()
    assert leido is not None
    assert leido.area == "admin"
    assert leido.roles_adicionales is None


# ══════════════════════════════════════════════════════════════════════════════
# Portabilidad a SQL Server (regresión ADR-014/017)
# ══════════════════════════════════════════════════════════════════════════════
def test_categoria_unicidad_usa_lower_portable() -> None:
    stmt = select(Categoria).where(func.lower(Categoria.nombre_categoria) == "automotriz")
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "lower(" in sql.lower()


def test_vendedor_filtro_activo_compila_para_sqlserver() -> None:
    stmt = select(Vendedor).where(Vendedor.activo == True)  # noqa: E712
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "activo = 1" in sql
    assert "IS 1" not in sql


def test_usuario_area_check_incluye_las_8_areas() -> None:
    """El CHECK `ck_usuario_area` enumera los 8 valores exactos (VARCHAR + CHECK, ADR-001)."""
    from sqlalchemy import CheckConstraint

    tabla: Any = Usuario.__table__  # __table__ está tipado como FromClause; aquí es Table
    checks = [
        c
        for c in tabla.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_usuario_area"
    ]
    assert checks, "falta el CHECK ck_usuario_area"
    sqltext = str(checks[0].sqltext)
    areas = ("ventas", "facturacion", "tesoreria", "cxc", "cxp", "direccion", "nominas", "admin")
    for area in areas:
        assert f"'{area}'" in sqltext
