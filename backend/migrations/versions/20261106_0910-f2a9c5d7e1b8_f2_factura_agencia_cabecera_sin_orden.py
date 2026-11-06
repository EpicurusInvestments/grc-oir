"""f2 factura_agencia cabecera sin orden

Último de los 3 pasos del ADR nuevo (ver `b7f3a1c9d2e4`/`d4e8f1a2c6b3`): elimina de la
CABECERA de `FacturaAgencia` lo que ya vive en `FacturaAgenciaOrden` —
`orden_id` (ya migrado a la puente) y `porcentaje_comision_agencia` (cada orden tiene el
suyo propio, `porcentaje_comision_snap`, congelado por fila). `comision_agencia` pasa a
NOT NULL: ya no es opcional, es la suma de las comisiones de las órdenes de la factura
(backfill de la migración anterior garantiza que ninguna fila quedó en NULL). También se
agrega el CHECK `ck_factura_agencia_iva_tasa`: a diferencia de `FacturaAfiliado`, el IVA
de esta factura YA NO se captura a mano — se calcula a la tasa central (ver docstring de
`factura_agencia.py`).

Revision ID: f2a9c5d7e1b8
Revises: d4e8f1a2c6b3
Create Date: 2026-11-06 09:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'f2a9c5d7e1b8'
down_revision: str | None = 'd4e8f1a2c6b3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('factura_agencia') as batch:
            batch.drop_constraint('ck_factura_agencia_pct_comision', type_='check')
            batch.drop_column('porcentaje_comision_agencia')
            batch.drop_constraint('fk_factura_agencia_orden', type_='foreignkey')
            batch.drop_column('orden_id')
            batch.alter_column(
                'comision_agencia',
                existing_type=sa.Numeric(precision=14, scale=2),
                nullable=False,
            )
            batch.create_check_constraint(
                'ck_factura_agencia_iva_tasa',
                'ROUND(iva_factura_agencia, 2) = ROUND(monto_factura_agencia * 0.16, 2)',
            )
    else:
        op.drop_constraint('ck_factura_agencia_pct_comision', 'factura_agencia', type_='check')
        op.drop_column('factura_agencia', 'porcentaje_comision_agencia')
        op.drop_constraint('fk_factura_agencia_orden', 'factura_agencia', type_='foreignkey')
        op.drop_column('factura_agencia', 'orden_id')
        op.alter_column(
            'factura_agencia', 'comision_agencia',
            existing_type=sa.Numeric(precision=14, scale=2), nullable=False,
        )
        op.create_check_constraint(
            'ck_factura_agencia_iva_tasa', 'factura_agencia',
            'ROUND(iva_factura_agencia, 2) = ROUND(monto_factura_agencia * 0.16, 2)',
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('factura_agencia') as batch:
            batch.drop_constraint('ck_factura_agencia_iva_tasa', type_='check')
            batch.alter_column(
                'comision_agencia',
                existing_type=sa.Numeric(precision=14, scale=2),
                nullable=True,
            )
            batch.add_column(sa.Column('orden_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_factura_agencia_orden', 'orden_cliente', ['orden_id'], ['orden_id'],
                ondelete='NO ACTION',
            )
            batch.add_column(
                sa.Column(
                    'porcentaje_comision_agencia', sa.Numeric(precision=5, scale=2), nullable=True
                )
            )
            batch.create_check_constraint(
                'ck_factura_agencia_pct_comision',
                'porcentaje_comision_agencia >= 0 AND porcentaje_comision_agencia <= 100',
            )
    else:
        op.drop_constraint('ck_factura_agencia_iva_tasa', 'factura_agencia', type_='check')
        op.alter_column(
            'factura_agencia', 'comision_agencia',
            existing_type=sa.Numeric(precision=14, scale=2), nullable=True,
        )
        op.add_column('factura_agencia', sa.Column('orden_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_factura_agencia_orden', 'factura_agencia', 'orden_cliente',
            ['orden_id'], ['orden_id'], ondelete='NO ACTION',
        )
        op.add_column(
            'factura_agencia',
            sa.Column(
                'porcentaje_comision_agencia', sa.Numeric(precision=5, scale=2), nullable=True
            ),
        )
        op.create_check_constraint(
            'ck_factura_agencia_pct_comision', 'factura_agencia',
            'porcentaje_comision_agencia >= 0 AND porcentaje_comision_agencia <= 100',
        )
