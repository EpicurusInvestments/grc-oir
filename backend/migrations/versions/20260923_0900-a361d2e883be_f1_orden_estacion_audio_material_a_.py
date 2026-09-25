"""f1 orden_estacion_audio material a transmitir

ADR-103 (petición del usuario) — Fase 3 del rediseño "Material a Transmitir": tabla
nueva `orden_estacion_audio` (uno o más archivos de audio por OrdenEstacion, con `orden`
fijando cuál es el default — `orden=0`) y columna nueva `orden_estacion_audio_id`
(nullable) en `orden_estacion_dia` para overrides puntuales por día (NULL = usa el
default).

Revision ID: a361d2e883be
Revises: 5b3010573980
Create Date: 2026-09-23 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'a361d2e883be'
down_revision: str | None = '5b3010573980'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'orden_estacion_audio',
        sa.Column('orden_estacion_audio_id', sa.Uuid(), nullable=False),
        sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
        sa.Column('ref', sa.Unicode(length=500), nullable=False),
        sa.Column('nombre_archivo', sa.Unicode(length=150), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['orden_estacion_id'], ['orden_estacion.orden_estacion_id'],
            name='fk_orden_estacion_audio_orden_estacion', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('orden_estacion_audio_id'),
        sa.UniqueConstraint(
            'orden_estacion_id', 'orden', name='uq_orden_estacion_audio_oe_orden'
        ),
    )
    op.add_column(
        'orden_estacion_dia',
        sa.Column('orden_estacion_audio_id', sa.Uuid(), nullable=True),
    )
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion_dia') as batch:
            batch.create_foreign_key(
                'fk_orden_estacion_dia_audio',
                'orden_estacion_audio',
                ['orden_estacion_audio_id'], ['orden_estacion_audio_id'],
                ondelete='NO ACTION',
            )
    else:
        op.create_foreign_key(
            'fk_orden_estacion_dia_audio', 'orden_estacion_dia', 'orden_estacion_audio',
            ['orden_estacion_audio_id'], ['orden_estacion_audio_id'], ondelete='NO ACTION',
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('orden_estacion_dia') as batch:
            batch.drop_constraint('fk_orden_estacion_dia_audio', type_='foreignkey')
            batch.drop_column('orden_estacion_audio_id')
    else:
        op.drop_constraint(
            'fk_orden_estacion_dia_audio', 'orden_estacion_dia', type_='foreignkey'
        )
        op.drop_column('orden_estacion_dia', 'orden_estacion_audio_id')
    op.drop_table('orden_estacion_audio')
