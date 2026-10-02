"""f1 orden_estacion_formato_real

ADR-123 (petición del usuario) — "Formato de Horarios Reales": junto a "Evidencias de
lo Transmitido" en "Capturar Reales", pero acepta CUALQUIER formato (PDF, Excel, TXT,
audio, ...) salvo ejecutables/scripts (lista negra, ver `leer_adjunto_libre` en
`app/integrations/almacenamiento/documentos.py`). Tabla nueva, mismo patrón que
`orden_estacion_evidencia` (0b643d77d4cc): lista plana, sin `orden` ni default.

`create_table`/`drop_table` funcionan igual en SQLite y SQL Server (no necesitan rama
por dialecto, mismo criterio que `orden_estacion_evidencia`).

Revision ID: b8d4c1a5e0f7
Revises: a7c1f3e9b2d4
Create Date: 2026-09-25 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'b8d4c1a5e0f7'
down_revision: str | None = 'a7c1f3e9b2d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'orden_estacion_formato_real',
        sa.Column('orden_estacion_formato_real_id', sa.Uuid(), nullable=False),
        sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
        sa.Column('ref', sa.Unicode(length=500), nullable=False),
        sa.Column('nombre_archivo', sa.Unicode(length=150), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['orden_estacion_id'], ['orden_estacion.orden_estacion_id'],
            name='fk_orden_estacion_formato_real_orden_estacion', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('orden_estacion_formato_real_id'),
    )
    op.create_index(
        'ix_orden_estacion_formato_real_orden_estacion_id',
        'orden_estacion_formato_real',
        ['orden_estacion_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_orden_estacion_formato_real_orden_estacion_id',
        table_name='orden_estacion_formato_real',
    )
    op.drop_table('orden_estacion_formato_real')
