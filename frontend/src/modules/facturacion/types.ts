/** Tipos de F2 — Facturación. Espejo de los schemas `*Read` del backend.
 *
 * Los montos llegan como STRING (el backend serializa `Decimal`, no `float`): se muestran
 * con `formatoMoneda` y NUNCA se operan en el front — todo cálculo vive en el servicio.
 */

// ── Estados ───────────────────────────────────────────────────────────────────
export const ESTADOS_FACTURACION = [
  "preparada",
  "enviada_a_timbrado",
  "timbrada",
  "entregada",
  "cobrada",
  "cancelada",
] as const;
export type EstadoFacturacion = (typeof ESTADOS_FACTURACION)[number];

/** Ciclo de vida SIN la rama de cancelación: es lo que dibuja el timeline del detalle. */
export const FLUJO_FACTURACION = [
  "preparada",
  "enviada_a_timbrado",
  "timbrada",
  "entregada",
  "cobrada",
] as const;

export const ESTADO_FACTURACION_LABEL: Record<EstadoFacturacion, string> = {
  preparada: "Preparada",
  enviada_a_timbrado: "Enviada a timbrado",
  timbrada: "Timbrada",
  entregada: "Entregada",
  cobrada: "Cobrada",
  cancelada: "Cancelada",
};

export const ESTATUS_PROVEEDOR = ["recibida", "en_revision", "autorizada", "pagada"] as const;
export type EstatusProveedor = (typeof ESTATUS_PROVEEDOR)[number];

export const ESTATUS_PROVEEDOR_LABEL: Record<EstatusProveedor, string> = {
  recibida: "Recibida",
  en_revision: "En revisión",
  autorizada: "Autorizada",
  pagada: "Pagada",
};

export const TIPOS_COSTO = ["nomina", "overhead"] as const;
export type TipoCosto = (typeof TIPOS_COSTO)[number];

export const TIPO_COSTO_LABEL: Record<TipoCosto, string> = {
  nomina: "Nómina",
  overhead: "Overhead",
};

// ── FacturaCliente ────────────────────────────────────────────────────────────
export interface FacturaCliente {
  factura_id: string;
  numero_factura: string;
  numero_pedido: string | null;
  referencia_adicional: string | null;
  orden_id: string;
  factura_relacionada_id: string | null;
  empresa_facturadora_id: string;
  anunciante_id: string;
  agencia_id: string | null;
  razon_social_facturacion: string;
  rfc_facturacion: string;
  direccion_facturacion: string | null;
  descripcion_factura: string;
  observaciones_factura: string | null;
  fecha_inicio_transmision: string;
  fecha_fin_transmision: string;
  fecha_factura: string;
  fecha_entrega_factura: string | null;
  subtotal_factura: string;
  iva_factura: string;
  total_factura: string;
  cuenta_contable_id: string;
  metodo_pago_clave: string;
  info_cuenta_pago: string | null;
  layout_factura: string | null;
  estado_facturacion: EstadoFacturacion;
  folio_fiscal_sat: string | null;
  fecha_timbrado: string | null;
  serie_timbrado: string | null;
  xml_path: string | null;
  pdf_path: string | null;
  created_by: string;
  created_at: string;
  updated_at: string | null;
  /** Nombre de la empresa emisora, denormalizado por el backend para la lista. */
  empresa_facturadora: string | null;
}

/** Lo que Facturación captura. Lo derivado y lo calculado los pone el servicio. */
export interface FacturaClienteCreate {
  orden_id: string;
  numero_factura: string;
  numero_pedido?: string | null;
  referencia_adicional?: string | null;
  descripcion_factura: string;
  observaciones_factura?: string | null;
  fecha_factura: string;
  cuenta_contable_id: string;
  metodo_pago_clave: string;
  info_cuenta_pago?: string | null;
  layout_factura?: string | null;
  /** El receptor se DERIVA de la orden; estos tres campos lo sobrescriben si el usuario
   *  los ajusta (la pantalla aprobada los muestra editables). */
  razon_social_facturacion?: string | null;
  rfc_facturacion?: string | null;
  direccion_facturacion?: string | null;
}

