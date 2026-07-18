"""f0 05 constantes sistema y cuenta contable

F0-05 — último módulo de la Fase 0. Dos tablas:

- `constantes_sistema`: catálogos SAT/timbrador homogéneos (grupo/clave/descripcion/valor).
  `grupo` es VARCHAR + CHECK con los 9 grupos de la pantalla aprobada (incluye MetodoPago,
  que se difirió de F0-04 y encaja como constante SAT simple). Unicidad natural por
  `(grupo, clave)`: la misma clave puede repetirse entre grupos, pero no dentro de uno.
- `cuenta_contable`: catálogo contable con estructura PROPIA (codigo_cuenta, nombre_cuenta,
  tipo_cuenta ENUM). Se modela como tabla aparte (Opción 2, ADR-024), recuperando lo
  diferido de F0-04 (ADR-022); `tipo_cuenta` es VARCHAR + CHECK (ingreso/costo/gasto/
  activo/pasivo).

Sin seed automático (decisión del equipo): la carga inicial de los catálogos SAT es manual;
la carga masiva CSV llega en la Tanda 2. Portabilidad SQL Server: DATETIME2 con variante,
NVARCHAR (Unicode), CHECK nombrados (ADR-011/014).

Revision ID: b6d9f2a4c817
Revises: f1a4d0c25e63
Create Date: 2026-07-18 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'b6d9f2a4c817'
down_revision: str | None = 'f1a4d0c25e63'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── ConstantesSistema (catálogos SAT/timbrador; incluye el grupo MetodoPago) ──────
    op.create_table(
        'constantes_sistema',
        sa.Column('constante_sistema_id', sa.Uuid(), nullable=False),
        sa.Column('grupo', sa.Unicode(length=40), nullable=False),
        sa.Column('clave', sa.Unicode(length=100), nullable=False),
        sa.Column('descripcion', sa.Unicode(length=400), nullable=False),
        # valor: opcional (p.ej. '33' legacy del timbrador, o la serie 'D').
        sa.Column('valor', sa.Unicode(length=200), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.CheckConstraint(
            "grupo IN ('TipoComprobante', 'Serie', 'RegimenFiscal', 'ClaveProdServ', "
            "'ClaveUnidad', 'UsoCFDI', 'FormaPago', 'MetodoPago', 'MonedaSAT')",
            name='ck_constantes_sistema_grupo',
        ),
        sa.PrimaryKeyConstraint('constante_sistema_id'),
    )
    op.create_index(op.f('ix_constantes_sistema_grupo'), 'constantes_sistema', ['grupo'], unique=False)
    # Unicidad natural: una clave por grupo (bajo collation CI de RDS trata 'PUE'='pue', ADR-017).
    op.create_index(
        'uq_constantes_sistema_grupo_clave', 'constantes_sistema', ['grupo', 'clave'], unique=True
    )

    # ── CuentaContable (tabla propia; recupera lo diferido de F0-04 — ADR-022/024) ────
    op.create_table(
        'cuenta_contable',
        sa.Column('cuenta_contable_id', sa.Uuid(), nullable=False),
        sa.Column('codigo_cuenta', sa.Unicode(length=40), nullable=False),
        sa.Column('nombre_cuenta', sa.Unicode(length=200), nullable=False),
        sa.Column('tipo_cuenta', sa.Unicode(length=20), nullable=False),  # ENUM → VARCHAR + CHECK
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.CheckConstraint(
            "tipo_cuenta IN ('ingreso', 'costo', 'gasto', 'activo', 'pasivo')",
            name='ck_cuenta_contable_tipo',
        ),
        sa.PrimaryKeyConstraint('cuenta_contable_id'),
    )
    op.create_index(
        op.f('ix_cuenta_contable_codigo_cuenta'), 'cuenta_contable', ['codigo_cuenta'], unique=True
    )
    op.create_index(
        op.f('ix_cuenta_contable_nombre_cuenta'), 'cuenta_contable', ['nombre_cuenta'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_cuenta_contable_nombre_cuenta'), table_name='cuenta_contable')
    op.drop_index(op.f('ix_cuenta_contable_codigo_cuenta'), table_name='cuenta_contable')
    op.drop_table('cuenta_contable')
    op.drop_index('uq_constantes_sistema_grupo_clave', table_name='constantes_sistema')
    op.drop_index(op.f('ix_constantes_sistema_grupo'), table_name='constantes_sistema')
    op.drop_table('constantes_sistema')
