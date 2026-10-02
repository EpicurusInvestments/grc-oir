"""f1 log envio correo orden estacion

ADR-105 (petición del usuario) — Fase 5 del rediseño "Orden de Servicio y Orden de
Transmisión": tabla nueva `log_envio_correo_orden_estacion`, bitácora de los envíos por
correo de los PDFs de OrdenEstacion (servicio/programados/reales). Un registro por
INTENTO (exitoso o no) — nunca se borra ni se edita, mismo criterio que
`LogCambioParametro` pero en tabla propia (esto registra una acción externa, no el
cambio de valor de un campo).

`create_table`/`drop_table` funcionan igual en SQLite y SQL Server (no necesitan rama
por dialecto, mismo criterio que la migración de `orden_estacion_audio`,
`a361d2e883be`).

Revision ID: fb5e4af2dd28
Revises: e262550019b7
Create Date: 2026-09-23 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'fb5e4af2dd28'
down_revision: str | None = 'e262550019b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'log_envio_correo_orden_estacion',
        sa.Column('log_envio_correo_id', sa.Uuid(), nullable=False),
        sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
        sa.Column('tipo_pdf', sa.Unicode(length=20), nullable=False),
        sa.Column('destinatario_email', sa.Unicode(length=320), nullable=False),
        sa.Column('usuario', sa.Unicode(length=150), nullable=False),
        sa.Column('exitoso', sa.Boolean(), nullable=False),
        sa.Column(
            'mensaje_error',
            sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'),
            nullable=True,
        ),
        sa.Column(
            'fecha_envio', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tipo_pdf IN ('servicio', 'programados', 'reales')",
            name='ck_log_envio_correo_oe_tipo_pdf',
        ),
        sa.ForeignKeyConstraint(
            ['orden_estacion_id'], ['orden_estacion.orden_estacion_id'],
            name='fk_log_envio_correo_oe_orden_estacion', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('log_envio_correo_id'),
    )
    op.create_index(
        'ix_log_envio_correo_oe_orden_estacion',
        'log_envio_correo_orden_estacion',
        ['orden_estacion_id'],
    )


def downgrade() -> None:
    op.drop_table('log_envio_correo_orden_estacion')
