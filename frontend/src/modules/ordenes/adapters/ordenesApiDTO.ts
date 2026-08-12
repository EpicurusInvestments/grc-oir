/** DTOs del backend real de Órdenes (F1, Tanda 3 — API de lectura), alineados a los
 * schemas `*Read` de `backend/app/modules/ordenes/*.py`. Montos/porcentajes DECIMAL
 * viajan como STRING (ADR-015), igual que en `modules/catalogos/*`.
 *
 * Estos DTOs son el "antes" del adaptador (`fromApi.ts`); nadie fuera de `adapters/`
 * debe importarlos — el resto del módulo solo conoce los tipos v5 de `types.ts`.
 */

export interface OrdenClienteApiDTO {
  orden_id: string;
  folio_orden: string;
  numero_orden_cliente: string;
  fecha_venta: string;
  anio_venta: number;
  mes_venta: number;
  empresa_facturadora_id: string;
  vendedor_principal_id: string;
  vendedor_secundario_id: string | null;
  anunciante_id: string;
  agencia_id: string | null;
  contrato_id: string | null;
  marca_id: string | null;
  categoria_id: string | null;
  producto: string | null;
  direccion_facturacion: string | null;
  facturacion_directa_cliente: boolean;
  afiliado_factura_directo_al_cliente: boolean;
  fecha_inicio_campania: string;
  fecha_fin_campania: string;
  total_dias_campania: number;
  duracion_spot: string;
  precio_unitario: string;
  total_spots: number;
  subtotal: string;
  iva: string;
  total: string;
  observaciones_predefinidas: string | null;
  observaciones_libres: string | null;
  estatus_orden: string;
  estatus_pago_afiliado: string;
  estatus_pago_agencia: string;
  archivo_orden_original_path: string | null;
  created_by: string;
  created_at: string;
  updated_at: string | null;
  porcentaje_comision_vendedor_principal_snap: string | null;
  porcentaje_comision_vendedor_secundario_snap: string | null;
  porcentaje_comision_agencia_snap: string | null;
  odc_cerrada_ref: string | null;
  carta_conciliacion_ref: string | null;
  cierre_sin_odc_cerrada: boolean;
  cierre_sin_carta_conciliacion: boolean;
  fecha_cierre: string | null;
}

export interface OrdenClienteVoBoItemApiDTO {
  orden_cliente_vobo_item_id: string;
  orden_id: string;
  item_clave: string;
  completado: boolean;
  usuario_id: string | null;
  fecha_completado: string | null;
}

export interface OrdenEstacionApiDTO {
  orden_estacion_id: string;
  folio_orden_estacion: string;
  orden_id: string;
  numero_orden_estacion: string | null;
  contrato_id: string | null;
  anunciante_id: string;
  vendedor_id: string;
  agencia_id: string | null;
  categoria_id: string | null;
  producto: string | null;
  estacion_id: string;
  plaza_id: string;
  duracion_spot: string;
  precio_spot: string;
  importe_estacion: string;
  porcentaje_participacion_oir: string;
  importe_oir: string;
  iva_oir: string;
  total_oir: string;
  importe_emisora: string;
  iva_emisora: string;
  total_emisora: string;
  estatus: string;
  observaciones_estacion: string | null;
  created_by: string;
  created_at: string;
  updated_at: string | null;
  testigos_url: string | null;
  testigos_ubicacion_alterna: string | null;
  notas_transmision: string | null;
  reporte_programados_ref: string | null;
  reporte_reales_ref: string | null;
}

export interface OrdenEstacionDiaApiDTO {
  orden_estacion_dia_id: string;
  orden_estacion_id: string;
  fecha_transmision: string;
  hora_inicio: string;
  hora_fin: string;
  spots_solicitados: number;
  spots_asignados: number;
  spots_programados: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface VerificacionApiDTO {
  verificacion_id: string;
  orden_estacion_dia_id: string;
  spots_verificados: number;
  fecha_verificacion: string;
  archivo_nombre: string | null;
  archivo_path: string | null;
  notas_verificacion: string | null;
  reconciliada: boolean;
  created_by: string;
  created_at: string;
}

export interface IncidenciaApiDTO {
  incidencia_id: string;
  verificacion_id: string;
  orden_estacion_id: string;
  tipo_incidencia: string;
  spots_ordenados: number;
  spots_ejecutados: number;
  diferencia_spots: number;
  descripcion_incidencia: string | null;
  fecha_incidencia: string;
  resolucion: string;
  monto_ajuste: string | null;
}
