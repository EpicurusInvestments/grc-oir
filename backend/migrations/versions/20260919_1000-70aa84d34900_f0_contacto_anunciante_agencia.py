"""f0 contacto anunciante y agencia

Crea `contacto_anunciante` y `contacto_agencia` — entidades NUEVAS, fuera de la spec
BD v2 (petición del usuario): Agencia y Anunciante ya traían un solo contacto plano
(`contacto_nombre`/`contacto_email`/`contacto_telefono`, sin tocar aquí — quedan como
legado). Ahora admiten VARIOS contactos cada uno, anidados igual que `Marca` en
Anunciante: tablas propias, sin discriminador ni FK polimórfica (cada una con su FK
simple al padre).

Mismos criterios que las migraciones recientes de F2/F3: `NO ACTION` en las FK (sin
DELETE físico en este esquema); columnas nullable sin `server_default` donde aplica.

Revision ID: 70aa84d34900
Revises: fb741ae3906d
Create Date: 2026-09-19 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '70aa84d34900'
down_revision: str | None = 'fb741ae3906d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'contacto_anunciante',
        sa.Column('contacto_anunciante_id', sa.Uuid(), nullable=False),
        sa.Column('anunciante_id', sa.Uuid(), nullable=False),
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
            ['anunciante_id'], ['anunciante.anunciante_id'],
            name='fk_contacto_anunciante_anunciante', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('contacto_anunciante_id'),
    )
    op.create_index(
        op.f('ix_contacto_anunciante_anunciante_id'), 'contacto_anunciante', ['anunciante_id'],
        unique=False,
    )

    op.create_table(
        'contacto_agencia',
        sa.Column('contacto_agencia_id', sa.Uuid(), nullable=False),
        sa.Column('agencia_id', sa.Uuid(), nullable=False),
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
            ['agencia_id'], ['agencia.agencia_id'],
            name='fk_contacto_agencia_agencia', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('contacto_agencia_id'),
    )
    op.create_index(
        op.f('ix_contacto_agencia_agencia_id'), 'contacto_agencia', ['agencia_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_contacto_agencia_agencia_id'), table_name='contacto_agencia')
    op.drop_table('contacto_agencia')
    op.drop_index(op.f('ix_contacto_anunciante_anunciante_id'), table_name='contacto_anunciante')
    op.drop_table('contacto_anunciante')
