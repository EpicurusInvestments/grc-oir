/** Tipos de F3 — Cobranza y Pagos. Espejo de los schemas `*Read` del backend
 * (`backend/app/modules/cobranza/`).
 *
 * Los montos llegan como STRING (el backend serializa `Decimal`, no `float`): se muestran
 * con `fmtMoneda` y NUNCA se operan en el front — todo cálculo vive en el servicio (mismo
 * criterio que F2).
 */

// ── CobranzaFactura ───────────────────────────────────────────────────────────
export const ESTATUS_COBRO = ["pendiente", "cobro_parcial", "cobrada"] as const;
export type EstatusCobro = (typeof ESTATUS_COBRO)[number];

export const ESTATUS_COBRO_LABEL: Record<EstatusCobro, string> = {
  pendiente: "Pendiente",
  cobro_parcial: "Parcial",
  cobrada: "Cobrada",
};

/** `CobranzaFactura` se crea SOLA al timbrar la `FacturaCliente` (handoff F2→F3,
 * ADR-072): no hay `POST` de alta en este módulo. `importe_cobrado`,
 * `importe_pendiente_cobro`, `vencida` y `numero_factura` los calcula el backend en CADA
 * lectura — nunca se recalculan aquí. */
export interface CobranzaFactura {
  cobranza_id: string;
  factura_id: string;
  anunciante_id: string;
  /** ADR-225: derivado de `FacturaCliente.agencia_id` al crear — `null` si fue
   *  facturación directa. Permite filtrar "facturas pendientes de esta agencia" en el
   *  picker de pago múltiple. */
  agencia_id: string | null;
  metodo_pago_clave: string;
  dias_credito: number;
  fecha_estimada_cobro: string;
  fecha_cobro: string | null;
  estatus_cobro: EstatusCobro;
  comentarios_cobranza: string | null;
  created_by: string;
  created_at: string;
  updated_at: string | null;
  // ── Derivados, calculados por el backend en cada GET ──
  importe_cobrado: string;
  importe_pendiente_cobro: string;
  /** Badge: `fecha_estimada_cobro` ya pasó y NO está cobrada. NUNCA es un valor de
   *  `estatus_cobro` (que solo admite los 3 de arriba). */
  vencida: boolean;
  /** Denormalizado para no obligar una consulta aparte a la lista. */
  numero_factura: string | null;
  /** Petición del usuario (columna "Número de parcialidad"): `numero_pago` del ÚLTIMO
   *  `PagoCliente` de esta cobranza (por `fecha_pago_cliente`, no por captura) — `null`
   *  si aún no hay pagos o el último no lo capturó. */
  ultimo_numero_pago: string | null;
  /** Petición del usuario (tabla de "Facturas disponibles" en Pago Múltiple): cantidad
   *  de pagos ya registrados para esta cobranza + 1, como string — siempre un número,
   *  nunca `null` (por conteo, no por parsear `ultimo_numero_pago`). */
  siguiente_numero_pago: string;
}

/** Único campo editable de `CobranzaFactura` vía `PUT`. */
export interface CobranzaFacturaUpdate {
  metodo_pago_clave?: string | null;
  dias_credito?: number | null;
  comentarios_cobranza?: string | null;
}

// ── PagoCliente ───────────────────────────────────────────────────────────────
export interface PagoCliente {
  pago_cliente_id: string;
  /** ADR-229: `null` = "pago no asignado" todavía a ninguna factura. */
  cobranza_id: string | null;
  fecha_pago_cliente: string;
  monto_aplicado: string;
  /** ADR-225: nullable desde que existe el pago múltiple — ese flujo no lo captura. */
  metodo_pago_clave: string | null;
  referencia_pago: string | null;
  archivo_nombre: string | null;
  archivo_path: string | null;
  // ── ADR-225: se agregan también al pago individual, no solo al múltiple ──
  forma_pago_clave: string | null;
  fecha_deposito: string | null;
  numero_pago: string | null;
  cuenta_contable_id: string | null;
  /** Comparten este id TODOS los `PagoCliente` creados en una misma captura de pago
   *  múltiple (trazabilidad) — `null` en un pago individual. */
  pago_multiple_id: string | null;
  created_by: string;
  created_at: string;
}

