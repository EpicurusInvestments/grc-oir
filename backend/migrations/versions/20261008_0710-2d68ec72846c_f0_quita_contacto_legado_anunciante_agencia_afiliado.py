"""f0 quita contacto legado anunciante agencia afiliado

ADR-174 (petición del usuario, reporte de bug): se elimina por completo el contacto
plano legado (`contacto_nombre`/`contacto_email`/`contacto_telefono`) de `anunciante`,
`agencia` y `afiliado` — ADR-091/092/094 ya lo habían retirado de los formularios de
alta/edición y lo dejaban de solo lectura ("Legado") en el detalle, pero el usuario lo
reportó como funcionalidad vieja confusa coexistiendo con la lista nueva de Contactos
(`contacto_anunciante`/`contacto_agencia`/`contacto_afiliado`, que NO se tocan aquí).

Único consumidor real detectado (`CobranzaFacturasPage.tsx`, "Contacto cobranza") se
migró a leer el primer `ContactoAnunciante` activo antes de esta migración.

Sin backfill: ADR-091/092/094 nunca migraron estos datos a las tablas de Contactos
nuevas, y el usuario no lo pidió aquí tampoco — se asumen datos de prueba (DB de
desarrollo), no datos reales de negocio.

Revision ID: 2d68ec72846c
Revises: 1531edf8c6dc
Create Date: 2026-10-08 07:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '2d68ec72846c'
down_revision: str | None = '1531edf8c6dc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLAS_Y_COLUMNAS = {
    'anunciante': ['contacto_nombre', 'contacto_email', 'contacto_telefono'],
    'agencia': ['contacto_nombre', 'contacto_email', 'contacto_telefono'],
    'afiliado': ['contacto_nombre', 'contacto_email', 'contacto_telefono'],
}

# Tipos originales (para el downgrade) — mismos de los 3 modelos antes de ADR-174.
_TIPOS = {
    'contacto_nombre': sa.Unicode(length=160),
    'contacto_email': sa.Unicode(length=160),
    'contacto_telefono': sa.Unicode(length=40),
}


def upgrade() -> None:
    es_sqlite = op.get_bind().dialect.name == 'sqlite'
    for tabla, columnas in _TABLAS_Y_COLUMNAS.items():
        if es_sqlite:
            with op.batch_alter_table(tabla) as batch:
                for columna in columnas:
                    batch.drop_column(columna)
        else:
            for columna in columnas:
                op.drop_column(tabla, columna)


def downgrade() -> None:
    es_sqlite = op.get_bind().dialect.name == 'sqlite'
    for tabla, columnas in _TABLAS_Y_COLUMNAS.items():
        if es_sqlite:
            with op.batch_alter_table(tabla) as batch:
                for columna in columnas:
                    batch.add_column(sa.Column(columna, _TIPOS[columna], nullable=True))
        else:
            for columna in columnas:
                op.add_column(tabla, sa.Column(columna, _TIPOS[columna], nullable=True))
