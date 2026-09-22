"""f0 02 tarifa por estacion

ADR-097 (petición del usuario): el catálogo de Tarifas deja de capturar vigencia y de
referenciar Plaza:

- Se eliminan `vigencia_desde`/`vigencia_hasta` (y su CHECK `ck_tarifa_plaza_vigencia`) —
  ya no hay periodos de vigencia ni validación de solapamiento de fechas.
- `plaza_id` se reemplaza por `estacion_id` (FK a `estacion.estacion_id`) — "Nombre de la
  emisora" en vez de "Plaza". La FK y el índice de `plaza_id` SÍ tenían nombre explícito
  (`fk_tarifa_plaza_plaza`/`ix_tarifa_plaza_plaza_id`, definidos en `b73f13de1b80`), así
  que se sueltan por nombre directo — a diferencia de la FK de `afiliado.plaza_id`
  (ADR-096), que era anónima y requirió descubrimiento dinámico.
- Se agrega `producto` (NUEVO, fuera de la spec BD v2): `spot│mencion│control_remoto│
  patrocinio`, CHECK `ck_tarifa_plaza_producto`.
- El índice compuesto `ix_tarifa_plaza_combo` pasa de
  `(plaza_id, tipo_senal, duracion_spot)` a `(estacion_id, tipo_senal, duracion_spot,
  producto)` — misma combinación que ahora usa la regla "sin duplicado activo" que
  reemplaza a "sin solapamiento" (ya no hay fechas que solapar).

Sin migración de datos: no existe un mapeo 1:1 determinista de plaza→estación para las
filas existentes (una plaza tiene N estaciones), y esta tabla solo trae datos de
`seed_dev.py` (mock, reseedable) — nunca datos reales de negocio. Se vacía la tabla antes
de recomponer las columnas; `seed_dev.py` ya se actualizó para sembrar por estación.

Revision ID: 96798afba3cc
Revises: a12fc26a6504
Create Date: 2026-09-21 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '96798afba3cc'
down_revision: str | None = 'a12fc26a6504'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Datos mock únicamente (ver nota arriba) — se vacía antes de recomponer columnas.
    op.execute('DELETE FROM tarifa_plaza')

    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.drop_constraint('ck_tarifa_plaza_vigencia', type_='check')
            batch.drop_column('vigencia_desde')
            batch.drop_column('vigencia_hasta')
            batch.drop_constraint('fk_tarifa_plaza_plaza', type_='foreignkey')
            batch.drop_index('ix_tarifa_plaza_plaza_id')
            batch.drop_column('plaza_id')
            batch.add_column(sa.Column('estacion_id', sa.Uuid(), nullable=False))
            batch.create_foreign_key(
                'fk_tarifa_plaza_estacion', 'estacion', ['estacion_id'], ['estacion_id']
            )
            batch.create_index('ix_tarifa_plaza_estacion_id', ['estacion_id'])
            batch.add_column(sa.Column('producto', sa.Unicode(length=20), nullable=False))
            batch.create_check_constraint(
                'ck_tarifa_plaza_producto',
                "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
            )
            batch.create_index(
                'ix_tarifa_plaza_combo',
                ['estacion_id', 'tipo_senal', 'duracion_spot', 'producto'],
            )
    else:
        op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
        op.drop_constraint('ck_tarifa_plaza_vigencia', 'tarifa_plaza', type_='check')
        op.drop_column('tarifa_plaza', 'vigencia_desde')
        op.drop_column('tarifa_plaza', 'vigencia_hasta')
        op.drop_constraint('fk_tarifa_plaza_plaza', 'tarifa_plaza', type_='foreignkey')
        op.drop_index('ix_tarifa_plaza_plaza_id', table_name='tarifa_plaza')
        op.drop_column('tarifa_plaza', 'plaza_id')
        op.add_column('tarifa_plaza', sa.Column('estacion_id', sa.Uuid(), nullable=False))
        op.create_foreign_key(
            'fk_tarifa_plaza_estacion', 'tarifa_plaza', 'estacion',
            ['estacion_id'], ['estacion_id'],
        )
        op.create_index(
            op.f('ix_tarifa_plaza_estacion_id'), 'tarifa_plaza', ['estacion_id'], unique=False
        )
        op.add_column(
            'tarifa_plaza', sa.Column('producto', sa.Unicode(length=20), nullable=False)
        )
        op.create_check_constraint(
            'ck_tarifa_plaza_producto',
            'tarifa_plaza',
            "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
        )
        op.create_index(
            'ix_tarifa_plaza_combo', 'tarifa_plaza',
            ['estacion_id', 'tipo_senal', 'duracion_spot', 'producto'], unique=False,
        )


def downgrade() -> None:
    # Mismo criterio que ADR-096: no hay datos que preservar (ver nota arriba), así que las
    # columnas restauradas quedan nullable en vez de reconstruir vigencias inventadas.
    op.execute('DELETE FROM tarifa_plaza')

    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('tarifa_plaza') as batch:
            batch.drop_index('ix_tarifa_plaza_combo')
            batch.drop_constraint('ck_tarifa_plaza_producto', type_='check')
            batch.drop_column('producto')
            batch.drop_constraint('fk_tarifa_plaza_estacion', type_='foreignkey')
            batch.drop_index('ix_tarifa_plaza_estacion_id')
            batch.drop_column('estacion_id')
            batch.add_column(sa.Column('plaza_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_tarifa_plaza_plaza', 'plaza', ['plaza_id'], ['plaza_id']
            )
            batch.create_index('ix_tarifa_plaza_plaza_id', ['plaza_id'])
            batch.add_column(sa.Column('vigencia_desde', sa.Date(), nullable=True))
            batch.add_column(sa.Column('vigencia_hasta', sa.Date(), nullable=True))
            batch.create_check_constraint(
                'ck_tarifa_plaza_vigencia', 'vigencia_hasta >= vigencia_desde'
            )
            batch.create_index(
                'ix_tarifa_plaza_combo', ['plaza_id', 'tipo_senal', 'duracion_spot']
            )
    else:
        op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
        op.drop_constraint('ck_tarifa_plaza_producto', 'tarifa_plaza', type_='check')
        op.drop_column('tarifa_plaza', 'producto')
        op.drop_constraint('fk_tarifa_plaza_estacion', 'tarifa_plaza', type_='foreignkey')
        op.drop_index('ix_tarifa_plaza_estacion_id', table_name='tarifa_plaza')
        op.drop_column('tarifa_plaza', 'estacion_id')
        op.add_column('tarifa_plaza', sa.Column('plaza_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_tarifa_plaza_plaza', 'tarifa_plaza', 'plaza', ['plaza_id'], ['plaza_id']
        )
        op.create_index(
            op.f('ix_tarifa_plaza_plaza_id'), 'tarifa_plaza', ['plaza_id'], unique=False
        )
        op.add_column('tarifa_plaza', sa.Column('vigencia_desde', sa.Date(), nullable=True))
        op.add_column('tarifa_plaza', sa.Column('vigencia_hasta', sa.Date(), nullable=True))
        op.create_check_constraint(
            'ck_tarifa_plaza_vigencia', 'tarifa_plaza', 'vigencia_hasta >= vigencia_desde'
        )
        op.create_index(
            'ix_tarifa_plaza_combo', 'tarifa_plaza',
            ['plaza_id', 'tipo_senal', 'duracion_spot'], unique=False,
        )