/** Lo que CxC captura al registrar un pago individual. */
export interface PagoClienteCreate {
  fecha_pago_cliente: string;
  monto_aplicado: string;
  metodo_pago_clave: string;
  referencia_pago?: string | null;
  archivo_nombre?: string | null;
  archivo_path?: string | null;
  forma_pago_clave: string;
  fecha_deposito?: string | null;
  numero_pago?: string | null;
  cuenta_contable_id: string;
}

/** Una factura seleccionada en el pago múltiple, el monto que se le asigna y SU
 *  parcialidad. ADR-227: `numero_pago` vive AQUÍ (por renglón), no en
 *  `PagoMultipleCreate` — cada factura tiene su propio historial de pagos. */
export interface PagoMultipleItem {
  cobranza_id: string;
  monto_aplicado: string;
  numero_pago?: string | null;
}

/** Pago múltiple (ADR-225, petición del usuario): un solo pago recibido que se reparte
 *  entre varias facturas del MISMO anunciante o agencia — cada factura seleccionada se
 *  registra como su propio `PagoCliente`. */
export interface PagoMultipleCreate {
  fecha_pago_cliente: string;
  /** Lo que de verdad entró — puede ser mayor a la suma de `pagos` (asignación
   *  parcial permitida); el tablero lo llama "Monto por asignar". */
  monto_total_pago: string;
  forma_pago_clave: string;
  fecha_deposito?: string | null;
  referencia_pago?: string | null;
  cuenta_contable_id: string;
  pagos: PagoMultipleItem[];
  /** ADR-230 (petición del usuario): si este lote reparte un pago "huérfano" (sin
   *  asignar) ya existente, aquí va su id — se borra en la misma transacción. */
  pago_origen_id?: string | null;
}

/** ADR-230 (petición del usuario): datos de un pago "huérfano" (sin asignar) que se
 *  precargan en `PagoMultipleForm` para repartirlo entre una o varias facturas. */
export interface PagoHuerfanoOrigen {
  pagoId: string;
  fecha_pago_cliente: string;
  monto_aplicado: string;
  forma_pago_clave: string | null;
  fecha_deposito: string | null;
  referencia_pago: string | null;
  cuenta_contable_id: string | null;
}

/** `PagoCliente` con su `CobranzaFactura` padre embebida — la usa el historial global de
 *  "Pagos recibidos": el backend no expone un `GET` de pagos sin acotar a una cobranza
 *  (`/cobranza/facturas/{cobranza_id}/pagos`), así que el front arma la vista agregando
 *  por cobranza (ver `historialPagosCliente` en `api.ts`). Limitación conocida: no
 *  escala a un volumen muy grande de cobranzas — suficiente para esta primera tanda.
 *  ADR-229: `cobranza` es `null` para un "pago no asignado". */
export interface PagoClienteConCobranza extends PagoCliente {
  cobranza: CobranzaFactura | null;
}

/** ADR-229 (petición del usuario): asigna una factura a un pago capturado sin ella. */
export interface PagoAsignarFacturaRequest {
  cobranza_id: string;
}

// ── Requisicion ───────────────────────────────────────────────────────────────
export const TIPOS_REQUISICION = [
  "pago_afiliado",
  "pago_agencia",
  "comision_vendedor",
  "comision_agencia",
] as const;
export type TipoRequisicion = (typeof TIPOS_REQUISICION)[number];

