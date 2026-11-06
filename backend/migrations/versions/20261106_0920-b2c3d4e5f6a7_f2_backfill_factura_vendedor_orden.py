"""f2 backfill factura_vendedor_orden

Migración de DATOS (mismo patrón que `d4e8f1a2c6b3`, el backfill de Agencia): copia cada
`FacturaVendedor` existente (con su `orden_id`/`porcentaje_comision_vendedor`/
`comision_vendedor` de la cabecera) a UNA fila de `FacturaVendedorOrden`, antes de que el
siguiente paso (`c3d4e5f6a7b8`) elimine esas columnas de la cabecera.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-06 09:20:00.000000
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PUENTE = sa.table(
    'factura_vendedor_orden',
    sa.column('id', sa.Uuid()),
    sa.column('factura_vendedor_id', sa.Uuid()),
    sa.column('orden_id', sa.Uuid()),
    sa.column('porcentaje_comision_snap', sa.Numeric(5, 2)),
    sa.column('comision_calculada', sa.Numeric(14, 2)),
)


def upgrade() -> None:
    conn = op.get_bind()
    # Por seguridad antes del ALTER a NOT NULL del siguiente paso.
    conn.execute(
        sa.text(
            'UPDATE factura_vendedor SET comision_vendedor = 0 WHERE comision_vendedor IS NULL'
        )
    )

    filas = conn.execute(
        sa.text(
            'SELECT factura_vendedor_id, orden_id, porcentaje_comision_vendedor, '
            'comision_vendedor FROM factura_vendedor WHERE orden_id IS NOT NULL'
        )
    ).all()
    for fila in filas:
        conn.execute(
            _PUENTE.insert().values(
                id=uuid.uuid4(),
                factura_vendedor_id=fila.factura_vendedor_id,
                orden_id=fila.orden_id,
                porcentaje_comision_snap=fila.porcentaje_comision_vendedor or Decimal('0'),
                comision_calculada=fila.comision_vendedor or Decimal('0'),
            )
        )


def downgrade() -> None:
    # Irreversible a propósito: una factura con VARIAS filas en la puente no tiene un
    # único `orden_id`/`%` al que volver (mismo criterio que `d4e8f1a2c6b3`).
    pass
