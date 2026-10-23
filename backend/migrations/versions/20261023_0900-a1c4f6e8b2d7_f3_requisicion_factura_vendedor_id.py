"""f3 requisicion factura_vendedor_id

Petición del usuario: al pagar una Requisición, se debe cerrar (pasar a "pagada") la
factura de proveedor relacionada. `pago_afiliado`/`pago_agencia` ya tenían ese enlace
(`factura_afiliado_id`/`factura_agencia_id`); `comision_vendedor` no tenía ninguno —
`vendedor_comision_id`+`orden_id` no bastan para resolver una `FacturaVendedor` única
(relación 1:N, sin `UniqueConstraint`). Se agrega `factura_vendedor_id`, mismo patrón
que sus hermanas: FK opcional, NULLABLE (las requisiciones ya existentes no la tienen y
no se les puede adivinar), con índice.

`comision_agencia` NO gana ningún campo aquí: no existe una entidad "factura" para esa
comisión (confirmado al investigar — es un pago puro, sin factura previa que cerrar).

Revision ID: a1c4f6e8b2d7
Revises: e92f9bc99f9f
Create Date: 2026-10-23 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'a1c4f6e8b2d7'
down_revision: str | None = 'e92f9bc99f9f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'requisicion',
        sa.Column('factura_vendedor_id', sa.Uuid(), nullable=True),
    )
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('requisicion') as batch:
            batch.create_foreign_key(
                'fk_requisicion_factura_vendedor',
                'factura_vendedor',
                ['factura_vendedor_id'],
                ['factura_vendedor_id'],
            )
            batch.create_index(
                'ix_requisicion_factura_vendedor_id', ['factura_vendedor_id']
            )
    else:
        op.create_foreign_key(
            'fk_requisicion_factura_vendedor',
            'requisicion',
            'factura_vendedor',
            ['factura_vendedor_id'],
            ['factura_vendedor_id'],
        )
        op.create_index(
            'ix_requisicion_factura_vendedor_id', 'requisicion', ['factura_vendedor_id']
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('requisicion') as batch:
            batch.drop_index('ix_requisicion_factura_vendedor_id')
            batch.drop_constraint('fk_requisicion_factura_vendedor', type_='foreignkey')
            batch.drop_column('factura_vendedor_id')
    else:
        op.drop_index('ix_requisicion_factura_vendedor_id', table_name='requisicion')
        op.drop_constraint('fk_requisicion_factura_vendedor', 'requisicion', type_='foreignkey')
        op.drop_column('requisicion', 'factura_vendedor_id')
