"""f0 anunciante rfc unico y monto maximo credito

Bugs/mejoras reportadas por el usuario, con captura:

1. "Que el RFC no se repita": `Anunciante.rfc_anunciante` no tenia ninguna restriccion de
   unicidad a nivel de base de datos (a diferencia de `Afiliado.rfc_afiliado`, que SI la
   tenia desde el inicio) — se agrega el UNIQUE constraint que faltaba, como respaldo de
   la validacion ya agregada en el servicio (`AnuncianteService._verificar_rfc_unico`).

2. Nuevo campo `monto_maximo_credito` (DECIMAL 14,2, nullable, CHECK >= 0) — PARAMETRO
   SENSIBLE (mismo criterio que `dias_credito_default`: permiso por campo + bitacora en
   `LogCambioParametro`). `NULL` = sin tope capturado, no se inventa un default numerico.

Revision ID: a4b5c6d7e8f9
Revises: f1a2b3c4d5e6
Create Date: 2026-11-20 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = 'anunciante'
_UNIQUE_RFC = 'uq_anunciante_rfc'
_CHECK_MONTO = 'ck_anunciante_monto_maximo_credito'


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.add_column(sa.Column('monto_maximo_credito', sa.Numeric(14, 2), nullable=True))
            batch.create_unique_constraint(_UNIQUE_RFC, ['rfc_anunciante'])
            batch.create_check_constraint(
                _CHECK_MONTO, 'monto_maximo_credito IS NULL OR monto_maximo_credito >= 0'
            )
    else:
        op.add_column(_TABLA, sa.Column('monto_maximo_credito', sa.Numeric(14, 2), nullable=True))
        op.create_unique_constraint(_UNIQUE_RFC, _TABLA, ['rfc_anunciante'])
        op.create_check_constraint(
            _CHECK_MONTO, _TABLA, 'monto_maximo_credito IS NULL OR monto_maximo_credito >= 0'
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.drop_constraint(_CHECK_MONTO, type_='check')
            batch.drop_constraint(_UNIQUE_RFC, type_='unique')
            batch.drop_column('monto_maximo_credito')
    else:
        op.drop_constraint(_CHECK_MONTO, _TABLA, type_='check')
        op.drop_constraint(_UNIQUE_RFC, _TABLA, type_='unique')
        op.drop_column(_TABLA, 'monto_maximo_credito')
