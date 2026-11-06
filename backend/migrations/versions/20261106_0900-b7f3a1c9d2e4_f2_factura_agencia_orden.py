"""f2 factura_agencia_orden

ADR nuevo (petición del usuario, con captura, 2026-11-06) — SUSTITUYE el criterio de
ADR-079: `FacturaAgencia` deja de relacionarse 1:1-por-factura con `OrdenCliente` (columna
`orden_id` en la cabecera) y pasa a ser N:M vía esta tabla puente, mismo patrón que
`FacturaAfiliadoOrden` (F2, migración `3e57e45d24cb`). Permite que una factura de agencia
acumule VARIAS órdenes, cada una con su propio `%` de comisión ya pactado
(`porcentaje_comision_snap`, congelado al agregarla).

Esta es la primera de 3 migraciones del cambio (crear tabla → migrar datos → soltar
columnas viejas de la cabecera), mismo patrón de 3 pasos que ADR-236
(`2e0c8a75aad5`/`4f286d68a07f`), aquí con un tercer paso porque además hay que ELIMINAR
columnas (ADR-236 solo agregaba).

Revision ID: b7f3a1c9d2e4
Revises: 4f286d68a07f
Create Date: 2026-11-06 09:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'b7f3a1c9d2e4'
down_revision: str | None = '4f286d68a07f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'factura_agencia_orden',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('factura_agencia_id', sa.Uuid(), nullable=False),
        sa.Column('orden_id', sa.Uuid(), nullable=False),
        sa.Column('porcentaje_comision_snap', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('comision_calculada', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint('comision_calculada >= 0', name='ck_factura_agencia_orden_comision'),
        sa.CheckConstraint(
            'porcentaje_comision_snap >= 0 AND porcentaje_comision_snap <= 100',
            name='ck_factura_agencia_orden_pct',
        ),
        sa.ForeignKeyConstraint(
            ['factura_agencia_id'], ['factura_agencia.factura_agencia_id'],
            name='fk_factura_agencia_orden_factura', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['orden_id'], ['orden_cliente.orden_id'],
            name='fk_factura_agencia_orden_oc', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'factura_agencia_id', 'orden_id', name='uq_factura_agencia_orden_factura_oc'
        ),
    )


def downgrade() -> None:
    op.drop_table('factura_agencia_orden')
