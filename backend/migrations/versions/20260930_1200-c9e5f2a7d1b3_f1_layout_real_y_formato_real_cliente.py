"""f1 orden_estacion_layout_real y orden_estacion_formato_real_cliente

ADR-146 (petición del usuario) — 2 componentes nuevos en "Capturar Reales", junto a
"Evidencias de lo Transmitido"/"Formato de Horarios Reales":

- "Carga de Órdenes Reales Desde Layout": `orden_estacion_layout_real`, lista blanca de
  extensiones (csv/xlsx/xls/txt) — solo guarda el archivo, el parseo para actualizar la
  tabla de reales se define en una fase posterior.
- "Formato de Horarios Reales Enviado al Cliente": `orden_estacion_formato_real_cliente`,
  lista negra (cualquier formato salvo ejecutables/scripts/audio).

Mismo patrón que `orden_estacion_formato_real` (b8d4c1a5e0f7): lista plana, sin `orden`
ni default. `create_table`/`drop_table` funcionan igual en SQLite y SQL Server (no
necesitan rama por dialecto).

Revision ID: c9e5f2a7d1b3
Revises: b8d4c1a5e0f7
Create Date: 2026-09-30 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'c9e5f2a7d1b3'
down_revision: str | None = 'b8d4c1a5e0f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'orden_estacion_layout_real',
        sa.Column('orden_estacion_layout_real_id', sa.Uuid(), nullable=False),
        sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
        sa.Column('ref', sa.Unicode(length=500), nullable=False),
        sa.Column('nombre_archivo', sa.Unicode(length=150), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['orden_estacion_id'], ['orden_estacion.orden_estacion_id'],
            name='fk_orden_estacion_layout_real_orden_estacion', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('orden_estacion_layout_real_id'),
    )
    op.create_index(
        'ix_orden_estacion_layout_real_orden_estacion_id',
        'orden_estacion_layout_real',
        ['orden_estacion_id'],
    )

    op.create_table(
        'orden_estacion_formato_real_cliente',
        sa.Column('orden_estacion_formato_real_cliente_id', sa.Uuid(), nullable=False),
        sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
        sa.Column('ref', sa.Unicode(length=500), nullable=False),
        sa.Column('nombre_archivo', sa.Unicode(length=150), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['orden_estacion_id'], ['orden_estacion.orden_estacion_id'],
            name='fk_orden_estacion_formato_real_cliente_orden_estacion', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('orden_estacion_formato_real_cliente_id'),
    )
    op.create_index(
        'ix_orden_estacion_formato_real_cliente_orden_estacion_id',
        'orden_estacion_formato_real_cliente',
        ['orden_estacion_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_orden_estacion_formato_real_cliente_orden_estacion_id',
        table_name='orden_estacion_formato_real_cliente',
    )
    op.drop_table('orden_estacion_formato_real_cliente')

    op.drop_index(
        'ix_orden_estacion_layout_real_orden_estacion_id',
        table_name='orden_estacion_layout_real',
    )
    op.drop_table('orden_estacion_layout_real')
