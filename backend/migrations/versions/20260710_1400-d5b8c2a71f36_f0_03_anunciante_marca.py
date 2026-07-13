"""f0 03 anunciante y marca

Tanda 2 de F0-03 (catálogos comerciales):
- `anunciante`: cliente comercial. `agencia_id` es FK **NULLABLE** (NULL = trato directo,
  sin agencia). Incluye el parámetro sensible `dias_credito_default` (auditado en el
  servicio) con CHECK `>= 0`.
- `marca`: se administra anidada en Anunciante (FK NOT NULL a anunciante).

Revision ID: d5b8c2a71f36
Revises: c4e7a1b93f20
Create Date: 2026-07-10 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'd5b8c2a71f36'
down_revision: str | None = 'c4e7a1b93f20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Anunciante (agencia_id NULLABLE = directo) ───────────────────────────────────
    op.create_table(
        'anunciante',
        sa.Column('anunciante_id', sa.Uuid(), nullable=False),
        # NULL = anunciante directo (sin agencia).
        sa.Column('agencia_id', sa.Uuid(), nullable=True),
        sa.Column('nombre_comercial', sa.Unicode(length=200), nullable=False),
        # nombre_fiscal: el que aparece en la factura (puede diferir del comercial).
        sa.Column('nombre_fiscal', sa.Unicode(length=250), nullable=False),
        sa.Column('rfc_anunciante', sa.Unicode(length=13), nullable=False),
        sa.Column('localizacion', sa.Unicode(length=250), nullable=True),
        sa.Column('referencia_anunciante', sa.Unicode(length=250), nullable=True),
        sa.Column('contacto_nombre', sa.Unicode(length=160), nullable=True),
        sa.Column('contacto_email', sa.Unicode(length=160), nullable=True),
        sa.Column('contacto_telefono', sa.Unicode(length=40), nullable=True),
        # PARÁMETRO SENSIBLE: días de crédito por defecto (auditado en el servicio).
        sa.Column('dias_credito_default', sa.Integer(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.CheckConstraint('dias_credito_default >= 0', name='ck_anunciante_dias_credito'),
        sa.ForeignKeyConstraint(['agencia_id'], ['agencia.agencia_id'], name='fk_anunciante_agencia'),
        sa.PrimaryKeyConstraint('anunciante_id'),
    )
    op.create_index(op.f('ix_anunciante_agencia_id'), 'anunciante', ['agencia_id'], unique=False)
    op.create_index(op.f('ix_anunciante_nombre_comercial'), 'anunciante', ['nombre_comercial'], unique=False)
    op.create_index(op.f('ix_anunciante_rfc_anunciante'), 'anunciante', ['rfc_anunciante'], unique=False)

    # ── Marca (anidada en Anunciante) ────────────────────────────────────────────────
    op.create_table(
        'marca',
        sa.Column('marca_id', sa.Uuid(), nullable=False),
        sa.Column('anunciante_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_marca', sa.Unicode(length=160), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        # updated_at: no está en la spec de Marca; se añade por uniformidad (ADR-011).
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.ForeignKeyConstraint(['anunciante_id'], ['anunciante.anunciante_id'], name='fk_marca_anunciante'),
        sa.PrimaryKeyConstraint('marca_id'),
    )
    op.create_index(op.f('ix_marca_anunciante_id'), 'marca', ['anunciante_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_marca_anunciante_id'), table_name='marca')
    op.drop_table('marca')
    op.drop_index(op.f('ix_anunciante_rfc_anunciante'), table_name='anunciante')
    op.drop_index(op.f('ix_anunciante_nombre_comercial'), table_name='anunciante')
    op.drop_index(op.f('ix_anunciante_agencia_id'), table_name='anunciante')
    op.drop_table('anunciante')
