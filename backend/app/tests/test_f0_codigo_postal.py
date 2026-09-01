"""Pruebas F0 · AsentamientoPostal / búsqueda por código postal (SQLite).

Catálogo de SOLO LECTURA (no hay alta/edición vía API, se siembra con
`scripts/cargar_codigos_postales.py`): estas pruebas siembran un par de filas a mano y
verifican el endpoint de búsqueda — varias colonias para un mismo CP, CP inexistente
(lista vacía, no 404) y RBAC de lectura de catálogos.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.modules.catalogos.codigo_postal import AsentamientoPostal
from app.modules.catalogos.router import router as catalogos_router


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
def datos(db: Session) -> None:
    db.add_all(
        [
            AsentamientoPostal(
                asentamiento_postal_id=uuid.uuid4(),
                codigo_postal="11950",
                asentamiento="Lomas Altas",
                tipo_asentamiento="Colonia",
                municipio="Miguel Hidalgo",
                estado="Ciudad de México",
                ciudad="Ciudad de México",
                pais="MEX",
            ),
            AsentamientoPostal(
                asentamiento_postal_id=uuid.uuid4(),
                codigo_postal="06700",
                asentamiento="Roma Norte",
                tipo_asentamiento="Colonia",
                municipio="Cuauhtémoc",
                estado="Ciudad de México",
                ciudad="Ciudad de México",
                pais="MEX",
            ),
            AsentamientoPostal(
                asentamiento_postal_id=uuid.uuid4(),
                codigo_postal="06700",
                asentamiento="Roma Sur",
                tipo_asentamiento="Colonia",
                municipio="Cuauhtémoc",
                estado="Ciudad de México",
                ciudad="Ciudad de México",
                pais="MEX",
            ),
        ]
    )
    db.commit()


@pytest.fixture
def client(db: Session) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(catalogos_router, prefix="/api/v1")

    def override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _hdr(area: str) -> dict[str, str]:
    return {"X-Dev-User": "tester", "X-Dev-Area": area}


def test_un_cp_con_una_sola_colonia(client: TestClient, datos: None) -> None:
    r = client.get("/api/v1/catalogos/codigos-postales/11950", headers=_hdr("ventas"))
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["asentamiento"] == "Lomas Altas"
    assert body[0]["municipio"] == "Miguel Hidalgo"
    assert body[0]["estado"] == "Ciudad de México"
    assert body[0]["pais"] == "MEX"


def test_un_cp_con_varias_colonias_las_devuelve_todas_ordenadas(
    client: TestClient, datos: None
) -> None:
    r = client.get("/api/v1/catalogos/codigos-postales/06700", headers=_hdr("ventas"))
    assert r.status_code == 200
    body = r.json()
    assert [f["asentamiento"] for f in body] == ["Roma Norte", "Roma Sur"]


def test_cp_inexistente_devuelve_lista_vacia_no_404(client: TestClient, datos: None) -> None:
    r = client.get("/api/v1/catalogos/codigos-postales/00000", headers=_hdr("ventas"))
    assert r.status_code == 200
    assert r.json() == []


def test_area_desconocida_no_tiene_acceso(client: TestClient, datos: None) -> None:
    r = client.get("/api/v1/catalogos/codigos-postales/11950", headers=_hdr("marketing"))
    assert r.status_code in (401, 403, 422)
