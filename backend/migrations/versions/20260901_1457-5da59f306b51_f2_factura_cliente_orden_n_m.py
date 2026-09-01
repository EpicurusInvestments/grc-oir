"""f2 factura_cliente_orden n:m

Reemplaza `factura_cliente.orden_id` (FK NOT NULL, 1:1) por la tabla puente
`factura_cliente_orden`: una factura al cliente puede cubrir VARIAS órdenes cerradas del
mismo anunciante (facturación múltiple). Es una desviación de la spec BD v2, que define
`OrdenCliente → FacturaCliente` como 1:1 — autorizada por el equipo, ver ADR-064.

Con la columna se va también el índice único filtrado `uq_factura_cliente_orden_vigente`
(ADR-047), que garantizaba "una OC no puede tener dos facturas vigentes". Esa regla NO es
expresable sobre la tabla puente, porque `estado_facturacion` vive en `factura_cliente`;
pasa a validarse en el servicio, que devuelve 409. Es la consecuencia aceptada al aprobar
la desviación, y tiene pruebas propias.

Los datos existentes se COPIAN a la tabla nueva antes de borrar la columna: cada factura
conserva exactamente la orden que tenía.

Revision ID: 5da59f306b51
Revises: 55d7f36d93fd
Create Date: 2026-09-01 14:57:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '5da59f306b51'
down_revision: str | None = '55d7f36d93fd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'factura_cliente_orden',
        sa.Column('factura_id', sa.Uuid(), nullable=False),
        sa.Column('orden_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['factura_id'], ['factura_cliente.factura_id'],
            name='fk_fc_orden_factura', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['orden_id'], ['orden_cliente.orden_id'],
            name='fk_fc_orden_orden', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('factura_id', 'orden_id', name='pk_factura_cliente_orden'),
    )
    # La bandeja "Listas para facturar" hace LEFT JOIN por `orden_id` contra todas las
    # órdenes cerradas en cada carga; sin este índice sería un scan de la puente completa.
    op.create_index('ix_factura_cliente_orden_orden', 'factura_cliente_orden', ['orden_id'])

    # ── Copia de los datos existentes, ANTES de borrar la columna ──
    op.execute(
        'INSERT INTO factura_cliente_orden (factura_id, orden_id) '
        'SELECT factura_id, orden_id FROM factura_cliente'
    )

    # El índice único filtrado se suelta ANTES y en los DOS motores. En SQL Server porque
    # una columna indexada no se puede eliminar; en SQLite porque el batch mode recrea la
    # tabla junto con los índices que refleja, y al llegar a este intentaría reconstruirlo
    # sobre una columna que acaba de desaparecer ("no such column: orden_id").
    op.drop_index('uq_factura_cliente_orden_vigente', table_name='factura_cliente')

    if op.get_bind().dialect.name == 'sqlite':
        # SQLite no soporta ALTER de constraints y rechaza el DROP COLUMN mientras la
        # columna siga nombrada en el DDL de la tabla → batch mode (ADR-063).
        with op.batch_alter_table('factura_cliente') as batch:
            batch.drop_column('orden_id')
    else:
        op.drop_constraint('fk_factura_cliente_orden', 'factura_cliente', type_='foreignkey')
        op.drop_column('factura_cliente', 'orden_id')


def downgrade() -> None:
    # Volver a 1:1 solo es posible si NINGUNA factura cubre más de una orden: con dos
    # órdenes no hay forma de elegir cuál conservar sin perder información. Se aborta con
    # un mensaje claro en vez de descartar datos en silencio.
    conexion = op.get_bind()
    multiples = conexion.execute(
        sa.text(
            'SELECT COUNT(*) FROM (SELECT factura_id FROM factura_cliente_orden '
            'GROUP BY factura_id HAVING COUNT(*) > 1) AS t'
        )
    ).scalar()
    if multiples:
        raise RuntimeError(
            f'No se puede revertir: {multiples} factura(s) cubren varias órdenes. '
            'Reversión imposible sin decidir qué orden conservar en cada una.'
        )

    if conexion.dialect.name == 'sqlite':
        with op.batch_alter_table('factura_cliente') as batch:
            batch.add_column(sa.Column('orden_id', sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                'fk_factura_cliente_orden', 'orden_cliente',
                ['orden_id'], ['orden_id'], ondelete='NO ACTION',
            )
    else:
        op.add_column('factura_cliente', sa.Column('orden_id', sa.Uuid(), nullable=True))
        op.create_foreign_key(
            'fk_factura_cliente_orden', 'factura_cliente', 'orden_cliente',
            ['orden_id'], ['orden_id'], ondelete='NO ACTION',
        )

    op.execute(
        'UPDATE factura_cliente SET orden_id = ('
        'SELECT orden_id FROM factura_cliente_orden '
        'WHERE factura_cliente_orden.factura_id = factura_cliente.factura_id)'
    )

    # La columna nace nullable para poder rellenarla; recuperar el NOT NULL original es
    # parte de dejar el esquema EXACTAMENTE como estaba.
    if conexion.dialect.name == 'sqlite':
        with op.batch_alter_table('factura_cliente') as batch:
            batch.alter_column('orden_id', existing_type=sa.Uuid(), nullable=False)
    else:
        op.alter_column(
            'factura_cliente', 'orden_id', existing_type=sa.Uuid(), nullable=False
        )

    # El índice único filtrado de ADR-047, con el MISMO DDL en ambos motores (SQL Server
    # lo llama filtrado y SQLite parcial, pero la sintaxis coincide).
    op.execute(
        "CREATE UNIQUE INDEX uq_factura_cliente_orden_vigente ON factura_cliente "
        "(orden_id) WHERE estado_facturacion <> 'cancelada'"
    )

    op.drop_index('ix_factura_cliente_orden_orden', table_name='factura_cliente_orden')
    op.drop_table('factura_cliente_orden')
