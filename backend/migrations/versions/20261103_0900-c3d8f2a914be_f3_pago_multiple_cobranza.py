"""f3 pago multiple cobranza

ADR-225 (petición del usuario): "Pago Múltiple para varias facturas" en Cobranza.

- `cobranza_factura.agencia_id`: derivado de `FacturaCliente.agencia_id` al crear (ya se
  copiaba `anunciante_id` por el mismo motivo) — hace falta para filtrar "facturas
  pendientes de esta AGENCIA" en el nuevo picker de pago múltiple. Nullable: igual que
  `FacturaCliente.agencia_id` (NULL = facturación directa, sin agencia).
- `pago_cliente`: 5 columnas nuevas.
  - `forma_pago_clave` (clave de `ConstantesSistema` grupo FormaPago, sin FK formal —
    mismo patrón que `metodo_pago_clave`; reutiliza el catálogo que F2 ya usa para
    `FacturaCliente.forma_pago_clave`, no uno nuevo).
  - `fecha_deposito`, `numero_pago` (parcialidad, texto libre tipo "2 de 3"),
    `cuenta_contable_id` (FK real a `CuentaContable`, catálogo ya existente).
  - `pago_multiple_id`: UUID compartido por todos los `PagoCliente` creados en UNA
    misma captura de pago múltiple (trazabilidad/agrupación) — NULL en un pago
    individual. Indexado para poder listar "los pagos de este mismo lote".
- `pago_cliente.metodo_pago_clave` pasa a NULLABLE: el pago múltiple no lo captura (el
  usuario no lo pidió para ese flujo); el pago individual lo sigue exigiendo a nivel de
  Pydantic (`PagoClienteCreate.metodo_pago_clave` sigue siendo obligatorio ahí), no a
  nivel de columna.

Todas las columnas nuevas son NULLABLE: los pagos viejos nunca las capturaron y no se
les inventa un valor; `PagoClienteCreate`/`PagoMultipleCreate` las exigen de aquí en
adelante según corresponda.

SQLite no soporta `ALTER` de constraints (FK) ni de nulabilidad fuera de `batch_alter_
table` (migraciones-sqlserver skill) — se rama por dialecto, dejando intacta la ruta de
SQL Server.

Revision ID: c3d8f2a914be
Revises: bf4b31efeac9
Create Date: 2026-11-03 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = 'c3d8f2a914be'
down_revision: str | None = 'bf4b31efeac9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    es_sqlite = op.get_bind().dialect.name == 'sqlite'

    if es_sqlite:
        with op.batch_alter_table('cobranza_factura') as batch:
            batch.add_column(sa.Column('agencia_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_cobranza_factura_agencia', 'agencia', ['agencia_id'], ['agencia_id']
            )
    else:
        op.add_column('cobranza_factura', sa.Column('agencia_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_cobranza_factura_agencia',
            'cobranza_factura',
            'agencia',
            ['agencia_id'],
            ['agencia_id'],
        )

    if es_sqlite:
        with op.batch_alter_table('pago_cliente') as batch:
            batch.add_column(
                sa.Column('forma_pago_clave', sa.Unicode(length=20), nullable=True)
            )
            batch.add_column(sa.Column('fecha_deposito', sa.Date(), nullable=True))
            batch.add_column(sa.Column('numero_pago', sa.Unicode(length=20), nullable=True))
            batch.add_column(sa.Column('cuenta_contable_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_pago_cliente_cuenta_contable',
                'cuenta_contable',
                ['cuenta_contable_id'],
                ['cuenta_contable_id'],
            )
            batch.add_column(sa.Column('pago_multiple_id', sa.Uuid(), nullable=True))
            batch.create_index('ix_pago_cliente_pago_multiple_id', ['pago_multiple_id'])
            batch.alter_column(
                'metodo_pago_clave', existing_type=sa.Unicode(length=20), nullable=True
            )
    else:
        op.add_column(
            'pago_cliente', sa.Column('forma_pago_clave', sa.Unicode(length=20), nullable=True)
        )
        op.add_column('pago_cliente', sa.Column('fecha_deposito', sa.Date(), nullable=True))
        op.add_column(
            'pago_cliente', sa.Column('numero_pago', sa.Unicode(length=20), nullable=True)
        )
        op.add_column(
            'pago_cliente', sa.Column('cuenta_contable_id', sa.Uuid(), nullable=True)
        )
        op.create_foreign_key(
            'fk_pago_cliente_cuenta_contable',
            'pago_cliente',
            'cuenta_contable',
            ['cuenta_contable_id'],
            ['cuenta_contable_id'],
        )
        op.add_column('pago_cliente', sa.Column('pago_multiple_id', sa.Uuid(), nullable=True))
        op.create_index(
            'ix_pago_cliente_pago_multiple_id', 'pago_cliente', ['pago_multiple_id']
        )
        op.alter_column(
            'pago_cliente', 'metodo_pago_clave', existing_type=sa.Unicode(length=20), nullable=True
        )


def downgrade() -> None:
    es_sqlite = op.get_bind().dialect.name == 'sqlite'

    if es_sqlite:
        with op.batch_alter_table('pago_cliente') as batch:
            batch.alter_column(
                'metodo_pago_clave', existing_type=sa.Unicode(length=20), nullable=False
            )
            batch.drop_index('ix_pago_cliente_pago_multiple_id')
            batch.drop_column('pago_multiple_id')
            batch.drop_constraint('fk_pago_cliente_cuenta_contable', type_='foreignkey')
            batch.drop_column('cuenta_contable_id')
            batch.drop_column('numero_pago')
            batch.drop_column('fecha_deposito')
            batch.drop_column('forma_pago_clave')
    else:
        op.alter_column(
            'pago_cliente', 'metodo_pago_clave', existing_type=sa.Unicode(length=20), nullable=False
        )
        op.drop_index('ix_pago_cliente_pago_multiple_id', table_name='pago_cliente')
        op.drop_column('pago_cliente', 'pago_multiple_id')
        op.drop_constraint('fk_pago_cliente_cuenta_contable', 'pago_cliente', type_='foreignkey')
        op.drop_column('pago_cliente', 'cuenta_contable_id')
        op.drop_column('pago_cliente', 'numero_pago')
        op.drop_column('pago_cliente', 'fecha_deposito')
        op.drop_column('pago_cliente', 'forma_pago_clave')

    if es_sqlite:
        with op.batch_alter_table('cobranza_factura') as batch:
            batch.drop_constraint('fk_cobranza_factura_agencia', type_='foreignkey')
            batch.drop_column('agencia_id')
    else:
        op.drop_constraint('fk_cobranza_factura_agencia', 'cobranza_factura', type_='foreignkey')
        op.drop_column('cobranza_factura', 'agencia_id')
