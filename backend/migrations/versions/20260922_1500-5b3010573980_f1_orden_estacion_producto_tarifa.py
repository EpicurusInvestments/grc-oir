"""f1 orden_estacion producto_tarifa

ADR-102 (petición del usuario) — Fase 2 del rediseño "Asignar estaciones": nueva columna
`producto_tarifa` en `orden_estacion` (`ProductoTarifa` del catálogo Tarifa —
`spot│mencion│control_remoto│patrocinio`, ADR-097), elegida por estación. Nullable: las
filas sembradas antes de esta fase no la tienen; `OrdenEstacionCreate` sí la exige para
las capturas nuevas. NO se toca la columna `producto` ya existente (esa es "Campaña",
texto libre heredado de OrdenCliente.producto — concepto distinto).

Revision ID: 5b3010573980
Revises: 51d8601f7779
Create Date: 2026-09-22 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '5b3010573980'
down_revision: str | None = '51d8601f7779'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'orden_estacion',
        sa.Column('producto_tarifa', sa.Unicode(length=20), nullable=True),
    )
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.create_check_constraint(
                'ck_orden_estacion_producto_tarifa',
                "producto_tarifa IS NULL OR producto_tarifa IN "
                "('spot', 'mencion', 'control_remoto', 'patrocinio')",
            )
    else:
        op.create_check_constraint(
            'ck_orden_estacion_producto_tarifa',
            'orden_estacion',
            "producto_tarifa IS NULL OR producto_tarifa IN "
            "('spot', 'mencion', 'control_remoto', 'patrocinio')",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.drop_constraint('ck_orden_estacion_producto_tarifa', type_='check')
            batch.drop_column('producto_tarifa')
    else:
        op.drop_constraint(
            'ck_orden_estacion_producto_tarifa', 'orden_estacion', type_='check'
        )
        op.drop_column('orden_estacion', 'producto_tarifa')
