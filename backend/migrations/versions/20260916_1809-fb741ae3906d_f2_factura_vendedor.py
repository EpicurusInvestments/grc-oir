"""f2 factura vendedor

Crea `factura_vendedor` — entidad NUEVA, fuera de la spec BD v2 (paridad exacta de
`factura_agencia`, pedida por el usuario para procesar la comisión del vendedor
principal). Por ser nueva, no lleva los campos legado `archivo_nombre`/`archivo_path`
que sí tienen `factura_afiliado`/`factura_agencia` (herencia de la spec original):
va directo a `archivo_pdf_path`/`archivo_xml_path`.

Mismos criterios que `factura_agencia` (ver esa migración y ADR-039/067/068):
`ROUND(x, 2)` en ambos lados del CHECK de suma, `NO ACTION` en todas las FK (sin DELETE
físico en este esquema), y las columnas de archivo NULLABLE sin `server_default`.

Revision ID: fb741ae3906d
Revises: ef082485b930
Create Date: 2026-09-16 18:09:34.359500
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'fb741ae3906d'
down_revision: str | None = 'ef082485b930'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'factura_vendedor',
        sa.Column('factura_vendedor_id', sa.Uuid(), nullable=False),
        sa.Column('vendedor_id', sa.Uuid(), nullable=False),
        sa.Column('orden_id', sa.Uuid(), nullable=False),
        sa.Column('folio_factura_vendedor', sa.Unicode(length=50), nullable=True),
        sa.Column(
            'fecha_factura_vendedor', sa.Date().with_variant(sa.DATE(), 'mssql'), nullable=False
        ),
        sa.Column('monto_factura_vendedor', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('iva_factura_vendedor', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('total_factura_vendedor', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('porcentaje_comision_vendedor', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('comision_vendedor', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('archivo_pdf_path', sa.Unicode(length=500), nullable=True),
        sa.Column('archivo_xml_path', sa.Unicode(length=500), nullable=True),
        sa.Column('estatus_factura_vendedor', sa.Unicode(length=20), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True
        ),
        sa.CheckConstraint(
            "estatus_factura_vendedor IN ('recibida', 'en_revision', 'autorizada', 'pagada')",
            name='ck_factura_vendedor_estatus',
        ),
        sa.CheckConstraint(
            'ROUND(total_factura_vendedor, 2) = '
            'ROUND(monto_factura_vendedor + iva_factura_vendedor, 2)',
            name='ck_factura_vendedor_total_suma',
        ),
        sa.CheckConstraint('comision_vendedor >= 0', name='ck_factura_vendedor_comision'),
        sa.CheckConstraint('iva_factura_vendedor >= 0', name='ck_factura_vendedor_iva'),
        sa.CheckConstraint('monto_factura_vendedor >= 0', name='ck_factura_vendedor_monto'),
        sa.CheckConstraint(
            'porcentaje_comision_vendedor >= 0 AND porcentaje_comision_vendedor <= 100',
            name='ck_factura_vendedor_pct_comision',
        ),
        sa.CheckConstraint('total_factura_vendedor >= 0', name='ck_factura_vendedor_total'),
        sa.ForeignKeyConstraint(
            ['created_by'], ['usuario.usuario_id'],
            name='fk_factura_vendedor_created_by', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['orden_id'], ['orden_cliente.orden_id'],
            name='fk_factura_vendedor_orden', ondelete='NO ACTION',
        ),
        sa.ForeignKeyConstraint(
            ['vendedor_id'], ['vendedor.vendedor_id'],
            name='fk_factura_vendedor_vendedor', ondelete='NO ACTION',
        ),
        sa.PrimaryKeyConstraint('factura_vendedor_id'),
    )


def downgrade() -> None:
    op.drop_table('factura_vendedor')
