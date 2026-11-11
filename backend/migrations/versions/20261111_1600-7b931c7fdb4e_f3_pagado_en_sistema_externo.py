"""f3 pagado_en_sistema_externo

ADR-256 (petición del usuario, "NEW FEATURE") — checkbox "Pagado en sistema externo"
al registrar un pago del cliente (individual y múltiple): identifica un pago que en
realidad se registró/concilió en otro sistema (p.ej. OIR), sin cambiar nada más del
flujo — mismo criterio que `FacturaCliente.facturado_en_sistema_externo` (ADR-248),
solo identificación, sin ningún efecto ni cálculo nuevo.

Se agrega `pagado_en_sistema_externo` (BIT, default `False`) a `pago_cliente`. Sin
backfill: ningún pago existente se registró nunca "en sistema externo" bajo este
concepto (la feature no existía) — `default=False` para todas las filas existentes es
correcto desde el día 1.

`add_column` con `server_default='0'` funciona igual en SQLite y SQL Server (mismo
criterio que `d5e6f7a8b9c0`) — no necesita rama por dialecto. El `downgrade` sí la
necesita: en SQL Server, `server_default` crea un DEFAULT CONSTRAINT autogenerado que
bloquea el `DROP COLUMN` si no se suelta antes.

Revision ID: 7b931c7fdb4e
Revises: d5e6f7a8b9c0
Create Date: 2026-11-11 16:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '7b931c7fdb4e'
down_revision: str | None = 'd5e6f7a8b9c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'pago_cliente',
        sa.Column(
            'pagado_en_sistema_externo', sa.Boolean(), nullable=False, server_default='0'
        ),
    )


def _drop_default_constraint_mssql(tabla: str, columna: str) -> None:
    """Ver docstring del módulo: `server_default` en SQL Server crea un DEFAULT
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
        with op.batch_alter_table('pago_cliente') as batch:
            batch.drop_column('pagado_en_sistema_externo')
    else:
        _drop_default_constraint_mssql('pago_cliente', 'pagado_en_sistema_externo')
        op.drop_column('pago_cliente', 'pagado_en_sistema_externo')
