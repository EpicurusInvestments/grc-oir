"""f0 asentamiento_postal

Nuevo catálogo `asentamiento_postal` (F0): códigos postales de México (SEPOMEX),
para autocompletar los domicilios estructurados de Anunciante/EmpresaFacturadora
(ver la migración siguiente). SOLO crea la tabla — está vacía hasta correr
`backend/scripts/cargar_codigos_postales.py` (145,908 filas: demasiadas para vivir
como datos literales dentro de una migración).

Revision ID: 7f4db0ba33db
Revises: 4f2e15c90f71
Create Date: 2026-08-31 17:30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '7f4db0ba33db'
down_revision: str | None = '4f2e15c90f71'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'asentamiento_postal',
        sa.Column('asentamiento_postal_id', sa.Uuid(), nullable=False),
        sa.Column('codigo_postal', sa.Unicode(length=5), nullable=False),
        sa.Column('asentamiento', sa.Unicode(length=150), nullable=False),
        sa.Column('tipo_asentamiento', sa.Unicode(length=50), nullable=True),
        sa.Column('municipio', sa.Unicode(length=150), nullable=False),
        sa.Column('estado', sa.Unicode(length=100), nullable=False),
        sa.Column('ciudad', sa.Unicode(length=150), nullable=True),
        sa.Column('pais', sa.Unicode(length=3), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True
        ),
        sa.PrimaryKeyConstraint('asentamiento_postal_id'),
    )
    op.create_index(
        'ix_asentamiento_postal_codigo_postal',
        'asentamiento_postal',
        ['codigo_postal'],
    )


def downgrade() -> None:
    op.drop_index('ix_asentamiento_postal_codigo_postal', table_name='asentamiento_postal')
    op.drop_table('asentamiento_postal')
