"""Fixtures de pruebas.

Usamos SQLite en memoria (StaticPool, una conexión compartida) para ejercitar la base
genérica de catálogos sin depender de SQL Server / red. La app real apunta a RDS; aquí
solo validamos la mecánica (paginación, filtros, baja lógica, RBAC).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.errors import register_error_handlers
from app.modules.catalogos.base_repository import BaseRepository
from app.modules.catalogos.crud_router import build_crud_router
from app.tests._demo import (
    CatalogoDemo,
    DemoCreate,
    DemoRead,
    DemoService,
    DemoUpdate,
)


@pytest.fixture
def engine():  # type: ignore[no-untyped-def]
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # En F0-00 Base.metadata solo contiene la entidad de juguete (no hay modelos reales).
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)


@pytest.fixture
def session_local(engine):  # type: ignore[no-untyped-def]
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db_session(session_local) -> Iterator[Session]:  # type: ignore[no-untyped-def]
    session = session_local()
    try:
        yield session
    finally:
        session.close()


def _demo_repo(db: Session) -> BaseRepository[CatalogoDemo]:
    return BaseRepository(db, CatalogoDemo, search_columns=[CatalogoDemo.nombre])


@pytest.fixture
def demo_service(db_session: Session) -> DemoService:
    return DemoService(_demo_repo(db_session))


@pytest.fixture
def app(session_local) -> FastAPI:  # type: ignore[no-untyped-def]
    application = FastAPI()
    register_error_handlers(application)

    def get_demo_service(db: Session = Depends(get_db)) -> DemoService:
        return DemoService(_demo_repo(db))

    application.include_router(
        build_crud_router(
            prefix="/demo",
            tags=["demo"],
            permiso_base="catalogos",
            read_schema=DemoRead,
            create_schema=DemoCreate,
            update_schema=DemoUpdate,
            get_service=get_demo_service,
        ),
        prefix="/api/v1",
    )

    def override_get_db() -> Iterator[Session]:
        session = session_local()
        try:
            yield session
        finally:
            session.close()

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
