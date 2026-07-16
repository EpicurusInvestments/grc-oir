"""f0 04 facturacion finanzas y usuario

F0-04 — catálogos de facturación/finanzas + modelo base de Usuario:
- `empresa_facturadora`: razón social que emite facturas (RFC único). `direccion_empresa`
  es TEXT en la spec → NVARCHAR(MAX) en SQL Server.
- `vendedor`: incluye el parámetro sensible `porcentaje_comision_default` (auditado en el
  servicio con el mecanismo de F0-03).
- `categoria`: catálogo simple; `nombre_categoria` único (case-insensitive por collation).
- `usuario`: MODELO base para el RBAC (pantalla en F5). Incluye seed de 1 admin (dev.admin).

MetodoPago y CuentaContable se difieren a ConstantesSistema (F0-05); LayoutFactura se omite
(ver ADR-022).

Revision ID: f1a4d0c25e63
Revises: e7f2a9c14b58
Create Date: 2026-07-14 10:00:00.000000
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'f1a4d0c25e63'
down_revision: str | None = 'e7f2a9c14b58'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Id determinista del usuario admin sembrado (para poder borrarlo en downgrade sin ambigüedad).
_SEED_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    # ── EmpresaFacturadora ───────────────────────────────────────────────────────────
    op.create_table(
        'empresa_facturadora',
        sa.Column('empresa_facturadora_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_empresa', sa.Unicode(length=200), nullable=False),
        sa.Column('rfc_empresa', sa.Unicode(length=13), nullable=False),
        # direccion_empresa: TEXT en la spec → NVARCHAR(MAX) en SQL Server / TEXT en SQLite.
        sa.Column('direccion_empresa', sa.UnicodeText(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.PrimaryKeyConstraint('empresa_facturadora_id'),
    )
    op.create_index(op.f('ix_empresa_facturadora_nombre_empresa'), 'empresa_facturadora', ['nombre_empresa'], unique=False)
    op.create_index(op.f('ix_empresa_facturadora_rfc_empresa'), 'empresa_facturadora', ['rfc_empresa'], unique=True)

    # ── Vendedor (con parámetro sensible % comisión) ───────────────────────────────────
    op.create_table(
        'vendedor',
        sa.Column('vendedor_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_vendedor', sa.Unicode(length=160), nullable=False),
        sa.Column('email_vendedor', sa.Unicode(length=160), nullable=True),
        # PARÁMETRO SENSIBLE: % de comisión por defecto (auditado en el servicio).
        sa.Column('porcentaje_comision_default', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.CheckConstraint(
            'porcentaje_comision_default >= 0 AND porcentaje_comision_default <= 100',
            name='ck_vendedor_comision',
        ),
        sa.PrimaryKeyConstraint('vendedor_id'),
    )
    op.create_index(op.f('ix_vendedor_nombre_vendedor'), 'vendedor', ['nombre_vendedor'], unique=False)

    # ── Categoria (nombre único CI) ────────────────────────────────────────────────────
    op.create_table(
        'categoria',
        sa.Column('categoria_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_categoria', sa.Unicode(length=160), nullable=False),
        sa.Column('descripcion_categoria', sa.UnicodeText(), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.PrimaryKeyConstraint('categoria_id'),
    )
    op.create_index(op.f('ix_categoria_nombre_categoria'), 'categoria', ['nombre_categoria'], unique=True)

    # ── Usuario (modelo base para RBAC; pantalla en F5) ────────────────────────────────
    op.create_table(
        'usuario',
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('nombre_usuario', sa.Unicode(length=160), nullable=False),
        sa.Column('email', sa.Unicode(length=160), nullable=False),
        sa.Column('area', sa.Unicode(length=20), nullable=False),
        sa.Column('roles_adicionales', sa.Unicode(length=400), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.CheckConstraint(
            "area IN ('ventas', 'facturacion', 'tesoreria', 'cxc', 'cxp', 'direccion', 'nominas', 'admin')",
            name='ck_usuario_area',
        ),
        sa.PrimaryKeyConstraint('usuario_id'),
    )
    op.create_index(op.f('ix_usuario_email'), 'usuario', ['email'], unique=True)

    # ── Seed: 1 usuario admin, alineado al dev.admin del entorno de desarrollo ─────────
    usuario_tbl = sa.table(
        'usuario',
        sa.column('usuario_id', sa.Uuid()),
        sa.column('nombre_usuario', sa.Unicode(length=160)),
        sa.column('email', sa.Unicode(length=160)),
        sa.column('area', sa.Unicode(length=20)),
        sa.column('roles_adicionales', sa.Unicode(length=400)),
        sa.column('activo', sa.Boolean()),
        sa.column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql')),
    )
    op.bulk_insert(
        usuario_tbl,
        [
            {
                'usuario_id': _SEED_ADMIN_ID,
                'nombre_usuario': 'dev.admin',
                'email': 'dev.admin@grcoir.com',
                'area': 'admin',
                'roles_adicionales': None,
                'activo': True,
                'created_at': datetime(2026, 7, 14, 0, 0, 0),
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM usuario WHERE usuario_id = :id").bindparams(id=_SEED_ADMIN_ID))
    op.drop_index(op.f('ix_usuario_email'), table_name='usuario')
    op.drop_table('usuario')
    op.drop_index(op.f('ix_categoria_nombre_categoria'), table_name='categoria')
    op.drop_table('categoria')
    op.drop_index(op.f('ix_vendedor_nombre_vendedor'), table_name='vendedor')
    op.drop_table('vendedor')
    op.drop_index(op.f('ix_empresa_facturadora_rfc_empresa'), table_name='empresa_facturadora')
    op.drop_index(op.f('ix_empresa_facturadora_nombre_empresa'), table_name='empresa_facturadora')
    op.drop_table('empresa_facturadora')