export const TIPO_REQUISICION_LABEL: Record<TipoRequisicion, string> = {
  pago_afiliado: "Pago afiliado",
  pago_agencia: "Pago agencia",
  // Petición del usuario: el valor interno sigue siendo "comision_vendedor" (spec BD
  // v2, no se renombra) — solo cambia el texto mostrado al usuario.
  comision_vendedor: "Pagos vendedor",
  comision_agencia: "Comisión agencia",
};

export const ESTATUS_REQUISICION = ["pendiente", "autorizada", "pagada", "cancelada"] as const;
export type EstatusRequisicion = (typeof ESTATUS_REQUISICION)[number];

export const ESTATUS_REQUISICION_LABEL: Record<EstatusRequisicion, string> = {
  pendiente: "Pendiente",
  autorizada: "Autorizada",
  pagada: "Pagada",
  cancelada: "Cancelada",
};

export interface Requisicion {
  requisicion_id: string;
  numero_requisicion: string;
  numero_oc_sap: string | null;
  tipo_requisicion: TipoRequisicion;
  factura_afiliado_id: string | null;
  factura_agencia_id: string | null;
  /** Petición del usuario: solo `comision_vendedor` la usa (opcional) — permite cerrar
   *  la `FacturaVendedor` correcta al pagar la requisición. */
  factura_vendedor_id: string | null;
  orden_id: string | null;
  afiliado_id: string | null;
  agencia_id: string | null;
  vendedor_comision_id: string | null;
  /** Derivado del catálogo Afiliado al crear (SÍ es columna persistida, a diferencia de
   *  los importes de `CobranzaFactura`). */
  razon_social_afiliada: string | null;
  monto_requisicion: string;
  porcentaje_comision_vendedor: string | null;
  requisicion_comision_vendedor: string | null;
  porcentaje_comision_agencia_req: string | null;
  requisicion_comision_agencia: string | null;
  /** Monitoreo de márgenes: puede ser NEGATIVA, a propósito. */
  diferencia_afiliada: string | null;
  estatus_requisicion: EstatusRequisicion;
  fecha_pago_requisicion: string | null;
  observaciones_cuentas_por_pagar: string | null;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

/** Las FKs obligatorias dependen de `tipo_requisicion` (el backend las valida, 400 si
 *  falta la que corresponde): `pago_afiliado`→`afiliado_id`; `pago_agencia`→`agencia_id`;
 *  `comision_vendedor`→`vendedor_comision_id`+`orden_id`;
 *  `comision_agencia`→`agencia_id`+`orden_id`. */
export interface RequisicionCreate {
  numero_requisicion: string;
  numero_oc_sap?: string | null;
  tipo_requisicion: TipoRequisicion;
  factura_afiliado_id?: string | null;
  factura_agencia_id?: string | null;
  factura_vendedor_id?: string | null;
  orden_id?: string | null;
  afiliado_id?: string | null;
  agencia_id?: string | null;
  monto_requisicion: string;
  vendedor_comision_id?: string | null;
  /** Si se omiten, el servicio los sugiere del catálogo (Vendedor/Agencia). */
  porcentaje_comision_vendedor?: string | null;
  porcentaje_comision_agencia_req?: string | null;
  observaciones_cuentas_por_pagar?: string | null;
}

export interface RequisicionUpdate {
  numero_oc_sap?: string | null;
  monto_requisicion?: string | null;
  porcentaje_comision_vendedor?: string | null;
  porcentaje_comision_agencia_req?: string | null;
  observaciones_cuentas_por_pagar?: string | null;
}

// ── MovimientoBancario ────────────────────────────────────────────────────────
export const TIPOS_MOVIMIENTO = ["cargo", "abono"] as const;
export type TipoMovimiento = (typeof TIPOS_MOVIMIENTO)[number];

export const TIPO_MOVIMIENTO_LABEL: Record<TipoMovimiento, string> = {
  cargo: "Cargo",
  abono: "Abono",
};

/** Sin máquina de estados: `conciliado` es un booleano de una sola vía (botón
 *  "Conciliar"), sin matching automático en esta versión. */
export interface MovimientoBancario {
  movimiento_id: string;
  fecha_movimiento: string;
  tipo_movimiento: TipoMovimiento;
  monto_movimiento: string;
  referencia_bancaria: string | null;
  descripcion_movimiento: string | null;
  conciliado: boolean;
  archivo_nombre: string | null;
  archivo_path: string | null;
  created_by: string;
  created_at: string;
}

/** Captura manual por Tesorería (canal dedicado, ver `api.ts`). */
export interface MovimientoBancarioCreate {
  fecha_movimiento: string;
  tipo_movimiento: TipoMovimiento;
  monto_movimiento: string;
  referencia_bancaria?: string | null;
  descripcion_movimiento?: string | null;
  archivo_nombre?: string | null;
  archivo_path?: string | null;
}

// ── Apoyo para combos y detalle (subconjuntos de otros módulos que F3 necesita) ──
export interface OpcionCatalogo {
  id: string;
  etiqueta: string;
}

/** Subconjunto de `Anunciante` (F0) para los días de crédito heredados. ADR-174: el
 *  "Contacto cobranza" ya no sale de aquí — consulta `ContactoAnunciante` aparte. */
export interface AnuncianteInfo {
  anunciante_id: string;
  nombre_comercial: string;
  rfc_anunciante: string;
  dias_credito_default: number;
}

/** Subconjunto de `FacturaCliente` (F2) para el bloque "Heredado de factura" del detalle
 *  de cobranza — `CobranzaFacturaRead` ya trae `numero_factura` denormalizado, pero no
 *  estos otros campos descriptivos. */
export interface FacturaClienteResumen {
  factura_id: string;
  numero_factura: string;
  descripcion_factura: string;
  razon_social_facturacion: string;
  agencia_id: string | null;
  total_factura: string;
}

/** Subconjunto de `Afiliado` (F0) para el beneficiario de una requisición. */
export interface AfiliadoInfo {
  afiliado_id: string;
  nombre_afiliado: string;
  razon_social_afiliado: string;
}

/** Subconjunto de `Agencia` (F0), con el % de comisión default para sugerir en
 *  `comision_agencia`. */
export interface AgenciaInfo {
  agencia_id: string;
  nombre_agencia: string;
  rfc_agencia: string;
  porcentaje_comision_agencia_default: string;
}

/** Subconjunto de `Vendedor` (F0), con el % de comisión default para sugerir. */
export interface VendedorInfo {
  vendedor_id: string;
  nombre_vendedor: string;
  porcentaje_comision_default: string | null;
}

/** Subconjunto de `FacturaAfiliado`/`FacturaAgencia` (F2) `autorizada` SIN requisición
 *  ya ligada (petición del usuario, con captura: "ya no deberían aparecer las facturas
 *  que ya tienen requisición de compra"): origen de una requisición de pago. */
export interface FacturaAfiliadoInfo {
  factura_afiliado_id: string;
  afiliado_id: string;
  factura_emisora: string;
  total_factura_afiliado: string;
}

export interface FacturaAgenciaInfo {
  factura_agencia_id: string;
  agencia_id: string;
  orden_id: string;
  folio_factura_agencia: string | null;
  total_factura_agencia: string;
}

/** Subconjunto de `FacturaVendedor` (F2) `autorizada`: origen de una requisición de
 *  `comision_vendedor` (petición del usuario). */
export interface FacturaVendedorInfo {
  factura_vendedor_id: string;
  vendedor_id: string;
  orden_id: string;
  folio_factura_vendedor: string | null;
  total_factura_vendedor: string;
}

/** Subconjunto de `OrdenCliente` (F1): origen de una requisición de comisión. */
export interface OrdenInfo {
  orden_id: string;
  folio_orden: string;
  anunciante_id: string;
  vendedor_principal_id: string;
  total: string;
}
