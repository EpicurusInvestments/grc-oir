"""f2 factura_vendedor cabecera sin orden

Último de los 3 pasos (ver `a1b2c3d4e5f6`/`b2c3d4e5f6a7`), mismo patrón que
`f2a9c5d7e1b8` (Agencia): elimina de la CABECERA de `FacturaVendedor` lo que ya vive en
`FacturaVendedorOrden` — `orden_id` y `porcentaje_comision_vendedor`. `comision_vendedor`
pasa a NOT NULL. Se agrega el CHECK `ck_factura_vendedor_iva_tasa`: el IVA de esta
factura ya no se captura a mano, se calcula a la tasa central.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-06 09:25:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('factura_vendedor') as batch:
            batch.drop_constraint('ck_factura_vendedor_pct_comision', type_='check')
            batch.drop_column('porcentaje_comision_vendedor')
            batch.drop_constraint('fk_factura_vendedor_orden', type_='foreignkey')
            batch.drop_column('orden_id')
            batch.alter_column(
                'comision_vendedor',
                existing_type=sa.Numeric(precision=14, scale=2),
                nullable=False,
            )
            batch.create_check_constraint(
                'ck_factura_vendedor_iva_tasa',
                'ROUND(iva_factura_vendedor, 2) = ROUND(monto_factura_vendedor * 0.16, 2)',
            )
    else:
        op.drop_constraint('ck_factura_vendedor_pct_comision', 'factura_vendedor', type_='check')
        op.drop_column('factura_vendedor', 'porcentaje_comision_vendedor')
        op.drop_constraint('fk_factura_vendedor_orden', 'factura_vendedor', type_='foreignkey')
        op.drop_column('factura_vendedor', 'orden_id')
        op.alter_column(
            'factura_vendedor', 'comision_vendedor',
            existing_type=sa.Numeric(precision=14, scale=2), nullable=False,
        )
        op.create_check_constraint(
            'ck_factura_vendedor_iva_tasa', 'factura_vendedor',
            'ROUND(iva_factura_vendedor, 2) = ROUND(monto_factura_vendedor * 0.16, 2)',
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('factura_vendedor') as batch:
            batch.drop_constraint('ck_factura_vendedor_iva_tasa', type_='check')
            batch.alter_column(
                'comision_vendedor',
                existing_type=sa.Numeric(precision=14, scale=2),
                nullable=True,
            )
            batch.add_column(sa.Column('orden_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_factura_vendedor_orden', 'orden_cliente', ['orden_id'], ['orden_id'],
                ondelete='NO ACTION',
            )
            batch.add_column(
                sa.Column(
                    'porcentaje_comision_vendedor', sa.Numeric(precision=5, scale=2), nullable=True
                )
            )
            batch.create_check_constraint(
                'ck_factura_vendedor_pct_comision',
                'porcentaje_comision_vendedor >= 0 AND porcentaje_comision_vendedor <= 100',
            )
    else:
        op.drop_constraint('ck_factura_vendedor_iva_tasa', 'factura_vendedor', type_='check')
        op.alter_column(
            'factura_vendedor', 'comision_vendedor',
            existing_type=sa.Numeric(precision=14, scale=2), nullable=True,
        )
        op.add_column('factura_vendedor', sa.Column('orden_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_factura_vendedor_orden', 'factura_vendedor', 'orden_cliente',
            ['orden_id'], ['orden_id'], ondelete='NO ACTION',
        )
        op.add_column(
            'factura_vendedor',
            sa.Column(
                'porcentaje_comision_vendedor', sa.Numeric(precision=5, scale=2), nullable=True
            ),
        )
        op.create_check_constraint(
            'ck_factura_vendedor_pct_comision', 'factura_vendedor',
            'porcentaje_comision_vendedor >= 0 AND porcentaje_comision_vendedor <= 100',
        )
