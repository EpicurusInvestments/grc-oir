"""f0 06 duracion spot catalogo

ADR-159 (petición del usuario): catálogo NUEVO (fuera de la spec BD v2) y DESCONECTADO
del enum `DuracionSpot` (`app/shared/enums.py`) que ya usan `TarifaPlaza`/`OrdenCliente`/
`OrdenEstacion` — ese enum no se toca. Este catálogo solo registra duraciones
administrables por `producto` (reusa el CHECK de `ProductoTarifa`, ya existente en
`tarifa_plaza`), con una descripción de duración en TEXTO LIBRE (no un ENUM cerrado) para
poder agregar valores nuevos sin otra migración ("ir agregándole más tiempo etc.").

Por ahora NINGÚN otro módulo lee ni escribe esta tabla ("solo crea el catálogo... solo
quiero ver el CRUD completo") — tabla nueva, independiente, sin FKs entrantes ni
salientes.

Revision ID: 2047cd2e1d53
Revises: ec3a357e7c0a
Create Date: 2026-10-05 13:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '2047cd2e1d53'
down_revision: str | None = 'ec3a357e7c0a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'duracion_spot_catalogo',
        sa.Column('duracion_spot_catalogo_id', sa.Uuid(), nullable=False),
        sa.Column('producto', sa.Unicode(length=20), nullable=False),
        sa.Column('descripcion_duracion', sa.Unicode(length=60), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True
        ),
        sa.CheckConstraint(
            "producto IN ('spot', 'mencion', 'control_remoto', 'patrocinio')",
            name='ck_duracion_spot_catalogo_producto',
        ),
        sa.PrimaryKeyConstraint('duracion_spot_catalogo_id'),
    )
    op.create_index(
        op.f('ix_duracion_spot_catalogo_producto'), 'duracion_spot_catalogo', ['producto'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_duracion_spot_catalogo_producto'), table_name='duracion_spot_catalogo'
    )
    op.drop_table('duracion_spot_catalogo')
