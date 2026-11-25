"""f2 quita check iva tasa agencia vendedor

Petición del usuario: ahora se puede cargar un XML real (CFDI) de la factura de la
Agencia/Vendedor y precargar Subtotal/IVA desde ahí (o capturarlos a mano), igual que ya
funciona en `FacturaAfiliado` — un XML real puede traer redondeos/retenciones que no
cuadren exacto con `IVA = Subtotal * 16%`, así que se quita el CHECK que lo forzaba
(`ck_factura_agencia_iva_tasa`, agregado en `f2a9c5d7e1b8`; `ck_factura_vendedor_iva_tasa`,
agregado en `c3d4e5f6a7b8`). `ck_..._total_suma` (`total = monto + iva`) se conserva en
ambas tablas: sigue siendo válido venga de donde venga el IVA.

Revision ID: d9e1f3a5b7c9
Revises: 5782aa74d8d8
Create Date: 2026-11-25 17:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'd9e1f3a5b7c9'
down_revision: str | None = '5782aa74d8d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('factura_agencia') as batch:
            batch.drop_constraint('ck_factura_agencia_iva_tasa', type_='check')
        with op.batch_alter_table('factura_vendedor') as batch:
            batch.drop_constraint('ck_factura_vendedor_iva_tasa', type_='check')
    else:
        op.drop_constraint('ck_factura_agencia_iva_tasa', 'factura_agencia', type_='check')
        op.drop_constraint('ck_factura_vendedor_iva_tasa', 'factura_vendedor', type_='check')


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('factura_agencia') as batch:
            batch.create_check_constraint(
                'ck_factura_agencia_iva_tasa',
                'ROUND(iva_factura_agencia, 2) = ROUND(monto_factura_agencia * 0.16, 2)',
            )
        with op.batch_alter_table('factura_vendedor') as batch:
            batch.create_check_constraint(
                'ck_factura_vendedor_iva_tasa',
                'ROUND(iva_factura_vendedor, 2) = ROUND(monto_factura_vendedor * 0.16, 2)',
            )
    else:
        op.create_check_constraint(
            'ck_factura_agencia_iva_tasa', 'factura_agencia',
            'ROUND(iva_factura_agencia, 2) = ROUND(monto_factura_agencia * 0.16, 2)',
        )
        op.create_check_constraint(
            'ck_factura_vendedor_iva_tasa', 'factura_vendedor',
            'ROUND(iva_factura_vendedor, 2) = ROUND(monto_factura_vendedor * 0.16, 2)',
        )
