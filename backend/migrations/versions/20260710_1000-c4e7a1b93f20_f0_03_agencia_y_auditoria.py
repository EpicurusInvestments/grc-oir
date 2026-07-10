"""f0 03 agencia y auditoria

Tanda 1 de F0-03 (catálogos comerciales):
- `log_cambio_parametro`: bitácora de cambios a parámetros sensibles (mecanismo de
  auditoría por campo). Se estrena aquí; su PANTALLA de administración llega en F5.
- `agencia`: catálogo comercial raíz. Incluye el parámetro sensible
  `porcentaje_comision_agencia_default` (auditado + permiso por campo en el servicio).

Revision ID: c4e7a1b93f20
Revises: b73f13de1b80
Create Date: 2026-07-10 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'c4e7a1b93f20'
down_revision: str | None = 'b73f13de1b80'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Bitácora de parámetros sensibles (mecanismo de auditoría por campo) ──────────
    op.create_table(
        'log_cambio_parametro',
        sa.Column('log_cambio_parametro_id', sa.Uuid(), nullable=False),
        sa.Column('entidad', sa.Unicode(length=60), nullable=False),
        # entidad_id: UUID de la entidad afectada, guardado como texto (bitácora genérica).
        sa.Column('entidad_id', sa.Unicode(length=60), nullable=False),
        sa.Column('campo', sa.Unicode(length=80), nullable=False),
        # valor_anterior / valor_nuevo: texto (los campos sensibles son heterogéneos).
        sa.Column('valor_anterior', sa.Unicode(length=400), nullable=True),
        sa.Column('valor_nuevo', sa.Unicode(length=400), nullable=True),
        sa.Column('usuario', sa.Unicode(length=150), nullable=False),
        sa.Column('ip', sa.Unicode(length=64), nullable=True),
        sa.Column('motivo_cambio', sa.Unicode(length=500), nullable=True),
        sa.Column('fecha_cambio', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.PrimaryKeyConstraint('log_cambio_parametro_id'),
    )
    op.create_index(
        'ix_log_cambio_parametro_entidad',
        'log_cambio_parametro',
        ['entidad', 'entidad_id'],
        unique=False,
    )

    # ── Agencia (catálogo comercial raíz) ────────────────────────────────────────────
    op.create_table(
        'agencia',
        sa.Column('agencia_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_agencia', sa.Unicode(length=200), nullable=False),
        sa.Column('rfc_agencia', sa.Unicode(length=13), nullable=False),
        sa.Column('contacto_nombre', sa.Unicode(length=160), nullable=True),
        sa.Column('contacto_email', sa.Unicode(length=160), nullable=True),
        sa.Column('contacto_telefono', sa.Unicode(length=40), nullable=True),
        # PARÁMETRO SENSIBLE: % de comisión por defecto (auditado en el servicio).
        sa.Column('porcentaje_comision_agencia_default', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.CheckConstraint(
            'porcentaje_comision_agencia_default >= 0 AND porcentaje_comision_agencia_default <= 100',
            name='ck_agencia_comision',
        ),
        sa.PrimaryKeyConstraint('agencia_id'),
    )
    # nombre_agencia único (bajo collation CI de SQL Server, la unicidad es
    # case-insensitive; el servicio además compara con LOWER() para dar un 409 claro).
    op.create_index('ix_agencia_nombre_agencia', 'agencia', ['nombre_agencia'], unique=True)
    op.create_index('ix_agencia_rfc_agencia', 'agencia', ['rfc_agencia'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_agencia_rfc_agencia', table_name='agencia')
    op.drop_index('ix_agencia_nombre_agencia', table_name='agencia')
    op.drop_table('agencia')
    op.drop_index('ix_log_cambio_parametro_entidad', table_name='log_cambio_parametro')
    op.drop_table('log_cambio_parametro')
