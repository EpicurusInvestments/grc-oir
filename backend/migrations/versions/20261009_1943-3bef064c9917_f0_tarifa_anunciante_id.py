"""f0 tarifa anunciante_id

ADR-177 (petición del usuario): agrega `anunciante_id` (FK a `anunciante`) a
`tarifa_plaza` — la llave de "sin duplicado activo" pasa de (estación+duración+
producto) a (ANUNCIANTE+estación+duración+producto).

Columna NULLABLE a nivel de base: las tarifas capturadas ANTES de este ADR no tienen
(ni se les puede adivinar) un Anunciante real — en vez de inventarles uno, esta
migración las DESACTIVA (`activo = 0`); `TarifaPlazaCreate.anunciante_id` sí lo exige
(sin default) para cualquier tarifa nueva de aquí en adelante, y el servicio bloquea
reactivar una tarifa legado sin Anunciante asignado primero.

El índice de combinación (`ix_tarifa_plaza_combo`) se recompone con `anunciante_id`
como primera columna.

Revision ID: 3bef064c9917
Revises: b8abcebf5d8b
Create Date: 2026-10-09 19:43:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '3bef064c9917'
down_revision: str | None = 'b8abcebf5d8b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'tarifa_plaza',
        sa.Column('anunciante_id', sa.Uuid(), nullable=True),
    )
    op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.create_foreign_key(
                'fk_tarifa_plaza_anunciante_id',
                'anunciante',
                ['anunciante_id'],
                ['anunciante_id'],
            )
            batch.create_index(
                'ix_tarifa_plaza_anunciante_id', ['anunciante_id']
            )
            batch.create_index(
                'ix_tarifa_plaza_combo',
                ['anunciante_id', 'estacion_id', 'duracion_spot', 'producto'],
            )
    else:
        op.create_foreign_key(
            'fk_tarifa_plaza_anunciante_id',
            'tarifa_plaza',
            'anunciante',
            ['anunciante_id'],
            ['anunciante_id'],
        )
        op.create_index('ix_tarifa_plaza_anunciante_id', 'tarifa_plaza', ['anunciante_id'])
        op.create_index(
            'ix_tarifa_plaza_combo',
            'tarifa_plaza',
            ['anunciante_id', 'estacion_id', 'duracion_spot', 'producto'],
        )

    # ADR-177 (petición del usuario, confirmado vía AskUserQuestion): las tarifas que ya
    # existían no tienen Anunciante y no se les puede asignar uno de forma confiable —
    # se desactivan en vez de inventarles un valor. Quedan visibles con el filtro
    # "Inactivas"; se reactivan editándolas para asignarles su Anunciante real.
    op.execute('UPDATE tarifa_plaza SET activo = 0')


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.drop_index('ix_tarifa_plaza_anunciante_id')
            batch.drop_constraint('fk_tarifa_plaza_anunciante_id', type_='foreignkey')
            batch.drop_column('anunciante_id')
            batch.create_index(
                'ix_tarifa_plaza_combo', ['estacion_id', 'duracion_spot', 'producto']
            )
    else:
        op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
        op.drop_index('ix_tarifa_plaza_anunciante_id', table_name='tarifa_plaza')
        op.drop_constraint('fk_tarifa_plaza_anunciante_id', 'tarifa_plaza', type_='foreignkey')
        op.drop_column('tarifa_plaza', 'anunciante_id')
        op.create_index(
            'ix_tarifa_plaza_combo',
            'tarifa_plaza',
            ['estacion_id', 'duracion_spot', 'producto'],
        )
    # Nota: NO se revierte el `activo = 0` de la migración de datos (no se registró qué
    # filas estaban activas antes) — mismo criterio que otras migraciones de este
    # proyecto que solo revierten esquema, no estado de negocio.
