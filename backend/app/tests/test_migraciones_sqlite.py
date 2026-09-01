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


def test_el_indice_filtrado_sobrevive_al_batch_mode(url_temporal: str) -> None:
    """El batch mode RECREA la tabla; el índice único filtrado de ADR-047 debe seguir vivo.

    Sin su cláusula `WHERE` se perdería la mitad de la decisión de negocio: una OC cuya
    factura fue cancelada volvería a quedar bloqueada para refacturarse.
    """
    import sqlalchemy as sa

    assert _alembic("upgrade", "head", url=url_temporal).returncode == 0

    eng = sa.create_engine(url_temporal)
    with eng.connect() as con:
        ddl = con.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = 'uq_factura_cliente_orden_vigente'"
        ).scalar()

    assert ddl is not None, "el índice único filtrado desapareció"
    assert "WHERE" in ddl.upper(), f"el índice perdió su cláusula WHERE: {ddl}"
