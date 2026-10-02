"""f1 sin vobo y pct oir negativo

ADR-100/ADR-101 (petición del usuario): dos cambios de F1 — "Orden de Servicio"
(OrdenCliente) y "Orden de Transmisión" (OrdenEstacion):

- Se elimina por completo el checklist de Vo.Bo. (`orden_cliente_vobo_item`, ADR-033):
  la orden ya no pasa por una transición `recibida → capturada` gateada por un
  checklist — se guarda y queda directo en `capturada`. Sin migración de datos: solo
  existían filas de bitácora del checklist (`completado`/`usuario_id`/
  `fecha_completado`), sin ningún otro dato colgando de ellas.
- Se relaja `ck_orden_estacion_pct_oir` (quita el piso de 0, conserva el tope de 100) y
  se eliminan `ck_orden_estacion_importe_oir`/`ck_orden_estacion_iva_oir`/
  `ck_orden_estacion_total_oir` (ya no exigen `>= 0`): ahora que se permite que
  `precio_spot` supere `OrdenCliente.precio_unitario`, el margen OIR puede ser negativo.

Revision ID: 51d8601f7779
Revises: 8fb8151c75c3
Create Date: 2026-09-22 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '51d8601f7779'
down_revision: str | None = '8fb8151c75c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table('orden_cliente_vobo_item')

    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.drop_constraint('ck_orden_estacion_pct_oir', type_='check')
            batch.drop_constraint('ck_orden_estacion_importe_oir', type_='check')
            batch.drop_constraint('ck_orden_estacion_iva_oir', type_='check')
            batch.drop_constraint('ck_orden_estacion_total_oir', type_='check')
            batch.create_check_constraint(
                'ck_orden_estacion_pct_oir', 'porcentaje_participacion_oir <= 100'
            )
    else:
        op.drop_constraint('ck_orden_estacion_pct_oir', 'orden_estacion', type_='check')
        op.drop_constraint('ck_orden_estacion_importe_oir', 'orden_estacion', type_='check')
        op.drop_constraint('ck_orden_estacion_iva_oir', 'orden_estacion', type_='check')
        op.drop_constraint('ck_orden_estacion_total_oir', 'orden_estacion', type_='check')
        op.create_check_constraint(
            'ck_orden_estacion_pct_oir', 'orden_estacion', 'porcentaje_participacion_oir <= 100'
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion') as batch:
            batch.drop_constraint('ck_orden_estacion_pct_oir', type_='check')
            batch.create_check_constraint(
                'ck_orden_estacion_pct_oir',
                'porcentaje_participacion_oir >= 0 AND porcentaje_participacion_oir <= 100',
            )
            batch.create_check_constraint('ck_orden_estacion_importe_oir', 'importe_oir >= 0')
            batch.create_check_constraint('ck_orden_estacion_iva_oir', 'iva_oir >= 0')
            batch.create_check_constraint('ck_orden_estacion_total_oir', 'total_oir >= 0')
    else:
        op.drop_constraint('ck_orden_estacion_pct_oir', 'orden_estacion', type_='check')
        op.create_check_constraint(
            'ck_orden_estacion_pct_oir',
            'orden_estacion',
            'porcentaje_participacion_oir >= 0 AND porcentaje_participacion_oir <= 100',
        )
        op.create_check_constraint(
            'ck_orden_estacion_importe_oir', 'orden_estacion', 'importe_oir >= 0'
        )
        op.create_check_constraint('ck_orden_estacion_iva_oir', 'orden_estacion', 'iva_oir >= 0')
        op.create_check_constraint(
            'ck_orden_estacion_total_oir', 'orden_estacion', 'total_oir >= 0'
        )

    op.create_table(
        'orden_cliente_vobo_item',
        sa.Column('orden_cliente_vobo_item_id', sa.Uuid(), nullable=False),
        sa.Column('orden_id', sa.Uuid(), nullable=False),
        sa.Column('item_clave', sa.Unicode(length=30), nullable=False),
        sa.Column('completado', sa.Boolean(), nullable=False),
        sa.Column('usuario_id', sa.Uuid(), nullable=True),
        sa.Column(
            'fecha_completado', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=True,
        ),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=True,
        ),
        sa.CheckConstraint(
            "item_clave IN ('razon_social', 'plaza', 'emisora', 'duracion', 'tarifa', "
            "'distribucion', 'horario', 'importes', 'audio', 'odc_firmada')",
            name='ck_orden_cliente_vobo_item_clave',
        ),
        sa.ForeignKeyConstraint(
            ['orden_id'], ['orden_cliente.orden_id'],
            name='fk_orden_cliente_vobo_item_orden', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['usuario_id'], ['usuario.usuario_id'],
            name='fk_orden_cliente_vobo_item_usuario', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('orden_cliente_vobo_item_id'),
        sa.UniqueConstraint(
            'orden_id', 'item_clave', name='uq_orden_cliente_vobo_item_orden_clave'
        ),
    )
