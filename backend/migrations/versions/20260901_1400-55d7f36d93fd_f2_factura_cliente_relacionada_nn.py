"""f2 factura_cliente_relacionada n:n

Reemplaza el self-FK único `factura_cliente.factura_relacionada_id` por una tabla de
relación N:N (`factura_cliente_relacionada`): la pantalla de "Nueva factura" necesita poder
marcar VARIAS facturas relacionadas de un mismo anunciante (control de sustituciones o
facturas canceladas del cliente, no solo un CFDI previo), y CFDI 4.0 sí soporta varios
`CfdiRelacionado` bajo un mismo `TipoRelacion` — el layout del PAC
(`adapter_pac_v40._relacionados`) ya emite esa sección como una fila por documento, así que
extenderla a N filas no cambia el formato (ver ADR-062).

Se verificó en la BD real (RDS `GRC-OIR`) que ninguna `FacturaCliente` existente tenía
`factura_relacionada_id` distinto de NULL (el campo nunca se expuso en el formulario), así
que no hay datos que migrar de la columna vieja a la tabla nueva.

Revision ID: 55d7f36d93fd
Revises: eb36ee5c1a0d
Create Date: 2026-09-01 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# identificadores de revisión, usados por Alembic.
revision: str = '55d7f36d93fd'
down_revision: str | None = 'eb36ee5c1a0d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('fk_factura_cliente_relacionada', 'factura_cliente', type_='foreignkey')
    op.drop_column('factura_cliente', 'factura_relacionada_id')

    op.create_table(
        'factura_cliente_relacionada',
        sa.Column('factura_id', sa.Uuid(), nullable=False),
        sa.Column('relacionada_id', sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            'factura_id <> relacionada_id', name='ck_factura_cliente_relacionada_distinta'
        ),
        sa.ForeignKeyConstraint(
            ['factura_id'], ['factura_cliente.factura_id'],
            name='fk_fc_relacionada_factura', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['relacionada_id'], ['factura_cliente.factura_id'],
            name='fk_fc_relacionada_relacionada', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint(
            'factura_id', 'relacionada_id', name='pk_factura_cliente_relacionada'
        ),
    )


def downgrade() -> None:
    op.drop_table('factura_cliente_relacionada')
    op.add_column(
        'factura_cliente',
        sa.Column('factura_relacionada_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_factura_cliente_relacionada', 'factura_cliente', 'factura_cliente',
        ['factura_relacionada_id'], ['factura_id'], ondelete='NO ACTION',
    )
