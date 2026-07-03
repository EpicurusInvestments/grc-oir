"""Acceso a la base de datos (SQL Server en AWS RDS), síncrono con pyodbc.

Decisión (backend/CLAUDE.md): backend SÍNCRONO. Los endpoints se declaran `def`
(FastAPI los corre en un threadpool). El engine se crea de forma perezosa: importar
este módulo NO abre conexión, por lo que la app arranca aunque RDS no sea alcanzable
(útil en local/CI sin red). La conexión real se prueba con `/health/db`.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import DateTime, Engine, create_engine
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def datetime2() -> DateTime:
    """Tipo de fecha/hora para columnas de auditoría.

    En SQL Server usa `DATETIME2` (rango y precisión modernos, recomendado por la spec);
    en otros dialectos (p.ej. SQLite en las pruebas) cae a `DATETIME`. Se devuelve una
    instancia nueva por columna para no compartir estado entre modelos.
    """
    return DateTime().with_variant(mssql.DATETIME2(), "mssql")  # type: ignore[no-untyped-call]


class Base(DeclarativeBase):
    """Base declarativa común. Cada modelo de entidad (desde F0-01) hereda de aquí."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Engine perezoso: se construye en el primer uso, no al importar."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None  # noqa: S101 — garantizado por get_engine()
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """Dependencia FastAPI: abre una sesión por request y la cierra al terminar."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