export interface TimbrarInput {
  folio_fiscal_sat: string;
  fecha_timbrado: string;
  serie_timbrado?: string | null;
  xml_path?: string | null;
  pdf_path?: string | null;
}

// ── FacturaAfiliado ───────────────────────────────────────────────────────────
export interface FacturaAfiliado {
  factura_afiliado_id: string;
  afiliado_id: string;
  razon_social_afiliada: string | null;
  factura_emisora: string;
  fecha_factura_afiliado: string;
  monto_factura_afiliado: string;
  iva_factura_afiliado: string;
  total_factura_afiliado: string;
  archivo_nombre: string | null;
  archivo_path: string | null;
  estatus_factura_afiliado: EstatusProveedor;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface FacturaAfiliadoCreate {
  afiliado_id: string;
  factura_emisora: string;
  fecha_factura_afiliado: string;
  monto_factura_afiliado: string;
  iva_factura_afiliado: string;
  archivo_nombre?: string | null;
  archivo_path?: string | null;
}

export interface FacturaAfiliadoOrden {
  id: string;
  factura_afiliado_id: string;
  orden_estacion_id: string;
  monto_asignado: string;
  notas_asignacion: string | null;
}

// ── FacturaAgencia ────────────────────────────────────────────────────────────
export interface FacturaAgencia {
  factura_agencia_id: string;
  agencia_id: string;
  orden_id: string;
  folio_factura_agencia: string | null;
  fecha_factura_agencia: string;
  monto_factura_agencia: string;
  iva_factura_agencia: string;
  total_factura_agencia: string;
  porcentaje_comision_agencia: string | null;
  comision_agencia: string | null;
  archivo_nombre: string | null;
  archivo_path: string | null;
  estatus_factura_agencia: EstatusProveedor;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface FacturaAgenciaCreate {
  agencia_id: string;
  orden_id: string;
  folio_factura_agencia?: string | null;
  fecha_factura_agencia: string;
  monto_factura_agencia: string;
  iva_factura_agencia: string;
  /** Si se omite, el backend toma el default del catálogo Agencia. */
  porcentaje_comision_agencia?: string | null;
}

// ── CostoAdicional ────────────────────────────────────────────────────────────
export interface CostoAdicional {
  costo_id: string;
  tipo_costo: TipoCosto;
  orden_id: string | null;
  descripcion_costo: string;
  periodo_contable: string;
  monto_costo: string;
  archivo_nombre: string | null;
  archivo_path: string | null;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface CostoAdicionalCreate {
  tipo_costo: TipoCosto;
  orden_id?: string | null;
  descripcion_costo: string;
  periodo_contable: string;
  monto_costo: string;
}

// ── Apoyo para los combos ─────────────────────────────────────────────────────
/** Subconjunto de `OrdenCliente` (F1) que F2 necesita para elegir qué facturar. */
export interface OrdenFacturable {
  orden_id: string;
  folio_orden: string;
  numero_orden_cliente: string;
  total: string;
  agencia_id: string | null;
}

export interface OpcionCatalogo {
  id: string;
  etiqueta: string;
}

/** Fila de la bandeja "Listas para facturar": OC cerrada que aún no tiene factura.
 *
 * El backend devuelve los NOMBRES ya resueltos (anunciante, agencia, vendedor) para que
 * la tarjeta no dispare tres consultas de catálogo por renglón.
 */
export interface OrdenPorFacturar {
  orden_id: string;
  folio_orden: string;
  numero_orden_cliente: string;
  anunciante: string;
  /** `null` = trato directo con el anunciante, sin agencia. */
  agencia: string | null;
  vendedor: string | null;
  producto: string | null;
  fecha_inicio_campania: string;
  fecha_fin_campania: string;
  subtotal: string;
  total: string;
  // ── Para pre-cargar el formulario de alta (pantalla aprobada) ──
  empresa_emisora: string | null;
  total_spots: number | null;
  duracion_spot: string | null;
  facturacion_directa_cliente: boolean;
  receptor_razon_social: string | null;
  receptor_rfc: string | null;
  receptor_direccion: string | null;
}
