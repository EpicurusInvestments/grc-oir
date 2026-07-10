"""f0 02 tarifas

Revision ID: b73f13de1b80
Revises: 7300e6f940a3
Create Date: 2026-07-08 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'b73f13de1b80'
down_revision: str | None = '7300e6f940a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('tarifa_plaza',
    sa.Column('tarifa_plaza_id', sa.Uuid(), nullable=False),
    sa.Column('plaza_id', sa.Uuid(), nullable=False),
    sa.Column('tipo_senal', sa.Unicode(length=4), nullable=False),
    sa.Column('duracion_spot', sa.Unicode(length=10), nullable=False),
    sa.Column('tarifa_bruta', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('descuento_pct', sa.Numeric(precision=5, scale=2), nullable=False),
    # tarifa_neta: CALCULADA por el servicio (bruta * (1 - descuento/100)) y persistida.
    sa.Column('tarifa_neta', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('vigencia_desde', sa.Date(), nullable=False),
    sa.Column('vigencia_hasta', sa.Date(), nullable=False),
    sa.Column('notas', sa.Unicode(length=500), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    # created_by: username del capturista (texto, no FK: no hay tabla Usuario hasta F0-04).
    sa.Column('created_by', sa.Unicode(length=150), nullable=True),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.CheckConstraint("tipo_senal IN ('fm', 'am', 'tv')", name='ck_tarifa_plaza_tipo_senal'),
    sa.CheckConstraint("duracion_spot IN ('20s', '30s', '60s', 'mencion')", name='ck_tarifa_plaza_duracion_spot'),
    sa.CheckConstraint('descuento_pct >= 0 AND descuento_pct <= 100', name='ck_tarifa_plaza_descuento_pct'),
    sa.CheckConstraint('vigencia_hasta >= vigencia_desde', name='ck_tarifa_plaza_vigencia'),
    sa.ForeignKeyConstraint(['plaza_id'], ['plaza.plaza_id'], name='fk_tarifa_plaza_plaza'),
    sa.PrimaryKeyConstraint('tarifa_plaza_id')
    )
    op.create_index(op.f('ix_tarifa_plaza_plaza_id'), 'tarifa_plaza', ['plaza_id'], unique=False)
    # Índice compuesto: acelera el filtrado por combinación y la consulta de solapamiento.
    op.create_index('ix_tarifa_plaza_combo', 'tarifa_plaza', ['plaza_id', 'tipo_senal', 'duracion_spot'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tarifa_plaza_combo', table_name='tarifa_plaza')
    op.drop_index(op.f('ix_tarifa_plaza_plaza_id'), table_name='tarifa_plaza')
    op.drop_table('tarifa_plaza')
