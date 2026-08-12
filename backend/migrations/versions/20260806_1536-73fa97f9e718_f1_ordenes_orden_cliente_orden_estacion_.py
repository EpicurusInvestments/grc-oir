"""f1 ordenes orden_cliente orden_estacion verificacion incidencia

Revision ID: 73fa97f9e718
Revises: b6d9f2a4c817
Create Date: 2026-08-06 15:36:37.472714

ADVERTENCIA — leer antes de tocar este archivo:
Esta revisión se editó en sitio varias veces (Tanda 2 y Tanda 4 de la auditoría de
compatibilidad RDS: nombres de FK, `ondelete`, índices, columnas de `incidencia`, tipos
explícitos de fecha/hora/texto largo, CHECK de montos/cantidades) porque RDS NUNCA
había visto esta revisión — era seguro seguir editándola en vez de encadenar una
migración nueva solo para esas correcciones.

Esa ventana se cierra en el momento en que esta revisión se aplique a RDS por primera
vez. **Una vez aplicada a RDS, este archivo no se vuelve a editar jamás.** Cualquier
cambio al esquema después de ese punto va en una migración NUEVA, encadenada con
`down_revision = '73fa97f9e718'` (o la que sea el head en ese momento) — nunca
modificando el contenido de una revisión que un `alembic_version` remoto ya referencia.
Editarla después de aplicada deja el `alembic_version` de RDS apuntando a un contenido
que ya no existe en el repositorio, y el equipo pierde la capacidad de reproducir el
esquema desde cero.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# identificadores de revisión, usados por Alembic.
revision: str = '73fa97f9e718'
down_revision: str | None = 'b6d9f2a4c817'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### editado a mano varias veces tras la auditoría de migración a RDS (ver bloque
    # de notas al final de esta función); ya NO es el autogenerado original ###
    op.create_table('orden_cliente',
    sa.Column('orden_id', sa.Uuid(), nullable=False),
    sa.Column('folio_orden', sa.Unicode(length=20), nullable=False),
    sa.Column('numero_orden_cliente', sa.Unicode(length=50), nullable=False),
    sa.Column('fecha_venta', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=False),
    sa.Column('anio_venta', sa.Integer(), nullable=False),
    sa.Column('mes_venta', sa.Integer(), nullable=False),
    sa.Column('empresa_facturadora_id', sa.Uuid(), nullable=False),
    sa.Column('vendedor_principal_id', sa.Uuid(), nullable=False),
    sa.Column('vendedor_secundario_id', sa.Uuid(), nullable=True),
    sa.Column('anunciante_id', sa.Uuid(), nullable=False),
    sa.Column('agencia_id', sa.Uuid(), nullable=True),
    sa.Column('contrato_id', sa.Uuid(), nullable=True),
    sa.Column('marca_id', sa.Uuid(), nullable=True),
    sa.Column('categoria_id', sa.Uuid(), nullable=True),
    sa.Column('producto', sa.Unicode(length=200), nullable=True),
    sa.Column('direccion_facturacion', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('facturacion_directa_cliente', sa.Boolean(), nullable=False),
    sa.Column('afiliado_factura_directo_al_cliente', sa.Boolean(), nullable=False),
    sa.Column('fecha_inicio_campania', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=False),
    sa.Column('fecha_fin_campania', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=False),
    sa.Column('total_dias_campania', sa.Integer(), nullable=False),
    sa.Column('duracion_spot', sa.Unicode(length=10), nullable=False),
    sa.Column('precio_unitario', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('total_spots', sa.Integer(), nullable=False),
    sa.Column('subtotal', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('iva', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('observaciones_predefinidas', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('observaciones_libres', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('estatus_orden', sa.Unicode(length=20), nullable=False),
    sa.Column('estatus_pago_afiliado', sa.Unicode(length=20), nullable=False),
    sa.Column('estatus_pago_agencia', sa.Unicode(length=20), nullable=False),
    sa.Column('archivo_orden_original_path', sa.Unicode(length=500), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.Column('porcentaje_comision_vendedor_principal_snap', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('porcentaje_comision_vendedor_secundario_snap', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('porcentaje_comision_agencia_snap', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('odc_cerrada_ref', sa.Unicode(length=500), nullable=True),
    sa.Column('carta_conciliacion_ref', sa.Unicode(length=500), nullable=True),
    sa.Column('cierre_sin_odc_cerrada', sa.Boolean(), nullable=False),
    sa.Column('cierre_sin_carta_conciliacion', sa.Boolean(), nullable=False),
    sa.Column('fecha_cierre', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=True),
    sa.CheckConstraint("duracion_spot IN ('20s', '30s', '60s', 'mencion')", name='ck_orden_cliente_duracion_spot'),
    sa.CheckConstraint("estatus_orden IN ('recibida', 'capturada', 'en_transmision', 'en_verificacion', 'orden_cerrada', 'facturada', 'cobrada', 'cancelada')", name='ck_orden_cliente_estatus_orden'),
    sa.CheckConstraint("estatus_pago_afiliado IN ('pendiente', 'en_revision', 'pagado')", name='ck_orden_cliente_estatus_pago_afiliado'),
    sa.CheckConstraint("estatus_pago_agencia IN ('pendiente', 'en_revision', 'pagado')", name='ck_orden_cliente_estatus_pago_agencia'),
    sa.CheckConstraint('fecha_fin_campania >= fecha_inicio_campania', name='ck_orden_cliente_fechas_campania'),
    sa.CheckConstraint('porcentaje_comision_agencia_snap IS NULL OR (porcentaje_comision_agencia_snap >= 0 AND porcentaje_comision_agencia_snap <= 100)', name='ck_orden_cliente_comision_ag_snap'),
    sa.CheckConstraint('porcentaje_comision_vendedor_principal_snap IS NULL OR (porcentaje_comision_vendedor_principal_snap >= 0 AND porcentaje_comision_vendedor_principal_snap <= 100)', name='ck_orden_cliente_comision_vp_snap'),
    sa.CheckConstraint('porcentaje_comision_vendedor_secundario_snap IS NULL OR (porcentaje_comision_vendedor_secundario_snap >= 0 AND porcentaje_comision_vendedor_secundario_snap <= 100)', name='ck_orden_cliente_comision_vs_snap'),
    sa.CheckConstraint('precio_unitario >= 0', name='ck_orden_cliente_precio_unitario'),
    sa.CheckConstraint('total_spots > 0', name='ck_orden_cliente_total_spots'),
    sa.CheckConstraint('subtotal >= 0', name='ck_orden_cliente_subtotal'),
    sa.CheckConstraint('iva >= 0', name='ck_orden_cliente_iva'),
    sa.CheckConstraint('total >= 0', name='ck_orden_cliente_total'),
    sa.CheckConstraint('total_dias_campania >= 1', name='ck_orden_cliente_total_dias_campania'),
    sa.CheckConstraint('mes_venta >= 1 AND mes_venta <= 12', name='ck_orden_cliente_mes_venta'),
    sa.ForeignKeyConstraint(['agencia_id'], ['agencia.agencia_id'], name='fk_orden_cliente_agencia', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['anunciante_id'], ['anunciante.anunciante_id'], name='fk_orden_cliente_anunciante', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.categoria_id'], name='fk_orden_cliente_categoria', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['contrato_id'], ['contrato.contrato_id'], name='fk_orden_cliente_contrato', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_orden_cliente_created_by', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['empresa_facturadora_id'], ['empresa_facturadora.empresa_facturadora_id'], name='fk_orden_cliente_empresa_facturadora', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['marca_id'], ['marca.marca_id'], name='fk_orden_cliente_marca', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['vendedor_principal_id'], ['vendedor.vendedor_id'], name='fk_orden_cliente_vendedor_principal', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['vendedor_secundario_id'], ['vendedor.vendedor_id'], name='fk_orden_cliente_vendedor_secundario', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('orden_id')
    )
    op.create_index(op.f('ix_orden_cliente_agencia_id'), 'orden_cliente', ['agencia_id'], unique=False)
    op.create_index(op.f('ix_orden_cliente_anunciante_id'), 'orden_cliente', ['anunciante_id'], unique=False)
    op.create_index(op.f('ix_orden_cliente_contrato_id'), 'orden_cliente', ['contrato_id'], unique=False)
    op.create_index(op.f('ix_orden_cliente_empresa_facturadora_id'), 'orden_cliente', ['empresa_facturadora_id'], unique=False)
    op.create_index(op.f('ix_orden_cliente_estatus_orden'), 'orden_cliente', ['estatus_orden'], unique=False)
    op.create_index(op.f('ix_orden_cliente_folio_orden'), 'orden_cliente', ['folio_orden'], unique=True)
    op.create_index(op.f('ix_orden_cliente_vendedor_principal_id'), 'orden_cliente', ['vendedor_principal_id'], unique=False)
    op.create_table('orden_cliente_vobo_item',
    sa.Column('orden_cliente_vobo_item_id', sa.Uuid(), nullable=False),
    sa.Column('orden_id', sa.Uuid(), nullable=False),
    sa.Column('item_clave', sa.Unicode(length=30), nullable=False),
    sa.Column('completado', sa.Boolean(), nullable=False),
    sa.Column('usuario_id', sa.Uuid(), nullable=True),
    sa.Column('fecha_completado', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.CheckConstraint("item_clave IN ('razon_social', 'plaza', 'emisora', 'duracion', 'tarifa', 'distribucion', 'horario', 'importes', 'audio', 'odc_firmada')", name='ck_orden_cliente_vobo_item_clave'),
    sa.ForeignKeyConstraint(['orden_id'], ['orden_cliente.orden_id'], name='fk_orden_cliente_vobo_item_orden', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.usuario_id'], name='fk_orden_cliente_vobo_item_usuario', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('orden_cliente_vobo_item_id'),
    sa.UniqueConstraint('orden_id', 'item_clave', name='uq_orden_cliente_vobo_item_orden_clave')
    )
    op.create_table('orden_estacion',
    sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
    sa.Column('folio_orden_estacion', sa.Unicode(length=25), nullable=False),
    sa.Column('orden_id', sa.Uuid(), nullable=False),
    sa.Column('numero_orden_estacion', sa.Unicode(length=50), nullable=True),
    sa.Column('contrato_id', sa.Uuid(), nullable=True),
    sa.Column('anunciante_id', sa.Uuid(), nullable=False),
    sa.Column('vendedor_id', sa.Uuid(), nullable=False),
    sa.Column('agencia_id', sa.Uuid(), nullable=True),
    sa.Column('categoria_id', sa.Uuid(), nullable=True),
    sa.Column('producto', sa.Unicode(length=200), nullable=True),
    sa.Column('estacion_id', sa.Uuid(), nullable=False),
    sa.Column('plaza_id', sa.Uuid(), nullable=False),
    sa.Column('duracion_spot', sa.Unicode(length=10), nullable=False),
    sa.Column('precio_spot', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('importe_estacion', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('porcentaje_participacion_oir', sa.Numeric(precision=5, scale=2), nullable=False),
    sa.Column('importe_oir', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('iva_oir', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total_oir', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('importe_emisora', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('iva_emisora', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('total_emisora', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('estatus', sa.Unicode(length=20), nullable=False),
    sa.Column('observaciones_estacion', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.Column('testigos_url', sa.Unicode(length=500), nullable=True),
    sa.Column('testigos_ubicacion_alterna', sa.Unicode(length=300), nullable=True),
    sa.Column('notas_transmision', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('reporte_programados_ref', sa.Unicode(length=500), nullable=True),
    sa.Column('reporte_reales_ref', sa.Unicode(length=500), nullable=True),
    sa.CheckConstraint("duracion_spot IN ('20s', '30s', '60s', 'mencion')", name='ck_orden_estacion_duracion_spot'),
    sa.CheckConstraint("estatus IN ('borrador', 'asignada', 'en_transmision', 'en_revision', 'cerrada', 'cancelada')", name='ck_orden_estacion_estatus'),
    sa.CheckConstraint('porcentaje_participacion_oir >= 0 AND porcentaje_participacion_oir <= 100', name='ck_orden_estacion_pct_oir'),
    sa.CheckConstraint('precio_spot >= 0', name='ck_orden_estacion_precio_spot'),
    sa.CheckConstraint('importe_estacion >= 0', name='ck_orden_estacion_importe_estacion'),
    sa.CheckConstraint('importe_oir >= 0', name='ck_orden_estacion_importe_oir'),
    sa.CheckConstraint('iva_oir >= 0', name='ck_orden_estacion_iva_oir'),
    sa.CheckConstraint('total_oir >= 0', name='ck_orden_estacion_total_oir'),
    sa.CheckConstraint('importe_emisora >= 0', name='ck_orden_estacion_importe_emisora'),
    sa.CheckConstraint('iva_emisora >= 0', name='ck_orden_estacion_iva_emisora'),
    sa.CheckConstraint('total_emisora >= 0', name='ck_orden_estacion_total_emisora'),
    sa.CheckConstraint('ROUND(importe_oir + importe_emisora, 2) = ROUND(importe_estacion, 2)', name='ck_orden_estacion_margen_oir_emisora'),
    sa.CheckConstraint('ROUND(total_oir, 2) = ROUND(importe_oir + iva_oir, 2)', name='ck_orden_estacion_total_oir_suma'),
    sa.CheckConstraint('ROUND(total_emisora, 2) = ROUND(importe_emisora + iva_emisora, 2)', name='ck_orden_estacion_total_emisora_suma'),
    sa.ForeignKeyConstraint(['agencia_id'], ['agencia.agencia_id'], name='fk_orden_estacion_agencia', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['anunciante_id'], ['anunciante.anunciante_id'], name='fk_orden_estacion_anunciante', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['categoria_id'], ['categoria.categoria_id'], name='fk_orden_estacion_categoria', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['contrato_id'], ['contrato.contrato_id'], name='fk_orden_estacion_contrato', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_orden_estacion_created_by', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['estacion_id'], ['estacion.estacion_id'], name='fk_orden_estacion_estacion', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['orden_id'], ['orden_cliente.orden_id'], name='fk_orden_estacion_orden_cliente', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['plaza_id'], ['plaza.plaza_id'], name='fk_orden_estacion_plaza', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['vendedor_id'], ['vendedor.vendedor_id'], name='fk_orden_estacion_vendedor', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('orden_estacion_id')
    )
    op.create_index(op.f('ix_orden_estacion_anunciante_id'), 'orden_estacion', ['anunciante_id'], unique=False)
    op.create_index(op.f('ix_orden_estacion_estacion_id'), 'orden_estacion', ['estacion_id'], unique=False)
    op.create_index(op.f('ix_orden_estacion_estatus'), 'orden_estacion', ['estatus'], unique=False)
    op.create_index(op.f('ix_orden_estacion_folio_orden_estacion'), 'orden_estacion', ['folio_orden_estacion'], unique=True)
    op.create_index(op.f('ix_orden_estacion_orden_id'), 'orden_estacion', ['orden_id'], unique=False)
    op.create_index(op.f('ix_orden_estacion_plaza_id'), 'orden_estacion', ['plaza_id'], unique=False)
    op.create_index(op.f('ix_orden_estacion_vendedor_id'), 'orden_estacion', ['vendedor_id'], unique=False)
    op.create_table('orden_estacion_dia',
    sa.Column('orden_estacion_dia_id', sa.Uuid(), nullable=False),
    sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
    sa.Column('fecha_transmision', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=False),
    sa.Column('hora_inicio', sa.Time().with_variant(mssql.TIME(), 'mssql'), nullable=False),
    sa.Column('hora_fin', sa.Time().with_variant(mssql.TIME(), 'mssql'), nullable=False),
    sa.Column('spots_solicitados', sa.Integer(), nullable=False),
    sa.Column('spots_asignados', sa.Integer(), nullable=False),
    sa.Column('spots_programados', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.CheckConstraint('hora_fin > hora_inicio', name='ck_orden_estacion_dia_horas'),
    sa.CheckConstraint('spots_asignados >= 0', name='ck_orden_estacion_dia_spots_asignados'),
    sa.CheckConstraint('spots_asignados <= spots_solicitados', name='ck_orden_estacion_dia_asignados_max'),
    sa.CheckConstraint('spots_programados IS NULL OR spots_programados >= 0', name='ck_orden_estacion_dia_spots_programados'),
    sa.CheckConstraint('spots_solicitados > 0', name='ck_orden_estacion_dia_spots_solicitados'),
    sa.ForeignKeyConstraint(['orden_estacion_id'], ['orden_estacion.orden_estacion_id'], name='fk_orden_estacion_dia_orden_estacion', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('orden_estacion_dia_id'),
    sa.UniqueConstraint('orden_estacion_id', 'fecha_transmision', 'hora_inicio', name='uq_orden_estacion_dia_oe_fecha_hora')
    )
    op.create_table('verificacion',
    sa.Column('verificacion_id', sa.Uuid(), nullable=False),
    sa.Column('orden_estacion_dia_id', sa.Uuid(), nullable=False),
    sa.Column('spots_verificados', sa.Integer(), nullable=False),
    sa.Column('fecha_verificacion', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=False),
    sa.Column('archivo_nombre', sa.Unicode(length=255), nullable=True),
    sa.Column('archivo_path', sa.Unicode(length=500), nullable=True),
    sa.Column('notas_verificacion', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('reconciliada', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['usuario.usuario_id'], name='fk_verificacion_created_by', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['orden_estacion_dia_id'], ['orden_estacion_dia.orden_estacion_dia_id'], name='fk_verificacion_orden_estacion_dia', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('verificacion_id'),
    sa.UniqueConstraint('orden_estacion_dia_id', name='uq_verificacion_orden_estacion_dia')
    )
    op.create_table('incidencia',
    sa.Column('incidencia_id', sa.Uuid(), nullable=False),
    sa.Column('verificacion_id', sa.Uuid(), nullable=False),
    sa.Column('orden_estacion_id', sa.Uuid(), nullable=False),
    sa.Column('tipo_incidencia', sa.Unicode(length=20), nullable=False),
    sa.Column('spots_ordenados', sa.Integer(), nullable=False),
    sa.Column('spots_ejecutados', sa.Integer(), nullable=False),
    sa.Column('diferencia_spots', sa.Integer(), nullable=False),
    sa.Column('descripcion_incidencia', sa.UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql'), nullable=True),
    sa.Column('fecha_incidencia', sa.Date().with_variant(mssql.DATE(), 'mssql'), nullable=False),
    sa.Column('resolucion', sa.Unicode(length=20), nullable=False),
    sa.Column('monto_ajuste', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('created_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=False),
    sa.Column('updated_at', sa.DateTime().with_variant(mssql.DATETIME2(), 'mssql'), nullable=True),
    sa.CheckConstraint("resolucion IN ('pendiente', 'aceptada', 'credito_cliente', 'descuento_afiliado', 'sin_resolucion')", name='ck_incidencia_resolucion'),
    sa.CheckConstraint("tipo_incidencia IN ('faltante', 'excedente', 'cambio_horario', 'cambio_fecha', 'spot_no_emitido')", name='ck_incidencia_tipo'),
    sa.CheckConstraint('spots_ordenados >= 0', name='ck_incidencia_spots_ordenados'),
    sa.CheckConstraint('spots_ejecutados >= 0', name='ck_incidencia_spots_ejecutados'),
    sa.ForeignKeyConstraint(['orden_estacion_id'], ['orden_estacion.orden_estacion_id'], name='fk_incidencia_orden_estacion', ondelete='NO ACTION'),
    sa.ForeignKeyConstraint(['verificacion_id'], ['verificacion.verificacion_id'], name='fk_incidencia_verificacion', ondelete='NO ACTION'),
    sa.PrimaryKeyConstraint('incidencia_id')
    )
    op.create_index(op.f('ix_incidencia_orden_estacion_id'), 'incidencia', ['orden_estacion_id'], unique=False)
    op.create_index(op.f('ix_incidencia_verificacion_id'), 'incidencia', ['verificacion_id'], unique=False)
    # NOTA: el autogenerate de Alembic reportó aquí "tabla eliminada" para
    # `cuenta_contable`/`constantes_sistema` y cambios de índice en `contrato`/`marca` —
    # falsos positivos por cómo SQLite refleja tipos (CHAR/VARCHAR/DATETIME nativos en vez
    # de los nombres lógicos de la metadata). Se quitaron a mano tras revisar el archivo
    # (regla de la skill migraciones-sqlserver: "revisar SIEMPRE el archivo generado").
    # Esta migración SOLO crea las 6 tablas de F1; no toca nada de F0.
    #
    # Tanda 2 de la auditoría de compatibilidad RDS:
    # - Las 25 FK ahora tienen `name=` explícito (patrón `fk_<tabla>_<columna_sin_id>`,
    #   igual que F0) y `ondelete='NO ACTION'` explícito (documenta la decisión — el
    #   comportamiento no cambia, SQL Server ya asumía NO ACTION por omisión).
    # - 4 índices nuevos, justificados por filtros REALES de
    #   `OrdenClienteRepository`/`OrdenEstacionRepository._apply_filters` (no por FK):
    #   `orden_cliente.estatus_orden`, `orden_cliente.agencia_id`,
    #   `orden_cliente.contrato_id`, `orden_estacion.estatus`. Deliberadamente NO se
    #   indexan `marca_id`/`categoria_id` (OrdenCliente) ni `created_by`/`usuario_id`
    #   en ninguna tabla, ni `fecha_inicio_campania`/`fecha_fin_campania`: ningún
    #   endpoint filtra por ellos hoy (este proyecto usa baja lógica, no DELETE físico,
    #   así que el argumento de "FK sin índice" no aplica aquí).
    # - `incidencia` gana `created_at`/`updated_at` (faltaban — no estaban en la spec,
    #   que no los lista para esta entidad, pero CLAUDE.md §6 los exige en toda
    #   entidad; `resolucion` es mutable, a diferencia de `Verificacion`, que se queda
    #   sin `updated_at` a propósito por ser un registro de evidencia inmutable, mismo
    #   criterio que `LogCambioParametro`).
    #
    # Tanda 4 (revisión del informe de migración a RDS, ADR-036/ADR-037):
    # - `fecha_*`/`hora_*` ahora usan `.with_variant(mssql.DATE()/TIME(), 'mssql')`
    #   explícito (helpers `fecha_sql()`/`hora_sql()` en `core/db.py`): sin esto, el SQL
    #   generado en modo OFFLINE (sin conexión) no puede detectar la versión real del
    #   servidor y cae a `DATETIME` legado — el SQL offline dejaba de ser un preview
    #   fiel. Con conexión real (`alembic upgrade head`) ya renderizaba bien, pero
    #   depender de eso es el mismo tipo de comportamiento implícito que costó el bug
    #   de ADR-014 (`.is_(True)` sobre BIT).
    # - Los 7 campos de texto largo ahora usan `.with_variant(mssql.NVARCHAR(None),
    #   'mssql')` explícito (helper `texto_largo()`): sin esto, `UnicodeText()` compila
    #   a `NTEXT` (deprecado por Microsoft) de forma INCONDICIONAL, no solo en modo
    #   offline. `NTEXT` no funciona bien con Full-Text Search ni funciones de cadena
    #   modernas — problema real para F4 (reportes/búsqueda). F0 (`Categoria`,
    #   `EmpresaFacturadora`) tiene el mismo patrón sin corregir — ticket aparte, fuera
    #   de esta migración; ver ADR-036.
    # - 7 CHECK nuevos en `orden_cliente` (precio_unitario/total_spots/subtotal/iva/
    #   total/total_dias_campania/mes_venta) y 2 en `incidencia` (spots_ordenados/
    #   spots_ejecutados >= 0) — faltaban montos/cantidades sin validar en un sistema
    #   financiero, inconsistente con `orden_estacion_dia` (spots_* >= 0 ya existía) y
    #   `orden_estacion` (rango del % ya existía) en la MISMA migración.
    #   `diferencia_spots`/`monto_ajuste` se dejan libres a propósito (representan
    #   faltante vs. excedente, legítimamente negativos).
    # - Se quitó `ix_orden_cliente_vobo_item_orden_id`: redundante con el UNIQUE
    #   `(orden_id, item_clave)`, que ya sirve como índice para consultas por
    #   `orden_id` solo (columna líder). Costo de escritura sin beneficio de lectura.
    #
    # Tanda 4b (revisión externa del informe, tercera pasada sobre esta migración):
    # - `verificacion` gana `UNIQUE(orden_estacion_dia_id)`: formaliza en el esquema lo
    #   que hoy solo garantiza la máquina de estados de `avanzar_reales` (no puede
    #   correr dos veces sobre la misma OE) — como máximo una Verificacion por día. Su
    #   índice antiguo (`ix_verificacion_orden_estacion_dia_id`) se quitó: el índice
    #   único del `UNIQUE` ya cubre esas consultas.
    # - `verificacion` gana `updated_at` (nulable, sin uso hoy): el argumento de
    #   "registro inmutable" solo se sostiene mientras `reconciliada` sea un campo
    #   MUERTO (se fija siempre en `True` al crear, nada la vuelve a tocar — hallazgo
    #   de esta tanda). Si el negocio pide un flujo con verificaciones no reconciliadas,
    #   la columna haría falta — se agrega ahora por el costo asimétrico (una línea
    #   ahora vs. un `ALTER TABLE` después sobre una base compartida). Ver ADR-038 y
    #   la pregunta de negocio abierta en la ficha del módulo.
    # - `orden_estacion_dia` gana `CHECK(spots_asignados <= spots_solicitados)` —
    #   respaldado por el texto literal de la spec ("Puede ser menor o igual a los
    #   solicitados"). NO se agrega el equivalente para `spots_programados` (sin
    #   respaldo en spec ni prototipo) ni para `spots_verificados` de `Verificacion`
    #   (JAMÁS debe llevar tope: "excedente" es un tipo de incidencia válido).
    # - `orden_estacion_dia` gana `UNIQUE(orden_estacion_id, fecha_transmision,
    #   hora_inicio)`: sin esto, un duplicado de esa combinación (el servicio no lo
    #   valida al crear) infla en silencio las sumas de balance/importe que agregan
    #   sobre estas filas. Se incluye `hora_inicio` porque el prototipo de frontend
    #   permite legítimamente dos franjas horarias distintas el mismo día.
    #
    # Tanda 4c (cuarta pasada, cierre de la auditoría antes de que esta migración se
    # vuelva inmutable):
    # - 8 CHECK nuevos en `orden_estacion` (precio_spot/importe_estacion/importe_oir/
    #   iva_oir/total_oir/importe_emisora/iva_emisora/total_emisora >= 0): la misma
    #   omisión de Tanda 4 (montos sin validar) que ahí solo se corrigió en
    #   `orden_cliente`/`incidencia`. Ninguno es legítimamente negativo: se derivan de
    #   `porcentaje_participacion_oir` (ya acotado 0-100) o de una multiplicación por
    #   una tarifa; a diferencia de `diferencia_spots`/`monto_ajuste` en `Incidencia`,
    #   aquí no existe un caso de ajuste que legitime un valor negativo.
    # - Se quitó `ix_orden_estacion_dia_orden_estacion_id`: redundante con la columna
    #   líder del `UNIQUE(orden_estacion_id, fecha_transmision, hora_inicio)` agregado
    #   en Tanda 4b (mismo criterio ya aplicado a `orden_cliente_vobo_item.orden_id` y
    #   `verificacion.orden_estacion_dia_id`).
    # - Se quitó `ix_orden_estacion_dia_fecha_transmision`: verificado que ningún
    #   endpoint filtra por `fecha_transmision` sola (`listar_dias()` siempre filtra
    #   primero por `orden_estacion_id`) — mismo criterio de "¿hay un filtro real?" ya
    #   usado para no indexar `fecha_inicio_campania`/`fecha_fin_campania` en Tanda 2.
    #
    # Tanda 4d (quinta pasada, sobre las respuestas de la Tanda 4c):
    # - `ck_orden_estacion_dia_spots_solicitados` pasa de `>= 0` a `> 0`: mismo
    #   argumento que `ck_orden_cliente_total_spots` (`> 0`) — un día con cero spots
    #   solicitados no tiene razón de existir como fila.
    # - 3 CHECK nuevos en `orden_estacion`, todos invariantes de SUMA EXACTA, no de
    #   rango: `ck_orden_estacion_margen_oir_emisora` (`importe_oir + importe_emisora
    #   = importe_estacion`), `ck_orden_estacion_total_oir_suma` (`total_oir =
    #   importe_oir + iva_oir`), `ck_orden_estacion_total_emisora_suma`
    #   (`total_emisora = importe_emisora + iva_emisora`). Verificado en el servicio
    #   que las tres se cumplen EXACTO por construcción (sumas/restas entre montos que
    #   YA se redondearon antes de combinarse, no un segundo redondeo independiente).
    #   Los 3 CHECK envuelven ambos lados en `ROUND(x, 2)`: la re-siembra de la demo en
    #   SQLite reveló que `ck_orden_estacion_total_emisora_suma` sin `ROUND` fallaba
    #   para `oe8` (44478.00 + 7116.48 = 51594.48 exacto en Decimal) — SQLite guarda
    #   `NUMERIC` como float64, y esa suma da 51594.479999999996 en float64, que no
    #   calza bit a bit con el float64 del total guardado por separado. SQL Server no
    #   tiene este problema (`NUMERIC(14,2)` ahí es de punto fijo real): `ROUND` es un
    #   no-op inofensivo en el destino real y solo neutraliza el ruido de float64 de
    #   SQLite. Confirmado que `ROUND` no enmascara una violación real de 1 centavo.
    #   Ver ADR-039 (análisis completo e implicación para toda la BD de desarrollo).
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### editado a mano para reflejar cada corrección de upgrade() — mantener en
    # espejo exacto (orden inverso) cada vez que upgrade() cambie ###
    op.drop_index(op.f('ix_incidencia_verificacion_id'), table_name='incidencia')
    op.drop_index(op.f('ix_incidencia_orden_estacion_id'), table_name='incidencia')
    op.drop_table('incidencia')
    op.drop_table('verificacion')
    op.drop_table('orden_estacion_dia')
    op.drop_index(op.f('ix_orden_estacion_vendedor_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_plaza_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_orden_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_folio_orden_estacion'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_estatus'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_estacion_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_anunciante_id'), table_name='orden_estacion')
    op.drop_table('orden_estacion')
    op.drop_table('orden_cliente_vobo_item')
    op.drop_index(op.f('ix_orden_cliente_vendedor_principal_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_folio_orden'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_estatus_orden'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_empresa_facturadora_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_contrato_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_anunciante_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_agencia_id'), table_name='orden_cliente')
    op.drop_table('orden_cliente')
    # ### end Alembic commands ###
