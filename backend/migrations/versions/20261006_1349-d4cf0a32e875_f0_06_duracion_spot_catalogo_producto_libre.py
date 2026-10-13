"""f0 06 duracion spot catalogo producto libre

ADR-164 (petición del usuario): `producto` deja de ser el CHECK/enum compartido con
`TarifaPlaza.producto` ('spot'/'mencion'/'control_remoto'/'patrocinio') y pasa a texto
libre, para poder dar de alta productos nuevos sin otra migración — mismo espíritu que
`descripcion_duracion` desde el principio (ADR-159).

Revision ID: d4cf0a32e875
Revises: 2047cd2e1d53
Create Date: 2026-10-06 13:49:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'd4cf0a32e875'
down_revision: str | None = '2047cd2e1d53'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('duracion_spot_catalogo') as batch:
            batch.drop_constraint('ck_duracion_spot_catalogo_producto', type_='check')
            batch.alter_column(
                'producto',
                existing_type=sa.Unicode(length=20),
                type_=sa.Unicode(length=60),
            )
    else:
        op.drop_constraint(
            'ck_duracion_spot_catalogo_producto', 'duracion_spot_catalogo', type_='check'
        )
        op.alter_column(
            'duracion_spot_catalogo',
            'producto',
            existing_type=sa.Unicode(length=20),
            type_=sa.Unicode(length=60),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('duracion_spot_catalogo') as batch:
            batch.alter_column(
                'producto',
                existing_type=sa.Unicode(length=60),
                type_=sa.Unicode(length=20),
            )
            batch.create_check_constraint(
                'ck_duracion_spot_catalogo_producto',
                "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
            )
    else:
        op.alter_column(
            'duracion_spot_catalogo',
            'producto',
            existing_type=sa.Unicode(length=60),
            type_=sa.Unicode(length=20),
        )
        op.create_check_constraint(
            'ck_duracion_spot_catalogo_producto',
            'duracion_spot_catalogo',
            "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
        )
