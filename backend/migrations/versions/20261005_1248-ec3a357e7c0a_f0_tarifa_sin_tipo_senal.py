"""f0 tarifa sin tipo senal

ADR-158 (petición del usuario): se elimina `tipo_senal` de `tarifa_plaza` por completo —
es una propiedad de la ESTACIÓN (`Estacion.tipo_senal`, ya existente), no de la tarifa;
mantenerla aquí duplicada permitía capturar un tipo de señal distinto al de la estación
seleccionada, sin ningún beneficio: tanto el chequeo de "sin duplicado activo" como la
sugerencia de tarifa al capturar una OE (`_tarifa_sugerida`, `orden_estacion.py`) YA
filtraban también por `estacion_id`, que determina el tipo de señal por sí solo.

Se suelta la columna, su CHECK (`ck_tarifa_plaza_tipo_senal`) y se recompone el índice
`ix_tarifa_plaza_combo` de `(estacion_id, tipo_senal, duracion_spot, producto)` a
`(estacion_id, duracion_spot, producto)`.

Sin migración de datos: la tabla solo trae datos mock de `seed_dev.py` (ya actualizado
para no sembrar `tipo_senal`), nunca datos reales de negocio.

Revision ID: ec3a357e7c0a
Revises: c9e5f2a7d1b3
Create Date: 2026-10-05 12:48:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'ec3a357e7c0a'
down_revision: str | None = 'c9e5f2a7d1b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.drop_constraint('ck_tarifa_plaza_tipo_senal', type_='check')
            batch.drop_column('tipo_senal')
            batch.create_index(
                'ix_tarifa_plaza_combo', ['estacion_id', 'duracion_spot', 'producto']
            )
    else:
        op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
        op.drop_constraint('ck_tarifa_plaza_tipo_senal', 'tarifa_plaza', type_='check')
        op.drop_column('tarifa_plaza', 'tipo_senal')
        op.create_index(
            'ix_tarifa_plaza_combo', 'tarifa_plaza',
            ['estacion_id', 'duracion_spot', 'producto'], unique=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.add_column(
                sa.Column('tipo_senal', sa.Unicode(length=4), nullable=False, server_default='fm')
            )
            batch.create_check_constraint(
                'ck_tarifa_plaza_tipo_senal', "tipo_senal IN ('fm', 'am', 'tv')"
            )
            batch.create_index(
                'ix_tarifa_plaza_combo', ['estacion_id', 'tipo_senal', 'duracion_spot', 'producto']
            )
    else:
        op.add_column(
            'tarifa_plaza',
            sa.Column('tipo_senal', sa.Unicode(length=4), nullable=False, server_default='fm'),
        )
        op.create_check_constraint(
            'ck_tarifa_plaza_tipo_senal', 'tarifa_plaza', "tipo_senal IN ('fm', 'am', 'tv')"
        )
        op.create_index(
            'ix_tarifa_plaza_combo', 'tarifa_plaza',
            ['estacion_id', 'tipo_senal', 'duracion_spot', 'producto'], unique=False,
        )
