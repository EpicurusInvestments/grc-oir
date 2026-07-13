"""f0 03 contrato

Tanda 3 de F0-03 (catálogos comerciales):
- `contrato`: contrato comercial de un anunciante (FK NOT NULL). Incluye el parámetro
  sensible `porcentaje_comision_contrato` (auditado en el servicio), la máquina de estados
  `estado_contrato` (CHECK), `fecha_fin >= fecha_inicio` (CHECK), `created_by` (texto) y
  `archivo_contrato_path` (prefijo del contrato en S3; subida diferida).

Revision ID: e7f2a9c14b58
Revises: d5b8c2a71f36
Create Date: 2026-07-11 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = 'e7f2a9c14b58'
down_revision: str | None = 'd5b8c2a71f36'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'contrato',
        sa.Column('contrato_id', sa.Uuid(), nullable=False),
        sa.Column('anunciante_id', sa.Uuid(), nullable=False),
        sa.Column('numero_contrato', sa.Unicode(length=60), nullable=False),
        sa.Column('nombre_contrato', sa.Unicode(length=200), nullable=False),
        sa.Column('fecha_inicio_contrato', sa.Date(), nullable=False),
        sa.Column('fecha_fin_contrato', sa.Date(), nullable=False),
        sa.Column('monto_contrato', sa.Numeric(precision=14, scale=2), nullable=True),
        # PARÁMETRO SENSIBLE: % de comisión del contrato (sobreescribe el default de la agencia).
        sa.Column('porcentaje_comision_contrato', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('condiciones_comerciales', sa.Unicode(length=4000), nullable=True),
        sa.Column('estado_contrato', sa.Unicode(length=20), nullable=False),
        # archivo_contrato_path: prefijo del contrato en S3 (contratos/<numero>/). Subida diferida.
        sa.Column('archivo_contrato_path', sa.Unicode(length=400), nullable=True),
        sa.Column('observaciones_contrato', sa.Unicode(length=1000), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        # created_by: username del capturista (texto, no FK: no hay tabla Usuario hasta F0-04).
        sa.Column('created_by', sa.Unicode(length=150), nullable=True),
        sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
        sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
        sa.CheckConstraint(
            "estado_contrato IN ('vigente', 'suspendido', 'finalizado', 'cancelado')",
            name='ck_contrato_estado',
        ),
        sa.CheckConstraint('fecha_fin_contrato >= fecha_inicio_contrato', name='ck_contrato_fechas'),
        sa.CheckConstraint(
            'porcentaje_comision_contrato IS NULL OR '
            '(porcentaje_comision_contrato >= 0 AND porcentaje_comision_contrato <= 100)',
            name='ck_contrato_comision',
        ),
        sa.ForeignKeyConstraint(['anunciante_id'], ['anunciante.anunciante_id'], name='fk_contrato_anunciante'),
        sa.PrimaryKeyConstraint('contrato_id'),
    )
    op.create_index(op.f('ix_contrato_anunciante_id'), 'contrato', ['anunciante_id'], unique=False)
    op.create_index(op.f('ix_contrato_numero_contrato'), 'contrato', ['numero_contrato'], unique=False)
    op.create_index(op.f('ix_contrato_estado_contrato'), 'contrato', ['estado_contrato'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_contrato_estado_contrato'), table_name='contrato')
    op.drop_index(op.f('ix_contrato_numero_contrato'), table_name='contrato')
    op.drop_index(op.f('ix_contrato_anunciante_id'), table_name='contrato')
    op.drop_table('contrato')
