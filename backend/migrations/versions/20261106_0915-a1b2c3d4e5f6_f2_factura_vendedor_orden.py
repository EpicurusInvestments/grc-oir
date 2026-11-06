"""f2 factura_vendedor_orden

ADR nuevo (petición del usuario, con captura, 2026-11-06) — mismo cambio que ADR-239
hizo para `FacturaAgencia`, aplicado aquí para `FacturaVendedor` en la misma entrega:
deja de relacionarse 1:1-por-factura con `OrdenCliente` y pasa a ser N:M vía esta tabla
puente, mismo patrón que `FacturaAgenciaOrden` (migración `b7f3a1c9d2e4`).

Primera de 3 migraciones (crear tabla → migrar datos → soltar columnas viejas), mismo
patrón de 3 pasos que el cambio de Agencia.

Revision ID: a1b2c3d4e5f6
Revises: f2a9c5d7e1b8
Create Date: 2026-11-06 09:15:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f2a9c5d7e1b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'factura_vendedor_orden',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('factura_vendedor_id', sa.Uuid(), nullable=False),
        sa.Column('orden_id', sa.Uuid(), nullable=False),
        sa.Column('porcentaje_comision_snap', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('comision_calculada', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint('comision_calculada >= 0', name='ck_factura_vendedor_orden_comision'),
        sa.CheckConstraint(
            'porcentaje_comision_snap >= 0 AND porcentaje_comision_snap <= 100',
            name='ck_factura_vendedor_orden_pct',
        ),
        sa.ForeignKeyConstraint(
            ['factura_vendedor_id'], ['factura_vendedor.factura_vendedor_id'],
            name='fk_factura_vendedor_orden_factura', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['orden_id'], ['orden_cliente.orden_id'],
            name='fk_factura_vendedor_orden_oc', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'factura_vendedor_id', 'orden_id', name='uq_factura_vendedor_orden_factura_oc'
        ),
    )


def downgrade() -> None:
    op.drop_table('factura_vendedor_orden')
