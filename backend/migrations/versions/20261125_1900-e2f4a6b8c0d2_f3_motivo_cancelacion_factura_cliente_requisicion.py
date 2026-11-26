"""f3 motivo cancelacion factura cliente y requisicion

Petición del usuario: se abren 2 candados que rechazaban cancelar algo ya cobrado/
pagado con el mensaje "requiere una nota de crédito" — ahora cancelan en cascada y
exigen motivo (mismo criterio que `PagoCliente.motivo_cancelacion`, ADR-286):

- `factura_cliente.motivo_cancelacion`: "Cancelar factura" (antes se rechazaba si ya
  había pagos recibidos).
- `requisicion.motivo_cancelacion`: "Cancelar Pago a Proveedor" (nueva transición
  `pagada -> cancelada`, antes terminal) — también se usa para el "Cancelar" que ya
  existía desde `autorizada` (campo opcional, no cambia ese flujo).

Revision ID: e2f4a6b8c0d2
Revises: d9e1f3a5b7c9
Create Date: 2026-11-25 19:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'e2f4a6b8c0d2'
down_revision: str | None = 'd9e1f3a5b7c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_cliente',
        sa.Column('motivo_cancelacion', sa.Unicode(length=255), nullable=True),
    )
    op.add_column(
        'requisicion',
        sa.Column('motivo_cancelacion', sa.Unicode(length=255), nullable=True),
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('requisicion') as batch:
            batch.drop_column('motivo_cancelacion')
        with op.batch_alter_table('factura_cliente') as batch:
            batch.drop_column('motivo_cancelacion')
    else:
        op.drop_column('requisicion', 'motivo_cancelacion')
        op.drop_column('factura_cliente', 'motivo_cancelacion')
