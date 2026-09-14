"""f3-cobranza-pagos

Crea las 4 tablas nuevas del módulo F3 (Cobranza y Pagos):
  - movimiento_bancario
  - cobranza_factura
  - pago_cliente
  - requisicion

Ninguna tabla de F0/F1/F2 se toca en la parte principal de esta migración.

─── Deriva de índices preexistente ───────────────────────────────────────────
`--autogenerate` detectó de paso una desviación de índices AJENA a F3:
  - uq_constantes_sistema_grupo_clave  (constantes_sistema)
  - ix_contrato_estado_contrato        (contrato)
  - ix_marca_nombre_marca              (marca)

Esta deriva existía antes de este módulo y ya la reportaba `alembic check`.

Se corrige CONDICIONALMENTE al final de upgrade()/downgrade():
  - SQLite  (desarrollo local): se OMITE — SQLite no soporta ALTER de
    constraints y las tablas de F3 sí se crean sin problema.
  - SQL Server / mssql (staging y producción): se APLICA normalmente.

De esta forma un solo archivo funciona en ambos entornos sin necesidad de
una migración separada para la deriva.
─────────────────────────────────────────────────────────────────────────────

Revision ID: 19395aa1c258
Revises: f9521496be2e
Create Date: 2026-09-11 20:23:52.571299
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '19395aa1c258'
down_revision: str | None = 'f9521496be2e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Tablas nuevas de F3 ───────────────────────────────────────────────

    op.create_table('movimiento_bancario',
    sa.Column('movimiento_id', sa.Uuid(), nullable=False),
    sa.Column('fecha_movimiento', sa.Date().with_variant(sa.DATE(), 'mssql'), nullable=False),
    sa.Column('tipo_movimiento', sa.Unicode(length=20), nullable=False),
    sa.Column('monto_movimiento', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('referencia_bancaria', sa.Unicode(length=100), nullable=True),
    sa.Column('descripcion_movimiento', sa.Unicode(length=300), nullable=True),
    sa.Column('conciliado', sa.Boolean(), nullable=False),
    sa.Column('archivo_nombre', sa.Unicode(length=255), nullable=True),
    sa.Column('archivo_path', sa.Unicode(length=500), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.CheckConstraint("tipo_movimiento IN ('cargo', 'abono')", name='ck_movimiento_bancario_tipo'),
    sa.CheckConstraint('monto_movimiento > 0', name='ck_movimiento_bancario_monto'),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_movimiento_bancario_created_by', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('movimiento_id')
    )

    op.create_table('cobranza_factura',
    sa.Column('cobranza_id', sa.Uuid(), nullable=False),
    sa.Column('factura_id', sa.Uuid(), nullable=False),
    sa.Column('anunciante_id', sa.Uuid(), nullable=False),
    sa.Column('metodo_pago_clave', sa.Unicode(length=20), nullable=False),
    sa.Column('dias_credito', sa.Integer(), nullable=False),
    sa.Column('fecha_estimada_cobro', sa.Date().with_variant(sa.DATE(), 'mssql'), nullable=False),
    sa.Column('fecha_cobro', sa.Date().with_variant(sa.DATE(), 'mssql'), nullable=True),
    sa.Column('estatus_cobro', sa.Unicode(length=20), nullable=False),
    sa.Column('comentarios_cobranza', sa.UnicodeText().with_variant(sa.NVARCHAR(), 'mssql'), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.CheckConstraint("estatus_cobro IN ('pendiente', 'cobro_parcial', 'cobrada')", name='ck_cobranza_factura_estatus'),
    sa.CheckConstraint('dias_credito >= 0', name='ck_cobranza_factura_dias_credito'),
    sa.ForeignKeyConstraint(['anunciante_id'], ['anunciante.anunciante_id'], name='fk_cobranza_factura_anunciante'),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_cobranza_factura_created_by', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['factura_id'], ['factura_cliente.factura_id'], name='fk_cobranza_factura_factura', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('cobranza_id'),
    sa.UniqueConstraint('factura_id')
    )

    op.create_table('pago_cliente',
    sa.Column('pago_cliente_id', sa.Uuid(), nullable=False),
    sa.Column('cobranza_id', sa.Uuid(), nullable=False),
    sa.Column('fecha_pago_cliente', sa.Date().with_variant(sa.DATE(), 'mssql'), nullable=False),
    sa.Column('monto_aplicado', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('metodo_pago_clave', sa.Unicode(length=20), nullable=False),
    sa.Column('referencia_pago', sa.Unicode(length=100), nullable=True),
    sa.Column('archivo_nombre', sa.Unicode(length=255), nullable=True),
    sa.Column('archivo_path', sa.Unicode(length=500), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.CheckConstraint('monto_aplicado > 0', name='ck_pago_cliente_monto'),
    sa.ForeignKeyConstraint(['cobranza_id'], ['cobranza_factura.cobranza_id'], name='fk_pago_cliente_cobranza', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_pago_cliente_created_by', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('pago_cliente_id')
    )
    op.create_index(op.f('ix_pago_cliente_cobranza_id'), 'pago_cliente', ['cobranza_id'], unique=False)

    op.create_table('requisicion',
    sa.Column('requisicion_id', sa.Uuid(), nullable=False),
    sa.Column('numero_requisicion', sa.Unicode(length=30), nullable=False),
    sa.Column('numero_oc_sap', sa.Unicode(length=30), nullable=True),
    sa.Column('tipo_requisicion', sa.Unicode(length=20), nullable=False),
    sa.Column('factura_afiliado_id', sa.Uuid(), nullable=True),
    sa.Column('factura_agencia_id', sa.Uuid(), nullable=True),
    sa.Column('orden_id', sa.Uuid(), nullable=True),
    sa.Column('afiliado_id', sa.Uuid(), nullable=True),
    sa.Column('agencia_id', sa.Uuid(), nullable=True),
    sa.Column('vendedor_comision_id', sa.Uuid(), nullable=True),
    sa.Column('razon_social_afiliada', sa.Unicode(length=200), nullable=True),
    sa.Column('monto_requisicion', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('porcentaje_comision_vendedor', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('requisicion_comision_vendedor', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('porcentaje_comision_agencia_req', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('requisicion_comision_agencia', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('diferencia_afiliada', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('estatus_requisicion', sa.Unicode(length=20), nullable=False),
    sa.Column('fecha_pago_requisicion', sa.Date().with_variant(sa.DATE(), 'mssql'), nullable=True),
    sa.Column('observaciones_cuentas_por_pagar', sa.UnicodeText().with_variant(sa.NVARCHAR(), 'mssql'), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.CheckConstraint("estatus_requisicion IN ('pendiente', 'autorizada', 'pagada', 'cancelada')", name='ck_requisicion_estatus'),
    sa.CheckConstraint("tipo_requisicion IN ('pago_afiliado', 'pago_agencia', 'comision_vendedor', 'comision_agencia')", name='ck_requisicion_tipo'),
    sa.CheckConstraint('monto_requisicion >= 0', name='ck_requisicion_monto'),
    sa.ForeignKeyConstraint(['afiliado_id'], ['afiliado.afiliado_id'], name='fk_requisicion_afiliado', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['agencia_id'], ['agencia.agencia_id'], name='fk_requisicion_agencia', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_requisicion_created_by', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['factura_afiliado_id'], ['factura_afiliado.factura_afiliado_id'], name='fk_requisicion_factura_afiliado', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['factura_agencia_id'], ['factura_agencia.factura_agencia_id'], name='fk_requisicion_factura_agencia', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['orden_id'], ['orden_cliente.orden_id'], name='fk_requisicion_orden', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['vendedor_comision_id'], ['vendedor.vendedor_id'], name='fk_requisicion_vendedor', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('requisicion_id')
    )

    # ── Deriva de índices preexistente (condicional por dialecto) ─────────
    # SQLite no soporta ALTER de constraints, por eso se omite en local.
    # En SQL Server (staging/producción) sí se aplica normalmente.
    # Ver docstring del módulo para contexto completo.
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_index(op.f('uq_constantes_sistema_grupo_clave'), table_name='constantes_sistema')
        op.create_unique_constraint('uq_constantes_sistema_grupo_clave', 'constantes_sistema', ['grupo', 'clave'])
        op.drop_index(op.f('ix_contrato_estado_contrato'), table_name='contrato')
        op.create_index(op.f('ix_marca_nombre_marca'), 'marca', ['nombre_marca'], unique=False)


def downgrade() -> None:
    # ── Deriva de índices preexistente (condicional por dialecto) ─────────
    # Se revierte solo en SQL Server por la misma razón que en upgrade().
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_index(op.f('ix_marca_nombre_marca'), table_name='marca')
        op.create_index(op.f('ix_contrato_estado_contrato'), 'contrato', ['estado_contrato'], unique=False)
        op.drop_constraint('uq_constantes_sistema_grupo_clave', 'constantes_sistema', type_='unique')
        op.create_index(op.f('uq_constantes_sistema_grupo_clave'), 'constantes_sistema', ['grupo', 'clave'], unique=1)

    # ── Tablas de F3 (se eliminan en orden inverso por dependencias FK) ───
    op.drop_table('requisicion')
    op.drop_index(op.f('ix_pago_cliente_cobranza_id'), table_name='pago_cliente')
    op.drop_table('pago_cliente')
    op.drop_table('cobranza_factura')
    op.drop_table('movimiento_bancario')
