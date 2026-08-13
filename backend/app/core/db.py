"""Acceso a la base de datos (SQL Server en AWS RDS, o SQLite local — ver ADR-028),
síncrono con pyodbc.

Decisión (backend/CLAUDE.md): backend SÍNCRONO. Los endpoints se declaran `def`
(FastAPI los corre en un threadpool). El engine se crea de forma perezosa: importar
este módulo NO abre conexión, por lo que la app arranca aunque RDS no sea alcanzable
(útil en local/CI sin red). La conexión real se prueba con `/health/db`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from sqlalchemy import Date, DateTime, Engine, Time, UnicodeText, create_engine
from sqlalchemy.dialects import mssql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def url_enmascarada(url_cruda: str) -> str:
    """Render seguro de `url_cruda`, contraseña SIEMPRE oculta — usar antes de
    imprimir/loguear una URL de conexión, nunca `str(url)`/`settings.sqlalchemy_url`
    directo.

    `URL.render_as_string(hide_password=True)` de SQLAlchemy solo enmascara el
    componente `password` ESTRUCTURADO de la URL (`user:password@host`). Pero
    `Settings.sqlalchemy_url` empaqueta TODA la cadena de conexión de SQL Server
    dentro de un solo parámetro de query `odbc_connect=...` (necesario por el guion
    de "GRC-OIR") — ahí `hide_password` no ve nada que enmascarar y el `PWD=...` de
    ese connect string pasa de largo, en claro (incidente real de la auditoría de
    migración a RDS, F1: `scripts/seed_dev.py` imprimía la URL cruda). Por eso, si
    existe `odbc_connect` en la query, se enmascara el `PWD=` DENTRO de ese string
    ANTES de renderizar, no después.
    """
    url = make_url(url_cruda)
    odbc_connect = url.query.get("odbc_connect")
    if odbc_connect:
        odbc_enmascarado = re.sub(r"(?i)PWD=[^;]*", "PWD=***", str(odbc_connect))
        url = url.set(query={**url.query, "odbc_connect": odbc_enmascarado})
    return url.render_as_string(hide_password=True)


def datetime2() -> DateTime:
    """Tipo de fecha/hora para columnas de auditoría.

    En SQL Server usa `DATETIME2` (rango y precisión modernos, recomendado por la spec);
    en otros dialectos (p.ej. SQLite en las pruebas) cae a `DATETIME`. Se devuelve una
    instancia nueva por columna para no compartir estado entre modelos.
    """
    return DateTime().with_variant(mssql.DATETIME2(), "mssql")  # type: ignore[no-untyped-call]


def fecha_sql() -> Date:
    """Tipo de fecha (sin hora) — `DATE` nativo en SQL Server, explícito.

    Auditoría de migración a RDS (F1, Tanda 4): sin este `.with_variant`, un `sa.Date()`
    a secas SOLO compila a `DATE` en `mssql` cuando el dialecto detecta la versión real
    del servidor (vía una conexión viva) — en modo offline (`alembic ... --sql`, sin
    conexión) cae a `DATETIME` legado (compatible con SQL Server pre-2008), lo cual
    hace que el SQL generado en ese modo NO sea un preview fiel de lo que realmente se
    crea. Forzar el tipo explícitamente (mismo patrón que `datetime2()`) elimina esa
    dependencia de detección de versión — el mismo tipo de comportamiento implícito
    que ya costó un bug real en ADR-014 (`.is_(True)` sobre BIT). En SQLite cae a `DATE`
    sin cambios.
    """
    return Date().with_variant(mssql.DATE(), "mssql")


def hora_sql() -> Time:
    """Tipo de hora (sin fecha) — `TIME` nativo en SQL Server, explícito.

    Mismo razonamiento que `fecha_sql()`: sin `.with_variant`, `sa.Time()` a secas cae a
    `DATETIME` en modo offline por falta de detección de versión.
    """
    return Time().with_variant(mssql.TIME(), "mssql")  # type: ignore[no-untyped-call]


def texto_largo() -> UnicodeText:
    """Tipo de texto largo — `NVARCHAR(MAX)` explícito en SQL Server.

    Auditoría de migración a RDS (F1, Tanda 4): `sa.UnicodeText()`/`Text()` a secas
    compila a `NTEXT` en el dialecto `mssql` (mapeo por defecto, INCONDICIONAL — no es
    un artefacto de modo offline como `fecha_sql()`/`hora_sql()`, pasa igual online).
    `NTEXT` está deprecado por Microsoft desde hace años (aunque sigue soportado) y no
    funciona bien con funciones de cadena modernas ni con Full-Text Search — problema
    real para columnas de texto libre que se buscan/reportan (F4). Se fuerza
    `NVARCHAR(MAX)` explícito, mismo patrón que `datetime2()`. En SQLite cae a `TEXT`
    sin cambios.
    """
    return UnicodeText().with_variant(mssql.NVARCHAR(None), "mssql")


class Base(DeclarativeBase):
    """Base declarativa común. Cada modelo de entidad (desde F0-01) hereda de aquí."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Engine perezoso: se construye en el primer uso, no al importar.

    SQLite (`settings.database_url` seteada, ADR-028) necesita `check_same_thread=False`
    porque FastAPI sirve cada request en un hilo del threadpool distinto. Contra SQL
    Server se conserva `pool_pre_ping` (detecta conexiones RDS caídas/reiniciadas).
    """
    global _engine, _SessionLocal
    if _engine is None:
        url = settings.sqlalchemy_url
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
        else:
            _engine = create_engine(url, pool_pre_ping=True, future=True)
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
