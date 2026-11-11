"""f2 facturado_en_sistema_externo

ADR-248 (petición del usuario, "NEW FEATURE") — checkbox "Facturado en sistema
externo" en "Registrar respuesta del timbrado": identifica una factura que en
realidad se facturó en otro sistema (p.ej. OIR), sin cambiar nada más del flujo — el
monto para OIR sigue siendo el que ya calculó este sistema (subtotal/iva/total de
`FacturaCliente`, derivados de las órdenes); la factura cargada en el otro sistema
seguramente trae un monto distinto, y eso es exactamente lo que este campo distingue
(solo identificación, sin ningún cálculo nuevo).

Se agrega `facturado_en_sistema_externo` (BIT, default `False`) a `factura_cliente`.
Sin backfill: ninguna fila existente se facturó nunca "en sistema externo" bajo este
concepto (la feature no existía) — `default=False` para todas es correcto desde el
día 1, no hace falta una migración de datos aparte (a diferencia de
`facturado_directo`, `2e0c8a75aad5`, que si necesitó corregir filas ya sembradas con
un valor por default incorrecto).

`add_column` con `server_default='0'` funciona igual en SQLite y SQL Server (mismo
criterio que `2e0c8a75aad5`) — no necesita rama por dialecto. El `downgrade` sí la
necesita: en SQL Server, `server_default` crea un DEFAULT CONSTRAINT autogenerado que
bloquea el `DROP COLUMN` si no se suelta antes.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-11-10 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'factura_cliente',
        sa.Column(
            'facturado_en_sistema_externo', sa.Boolean(), nullable=False, server_default='0'
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
        with op.batch_alter_table('factura_cliente') as batch:
            batch.drop_column('facturado_en_sistema_externo')
    else:
        _drop_default_constraint_mssql('factura_cliente', 'facturado_en_sistema_externo')
        op.drop_column('factura_cliente', 'facturado_en_sistema_externo')
