"""f1 orden_estacion_evidencia transmitido

ADR-119 (petición del usuario): tabla nueva `orden_estacion_evidencia` — evidencias
(audio) de lo REALMENTE transmitido, capturadas libremente en "Capturar Reales"
(2.2→2.3). Reemplaza en la pantalla de captura a `OrdenEstacion.testigos_url`/
`testigos_ubicacion_alterna` (esas 2 columnas NO se tocan aquí — se preserva cualquier
dato ya capturado en RDS, simplemente dejan de escribirse desde el flujo normal).

Sin `orden`/default ni override por día (a diferencia de `orden_estacion_audio`,
"Material a Transmitir"): es una lista plana, ordenada por `created_at`.

Revision ID: 0b643d77d4cc
Revises: c3162961f659
Create Date: 2026-09-24 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '0b643d77d4cc'
down_revision: str | None = 'c3162961f659'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'orden_estacion_evidencia',
        sa.Column('orden_estacion_evidencia_id', sa.Uuid(), nullable=False),
        sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
        sa.Column('ref', sa.Unicode(length=500), nullable=False),
        sa.Column('nombre_archivo', sa.Unicode(length=150), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['orden_estacion_id'], ['orden_estacion.orden_estacion_id'],
            name='fk_orden_estacion_evidencia_orden_estacion', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('orden_estacion_evidencia_id'),
    )
    op.create_index(
        'ix_orden_estacion_evidencia_orden_estacion_id',
        'orden_estacion_evidencia',
        ['orden_estacion_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_orden_estacion_evidencia_orden_estacion_id',
        table_name='orden_estacion_evidencia',
    )
    op.drop_table('orden_estacion_evidencia')
