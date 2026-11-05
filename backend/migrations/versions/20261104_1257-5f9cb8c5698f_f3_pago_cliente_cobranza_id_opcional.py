"""f3 pago cliente cobranza id opcional

ADR-229 (petición del usuario): "pagos no asignados" — un `PagoCliente` puede
capturarse SIN saber todavía a qué `CobranzaFactura` corresponde, y asignársele
después. `cobranza_id` pasa de NOT NULL a NULLABLE (la FK y su nombre no cambian).

Nullability-only, SQLite necesita batch mode igual que cualquier otro ALTER de
columna (ver skill `migraciones-sqlserver` / ADR-063).

Revision ID: 5f9cb8c5698f
Revises: 608bd39dc2f2
Create Date: 2026-11-04 12:57:21.222581
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '5f9cb8c5698f'
down_revision: str | None = '608bd39dc2f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table('pago_cliente') as batch:
            batch.alter_column('cobranza_id', existing_type=sa.Uuid(), nullable=True)
    else:
        op.alter_column(
            'pago_cliente', 'cobranza_id', existing_type=sa.Uuid(), nullable=True
        )


def downgrade() -> None:
    # Revertir exige que NINGÚN pago exista sin asignar — si alguno quedó sin asignar,
    # no hay un valor razonable que inventarle (a diferencia de otros downgrades de este
    # proyecto que sí pueden reconstruir el dato).
    conexion = op.get_bind()
    sin_asignar = conexion.execute(
        sa.text('SELECT COUNT(*) FROM pago_cliente WHERE cobranza_id IS NULL')
    ).scalar()
    if sin_asignar:
        raise RuntimeError(
            f'No se puede revertir: {sin_asignar} pago(s) sin asignar. '
            'Asígnalos a una factura o bórralos antes de bajar esta versión.'
        )

    if conexion.dialect.name == 'sqlite':
        with op.batch_alter_table('pago_cliente') as batch:
            batch.alter_column('cobranza_id', existing_type=sa.Uuid(), nullable=False)
    else:
        op.alter_column(
            'pago_cliente', 'cobranza_id', existing_type=sa.Uuid(), nullable=False
        )
