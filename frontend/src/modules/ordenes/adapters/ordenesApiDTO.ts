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
  /** ADR-067. `subtotal_spots_bonificables` viaja aquí por paridad con el schema del
   *  backend, pero el front no la consume: recalcula el desglose completo en
   *  `totalesOC` (selectors.ts) a partir de `cantidad_spots_bonificables`, igual que ya
   *  hace con `subtotal`/`iva`/`total`. */
  cantidad_spots_bonificables: number;
  subtotal_spots_bonificables: string;
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
  producto_tarifa: string | null;
  estacion_id: string;
  plaza_id: string;
  duracion_spot: string;
  precio_spot: string;
  /** ADR-068. El front SÍ la consume (a diferencia de `subtotal_spots_bonificables` de
   *  OrdenCliente): `oiImporte()` (selectors.ts) recalcula el importe a partir de esta
   *  columna, igual que ya hace con `precio_spot` — `importe_estacion` de este DTO no se
   *  usa (mismo criterio que `subtotal`/`iva`/`total` de `OrdenClienteApiDTO`). */
  cantidad_spots_bonificables: number;
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
  orden_estacion_audio_id: string | null;
  cancelada: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface OrdenEstacionAudioApiDTO {
  orden_estacion_audio_id: string;
  orden_estacion_id: string;
  nombre_archivo: string;
  orden: number;
  created_at: string;
}

/** ADR-109: respuesta de `POST /ordenes/material-staging` — un audio YA subido a S3
 *  ANTES de que exista la OrdenEstacion. `ref` se manda tal cual en `audios` al crear
 *  la OE (`OrdenEstacionCreate.audios`, backend). */
export interface MaterialStagingApiDTO {
  ref: string;
  nombre_archivo: string;
}

/** ADR-119: "Evidencias de lo Transmitido" — lista PLANA (a diferencia de
 *  `OrdenEstacionAudioApiDTO`, sin `orden` ni concepto de default). */
export interface OrdenEstacionEvidenciaApiDTO {
  orden_estacion_evidencia_id: string;
  orden_estacion_id: string;
  nombre_archivo: string;
  created_at: string;
}

/** ADR-123: "Formato de Horarios Reales" — igual que evidencias, pero cualquier
 * formato salvo ejecutables/scripts. */
export interface OrdenEstacionFormatoRealApiDTO {
  orden_estacion_formato_real_id: string;
  orden_estacion_id: string;
  nombre_archivo: string;
  created_at: string;
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

/** ADR-105/ADR-120: bitácora de un envío por correo de un PDF de OrdenEstacion (o del
 * "bundle" de Orden de Transmisión, `tipo_pdf: "orden_transmision"`). */
export interface LogEnvioCorreoApiDTO {
  log_envio_correo_id: string;
  orden_estacion_id: string;
  tipo_pdf: "servicio" | "programados" | "reales" | "orden_transmision";
  destinatario_email: string;
  usuario: string;
  exitoso: boolean;
  mensaje_error: string | null;
  fecha_envio: string;
}
