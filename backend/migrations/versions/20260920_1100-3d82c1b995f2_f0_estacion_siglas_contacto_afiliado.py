"""f0 estacion siglas y contacto afiliado

Dos cambios de F0-01 (ADR-094), petición del usuario:

- `estacion` gana `siglas` (NUEVO, fuera de la spec BD v2): identificador corto de la
  emisora (p.ej. "XEW"), opcional. `plaza_id` NO cambia de columna — sigue existiendo
  igual (NOT NULL, FK a `plaza`); lo que cambia es de dónde viene el valor (antes lo
  derivaba el servicio del afiliado — ADR-005 —, ahora lo captura el cliente
  directamente), un cambio de comportamiento en la capa de servicio, no de esquema.
- Crea `contacto_afiliado` — entidad NUEVA, mismo patrón que `contacto_anunciante`/
  `contacto_agencia` (ADR-091): varios contactos por Afiliado, tabla propia con FK simple.

Revision ID: 3d82c1b995f2
Revises: 70aa84d34900
Create Date: 2026-09-20 11:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '3d82c1b995f2'
down_revision: str | None = '70aa84d34900'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('estacion', sa.Column('siglas', sa.Unicode(length=20), nullable=True))

    op.create_table(
        'contacto_afiliado',
        sa.Column('contacto_afiliado_id', sa.Uuid(), nullable=False),
        sa.Column('afiliado_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_contacto', sa.Unicode(length=160), nullable=False),
        sa.Column('puesto_contacto', sa.Unicode(length=160), nullable=True),
        sa.Column('telefono_contacto', sa.Unicode(length=40), nullable=True),
        sa.Column('email_contacto', sa.Unicode(length=160), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ['afiliado_id'], ['afiliado.afiliado_id'],
            name='fk_contacto_afiliado_afiliado', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('contacto_afiliado_id'),
    )
    op.create_index(
        op.f('ix_contacto_afiliado_afiliado_id'), 'contacto_afiliado', ['afiliado_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_contacto_afiliado_afiliado_id'), table_name='contacto_afiliado')
    op.drop_table('contacto_afiliado')
    op.drop_column('estacion', 'siglas')
