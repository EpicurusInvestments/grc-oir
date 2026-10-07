"""f0 tarifa producto duracion texto libre

ADR-166 (petición del usuario): `tarifa_plaza.producto` y `tarifa_plaza.duracion_spot`
dejan de ser los CHECK/enum cerrados (`spot|mencion|control_remoto|patrocinio` /
`20s|30s|60s`) y pasan a texto libre, para capturarse eligiendo del catálogo
`duracion_spot_catalogo` ("Producto Duración") en vez de un selector fijo. Se ensanchan
ambas columnas a `Unicode(60)` (mismo ancho que ese catálogo). El índice
`ix_tarifa_plaza_combo` se recompone igual (mismas columnas, sin cambio de forma).

Sin migración de datos: los valores ya capturados con el enum anterior siguen siendo
cadenas válidas, solo dejan de ser las únicas posibles.

Revision ID: f4c9c5db55eb
Revises: d4cf0a32e875
Create Date: 2026-10-06 14:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'f4c9c5db55eb'
down_revision: str | None = 'd4cf0a32e875'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.drop_constraint('ck_tarifa_plaza_duracion_spot', type_='check')
            batch.drop_constraint('ck_tarifa_plaza_producto', type_='check')
            batch.alter_column(
                'duracion_spot', existing_type=sa.Unicode(length=10), type_=sa.Unicode(length=60)
            )
            batch.alter_column(
                'producto', existing_type=sa.Unicode(length=20), type_=sa.Unicode(length=60)
            )
            batch.create_index(
                'ix_tarifa_plaza_combo', ['estacion_id', 'duracion_spot', 'producto']
            )
    else:
        op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
        op.drop_constraint('ck_tarifa_plaza_duracion_spot', 'tarifa_plaza', type_='check')
        op.drop_constraint('ck_tarifa_plaza_producto', 'tarifa_plaza', type_='check')
        op.alter_column(
            'tarifa_plaza', 'duracion_spot',
            existing_type=sa.Unicode(length=10), type_=sa.Unicode(length=60),
        )
        op.alter_column(
            'tarifa_plaza', 'producto',
            existing_type=sa.Unicode(length=20), type_=sa.Unicode(length=60),
        )
        op.create_index(
            'ix_tarifa_plaza_combo', 'tarifa_plaza',
            ['estacion_id', 'duracion_spot', 'producto'], unique=False,
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.alter_column(
                'duracion_spot', existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=10)
            )
            batch.alter_column(
                'producto', existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=20)
            )
            batch.create_check_constraint(
                'ck_tarifa_plaza_duracion_spot', "duracion_spot IN ('20s', '30s', '60s')"
            )
            batch.create_check_constraint(
                'ck_tarifa_plaza_producto',
                "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
            )
            batch.create_index(
                'ix_tarifa_plaza_combo', ['estacion_id', 'duracion_spot', 'producto']
            )
    else:
        op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
        op.alter_column(
            'tarifa_plaza', 'duracion_spot',
            existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=10),
        )
        op.alter_column(
            'tarifa_plaza', 'producto',
            existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=20),
        )
        op.create_check_constraint(
            'ck_tarifa_plaza_duracion_spot', 'tarifa_plaza', "duracion_spot IN ('20s', '30s', '60s')"
        )
        op.create_check_constraint(
            'ck_tarifa_plaza_producto', 'tarifa_plaza',
            "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
        )
        op.create_index(
            'ix_tarifa_plaza_combo', 'tarifa_plaza',
            ['estacion_id', 'duracion_spot', 'producto'], unique=False,
        )
