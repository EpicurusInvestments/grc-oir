"""Pruebas F0-06 · DuracionSpotCatalogo (SQLite) — ADR-159 (petición del usuario).

Catálogo NUEVO, fuera de la spec BD v2, desconectado del enum `DuracionSpot` compartido
(`app/shared/enums.py`) que usan Tarifa/Órdenes — ese enum no se toca. Se ejercitan las
reglas de servicio: sin duplicado por (producto + descripcion_duracion) case-insensitive,
baja lógica, validación de `producto` (reusa `ProductoTarifa` de `tarifa.py`) y búsqueda
por descripción. El DDL real (CHECK de `producto`, índice) se valida contra RDS con
`alembic upgrade`, no aquí. Portabilidad a SQL Server del filtro `func.lower` (ADR-017).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.errors import ConflictError
from app.core.security import Area, CurrentUser
from app.modules.catalogos.duracion_spot_catalogo import (
    DuracionSpotCatalogo,
    DuracionSpotCatalogoCreate,
    DuracionSpotCatalogoRepository,
    DuracionSpotCatalogoService,
    DuracionSpotCatalogoUpdate,
)

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


@pytest.fixture
def svc(db: Session) -> DuracionSpotCatalogoService:
    repo = DuracionSpotCatalogoRepository(
        db, DuracionSpotCatalogo, search_columns=[DuracionSpotCatalogo.descripcion_duracion]
    )
    return DuracionSpotCatalogoService(repo)


def test_crear_duracion_basica(svc: DuracionSpotCatalogoService) -> None:
    d = svc.create(
        DuracionSpotCatalogoCreate(producto="spot", descripcion_duracion="20"), ADMIN
    )
    assert d.producto == "spot"
    assert d.descripcion_duracion == "20"
    assert d.activo is True


def test_duplicado_mismo_producto_y_descripcion_rechazado(
    svc: DuracionSpotCatalogoService,
) -> None:
    svc.create(DuracionSpotCatalogoCreate(producto="spot", descripcion_duracion="30"), ADMIN)
    with pytest.raises(ConflictError):
        svc.create(
            DuracionSpotCatalogoCreate(producto="spot", descripcion_duracion="  30  "), ADMIN
        )


def test_distinto_producto_misma_descripcion_no_duplica(
    svc: DuracionSpotCatalogoService,
) -> None:
    # "sin duración" se repite para control_remoto y patrocinio — NO es duplicado porque
    # el producto es distinto.
    a = svc.create(
        DuracionSpotCatalogoCreate(producto="control_remoto", descripcion_duracion="sin duración"),
        ADMIN,
    )
    b = svc.create(
        DuracionSpotCatalogoCreate(producto="patrocinio", descripcion_duracion="sin duración"),
        ADMIN,
    )
    assert a.duracion_spot_catalogo_id != b.duracion_spot_catalogo_id


def test_update_no_choca_consigo_misma(svc: DuracionSpotCatalogoService) -> None:
    d = svc.create(DuracionSpotCatalogoCreate(producto="mencion", descripcion_duracion="1"), ADMIN)
    upd = svc.update(
        d.duracion_spot_catalogo_id,
        DuracionSpotCatalogoUpdate(descripcion_duracion="1 (ajustado)"),
        ADMIN,
    )
    assert upd.descripcion_duracion == "1 (ajustado)"


def test_update_a_duplicado_existente_rechazado(svc: DuracionSpotCatalogoService) -> None:
    svc.create(DuracionSpotCatalogoCreate(producto="mencion", descripcion_duracion="2"), ADMIN)
    c = svc.create(DuracionSpotCatalogoCreate(producto="mencion", descripcion_duracion="3"), ADMIN)
    with pytest.raises(ConflictError):
        svc.update(
            c.duracion_spot_catalogo_id,
            DuracionSpotCatalogoUpdate(descripcion_duracion="2"),
            ADMIN,
        )


def test_baja_logica(svc: DuracionSpotCatalogoService) -> None:
    d = svc.create(
        DuracionSpotCatalogoCreate(producto="spot", descripcion_duracion="60"), ADMIN
    )
    baja = svc.cambiar_estado(d.duracion_spot_catalogo_id, activo=False, usuario=ADMIN)
    assert baja.activo is False


def test_producto_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        DuracionSpotCatalogoCreate(producto="jingle", descripcion_duracion="20")


def test_descripcion_vacia_rechazada() -> None:
    with pytest.raises(ValidationError):
        DuracionSpotCatalogoCreate(producto="spot", descripcion_duracion="")


def test_busqueda_por_descripcion(svc: DuracionSpotCatalogoService) -> None:
    svc.create(DuracionSpotCatalogoCreate(producto="spot", descripcion_duracion="20"), ADMIN)
    svc.create(
        DuracionSpotCatalogoCreate(producto="control_remoto", descripcion_duracion="sin duración"),
        ADMIN,
    )
    from app.shared.schemas import ListParams

    res = svc.list(ListParams(q="sin dur"))
    assert res.total == 1
    assert res.items[0].producto == "control_remoto"


# ══════════════════════════════════════════════════════════════════════════════
# Portabilidad a SQL Server (regresión ADR-014/017)
# ══════════════════════════════════════════════════════════════════════════════
def test_unicidad_usa_lower_portable() -> None:
    stmt = select(DuracionSpotCatalogo).where(
        func.lower(DuracionSpotCatalogo.descripcion_duracion) == "sin duración"
    )
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "lower(" in sql.lower()


def test_filtro_activo_compila_para_sqlserver() -> None:
    stmt = select(DuracionSpotCatalogo).where(DuracionSpotCatalogo.activo == True)  # noqa: E712
    sql = str(
        stmt.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[no-untyped-call]
    )
    assert "activo = 1" in sql
    assert "IS 1" not in sql
