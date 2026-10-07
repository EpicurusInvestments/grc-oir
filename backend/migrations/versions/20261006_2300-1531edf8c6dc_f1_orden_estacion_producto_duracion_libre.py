"""f1 orden estacion producto duracion libre

ADR-169 (petición del usuario): "Orden de Transmisión" (OrdenEstacion) conecta
`producto_tarifa`/`duracion_spot` al catálogo `DuracionSpotCatalogo` ("Producto
Duración", F0-06), mismo patrón que Tarifa (ADR-166) y OrdenCliente (ADR-167/168). Se
quitan los CHECK `ck_orden_estacion_duracion_spot` (`20s|30s|60s`) y
`ck_orden_estacion_producto_tarifa` (`spot|mencion|control_remoto|patrocinio`); ambas
columnas se ensanchan a `Unicode(60)` y `duracion_spot` se vuelve NULLABLE (antes NOT
NULL) — `producto_tarifa` ya era nullable desde ADR-102 (filas sembradas antes de esa
fase).

Sin migración de datos: los valores ya capturados con el enum anterior siguen siendo
cadenas válidas.

Revision ID: 1531edf8c6dc
Revises: 94ad93d7c96d
Create Date: 2026-10-06 23:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '1531edf8c6dc'
down_revision: str | None = '94ad93d7c96d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.drop_constraint('ck_orden_estacion_duracion_spot', type_='check')
            batch.drop_constraint('ck_orden_estacion_producto_tarifa', type_='check')
            batch.alter_column(
                'duracion_spot',
                existing_type=sa.Unicode(length=10),
                type_=sa.Unicode(length=60),
                nullable=True,
            )
            batch.alter_column(
                'producto_tarifa',
                existing_type=sa.Unicode(length=20),
                type_=sa.Unicode(length=60),
            )
    else:
        op.drop_constraint('ck_orden_estacion_duracion_spot', 'orden_estacion', type_='check')
        op.drop_constraint('ck_orden_estacion_producto_tarifa', 'orden_estacion', type_='check')
        op.alter_column(
            'orden_estacion', 'duracion_spot',
            existing_type=sa.Unicode(length=10), type_=sa.Unicode(length=60),
            nullable=True,
        )
        op.alter_column(
            'orden_estacion', 'producto_tarifa',
            existing_type=sa.Unicode(length=20), type_=sa.Unicode(length=60),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.alter_column(
                'duracion_spot',
                existing_type=sa.Unicode(length=60),
                type_=sa.Unicode(length=10),
                nullable=False,
            )
            batch.alter_column(
                'producto_tarifa',
                existing_type=sa.Unicode(length=60),
                type_=sa.Unicode(length=20),
            )
            batch.create_check_constraint(
                'ck_orden_estacion_duracion_spot', "duracion_spot IN ('20s', '30s', '60s')"
            )
            batch.create_check_constraint(
                'ck_orden_estacion_producto_tarifa',
                "producto_tarifa IS NULL OR producto_tarifa IN "
                "('spot', 'mencion', 'control_remoto', 'patrocinio')",
            )
    else:
        op.alter_column(
            'orden_estacion', 'duracion_spot',
            existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=10),
            nullable=False,
        )
        op.alter_column(
            'orden_estacion', 'producto_tarifa',
            existing_type=sa.Unicode(length=60), type_=sa.Unicode(length=20),
        )
        op.create_check_constraint(
            'ck_orden_estacion_duracion_spot', 'orden_estacion',
            "duracion_spot IN ('20s', '30s', '60s')",
        )
        op.create_check_constraint(
            'ck_orden_estacion_producto_tarifa', 'orden_estacion',
            "producto_tarifa IS NULL OR producto_tarifa IN "
            "('spot', 'mencion', 'control_remoto', 'patrocinio')",
        )
