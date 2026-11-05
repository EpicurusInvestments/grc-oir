"""f2 f3 facturado_directo

ADR-236 (petición del usuario, reportado con captura): `agencia_id` por sí solo NO
alcanza para saber si el receptor de una factura es el anunciante o la agencia — es
solo una REFERENCIA capturada en la orden (`OrdenCliente.agencia_id`), y puede estar
lleno aunque la orden sea `facturacion_directa_cliente = True` (facturación directa con
una agencia de referencia). El picker de "Pago Múltiple" (F3) filtraba por
`agencia_id IS NULL`/`agencia_id = X` y por eso mezclaba facturas de ambos receptores.

Se agrega `facturado_directo` (BIT) a `factura_cliente` (calculado una sola vez al
crear la factura, igual que `_receptor_de()`) y a `cobranza_factura` (copiado de
`factura_cliente` al timbrar, mismo criterio que `agencia_id`). El backfill de las filas
existentes va en la revisión siguiente (migración solo de datos, mismo patrón que
`608bd39dc2f2`).

`add_column` con `server_default='1'` funciona igual en SQLite y SQL Server (mismo
criterio que `e262550019b7`) — no necesita rama por dialecto. El `downgrade` sí la
necesita: en SQL Server, `server_default` crea un DEFAULT CONSTRAINT autogenerado que
bloquea el `DROP COLUMN` si no se suelta antes.

Revision ID: 2e0c8a75aad5
Revises: 5f9cb8c5698f
Create Date: 2026-11-05 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '2e0c8a75aad5'
down_revision: str | None = '5f9cb8c5698f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_cliente',
        sa.Column('facturado_directo', sa.Boolean(), nullable=False, server_default='1'),
    )
    op.add_column(
        'cobranza_factura',
        sa.Column('facturado_directo', sa.Boolean(), nullable=False, server_default='1'),
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
        with op.batch_alter_table('cobranza_factura') as batch:
            batch.drop_column('facturado_directo')
        with op.batch_alter_table('factura_cliente') as batch:
            batch.drop_column('facturado_directo')
    else:
        _drop_default_constraint_mssql('cobranza_factura', 'facturado_directo')
        op.drop_column('cobranza_factura', 'facturado_directo')
        _drop_default_constraint_mssql('factura_cliente', 'facturado_directo')
        op.drop_column('factura_cliente', 'facturado_directo')
