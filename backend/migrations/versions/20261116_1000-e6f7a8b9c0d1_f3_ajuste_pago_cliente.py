"""f3 ajuste pago_cliente

ADR-270 (petición del usuario, con desarrolladores consultados): "Correcciones en pagos
múltiples" — nueva columna `ajuste` en `pago_cliente`, entre -$10 y +$10, que se SUMA a
`monto_aplicado` al validar que el pago múltiple cuadre exacto contra lo capturado
(`PagoMultipleCreate.monto_total_pago`). `monto_aplicado` sigue siendo el pendiente de
la factura, sin tocar — el ajuste absorbe diferencias chicas (comisiones bancarias,
redondeos); diferencias grandes siguen generando el pago "huérfano" de ADR-230.

Se agrega `ajuste` (DECIMAL(14,2), default 0, NOT NULL) + CHECK `ajuste BETWEEN -10 AND
10`. Sin backfill: ningún pago existente tuvo nunca este concepto — `default=0` para
todas las filas existentes es correcto desde el día 1.

Revision ID: e6f7a8b9c0d1
Revises: 7b931c7fdb4e
Create Date: 2026-11-16 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: str | None = '7b931c7fdb4e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLA = 'pago_cliente'
_CHECK = 'ck_pago_cliente_ajuste'


def upgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.add_column(
                sa.Column('ajuste', sa.Numeric(14, 2), nullable=False, server_default='0')
            )
            batch.create_check_constraint(_CHECK, 'ajuste BETWEEN -10 AND 10')
    else:
        op.add_column(
            _TABLA,
            sa.Column('ajuste', sa.Numeric(14, 2), nullable=False, server_default='0'),
        )
        op.create_check_constraint(_CHECK, _TABLA, 'ajuste BETWEEN -10 AND 10')


def _drop_default_constraint_mssql(tabla: str, columna: str) -> None:
    """Ver docstring de `7b931c7fdb4e`: `server_default` en SQL Server crea un DEFAULT
    CONSTRAINT con nombre autogenerado que hay que soltar antes del `DROP COLUMN`."""
    op.execute(
        f"""
        DECLARE @constraint_name NVARCHAR(200)
        SELECT @constraint_name = dc.name
        FROM sys.default_constraints dc
        JOIN sys.columns c
            ON c.default_object_id = dc.object_id AND c.object_id = dc.parent_object_id
        WHERE dc.parent_object_id = OBJECT_ID('{tabla}') AND c.name = '{columna}'
        IF @constraint_name IS NOT NULL
            EXEC('ALTER TABLE {tabla} DROP CONSTRAINT ' + @constraint_name)
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'sqlite':
        with op.batch_alter_table(_TABLA) as batch:
            batch.drop_constraint(_CHECK, type_='check')
            batch.drop_column('ajuste')
    else:
        op.drop_constraint(_CHECK, _TABLA, type_='check')
        _drop_default_constraint_mssql(_TABLA, 'ajuste')
        op.drop_column(_TABLA, 'ajuste')
