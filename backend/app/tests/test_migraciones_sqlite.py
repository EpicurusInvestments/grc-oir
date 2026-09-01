"""Las migraciones tienen que correr en SQLite, no solo en SQL Server (ADR-063).

Por qué existe este archivo: el resto de la suite monta el esquema con
`Base.metadata.create_all` (ver `conftest.py`), así que **nunca ejecuta las migraciones**.
Ese punto ciego dejó pasar una migración que funcionaba en RDS pero rompía el arranque
local (`op.drop_constraint` no existe en SQLite), con las 408 pruebas en verde.

Se corre `alembic` en un SUBPROCESO a propósito: `migrations/env.py` lee la URL de
`settings`, que ya está importado y cacheado en el proceso de pytest, así que dentro del
mismo proceso no se puede apuntar a otra base.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def _alembic(*args: str, url: str) -> subprocess.CompletedProcess[str]:
    entorno = {**os.environ, "DATABASE_URL": url, "APP_ENV": "development"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=RAIZ,
        env=entorno,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def url_temporal(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'migraciones.db'}"


def test_upgrade_head_desde_una_base_vacia(url_temporal: str) -> None:
    """La cadena completa corre en SQLite: es lo que hace quien clona el repo."""
    r = _alembic("upgrade", "head", url=url_temporal)
    assert r.returncode == 0, f"alembic upgrade head falló:\n{r.stderr}"

    actual = _alembic("current", url=url_temporal)
    assert "(head)" in actual.stdout, f"no quedó en head:\n{actual.stdout}{actual.stderr}"


def test_viaje_redondo_de_la_ultima_migracion(url_temporal: str) -> None:
    """`downgrade` y `upgrade` de la punta: un downgrade roto solo se ve al usarlo."""
    assert _alembic("upgrade", "head", url=url_temporal).returncode == 0

    abajo = _alembic("downgrade", "-1", url=url_temporal)
    assert abajo.returncode == 0, f"downgrade -1 falló:\n{abajo.stderr}"

    arriba = _alembic("upgrade", "head", url=url_temporal)
    assert arriba.returncode == 0, f"re-upgrade falló:\n{arriba.stderr}"


def test_los_check_de_factura_cliente_sobreviven_al_batch_mode(url_temporal: str) -> None:
    """El batch mode RECREA la tabla: hay que verificar qué se lleva por delante.

    Las migraciones `55d7f36d93fd` y `5da59f306b51` reconstruyen `factura_cliente` en
    SQLite. Sus CHECK son invariantes de dinero (ADR-039): que el total sea la suma, que el
    IVA sea el 16 % del subtotal, que ningún importe sea negativo. Si una recreación se
    llevara uno, la base aceptaría en silencio facturas descuadradas.

    (Hasta ADR-064 esta prueba vigilaba el índice único filtrado `uq_factura_cliente_orden_
    vigente`; esa columna ya no existe y la regla que protegía vive ahora en el servicio.)
    """
    import sqlalchemy as sa

    assert _alembic("upgrade", "head", url=url_temporal).returncode == 0

    eng = sa.create_engine(url_temporal)
    with eng.connect() as con:
        ddl = con.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'factura_cliente'"
        ).scalar()

    assert ddl is not None, "la tabla factura_cliente desapareció"
    for constraint in (
        "ck_factura_cliente_total_suma",
        "ck_factura_cliente_iva_calculado",
        "ck_factura_cliente_subtotal",
        "ck_factura_cliente_periodo",
        "ck_factura_cliente_estado",
    ):
        assert constraint in ddl, f"la recreación de tabla se llevó {constraint}"


def test_la_relacion_con_ordenes_queda_en_la_tabla_puente(url_temporal: str) -> None:
    """ADR-064: `factura_cliente.orden_id` desaparece y la relación pasa a ser N:M."""
    import sqlalchemy as sa

    assert _alembic("upgrade", "head", url=url_temporal).returncode == 0

    eng = sa.create_engine(url_temporal)
    with eng.connect() as con:
        columnas = [
            fila[1]
            for fila in con.exec_driver_sql("PRAGMA table_info(factura_cliente)").fetchall()
        ]
        puente = con.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'factura_cliente_orden'"
        ).scalar()
        indice = con.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE name = 'ix_factura_cliente_orden_orden'"
        ).scalar()

    assert "orden_id" not in columnas, "factura_cliente todavía tiene la columna orden_id"
    assert puente is not None, "falta la tabla puente factura_cliente_orden"
    assert indice is not None, "falta el índice sobre factura_cliente_orden.orden_id"
