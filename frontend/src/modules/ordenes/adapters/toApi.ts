/** Construye los bodies de request (vocabulario spec) a partir de los tipos v5 que ya
 * capturan los formularios — dirección INVERSA de `fromApi.ts` (esa LEE de la API; esta
 * ESCRIBE a la API). Ningún formulario cambia: siguen produciendo `OrdenClienteInput`/
 * `OrdenEstacionInput`/etc. tal cual; estas funciones son el único lugar que sabe cómo
 * traducirlos al contrato real del backend (Tanda 5).
 */

import type { AvanzarARealesInput, CerrarOCInput } from "../state/OrdenesContext";
import type { OrdenCliente, OrdenClienteInput, OrdenEstacionInput } from "../types";

// ── OrdenCliente: alta ────────────────────────────────────────────────────────
// ADR-100: sin checklist de Vo.Bo. — la orden se guarda y el backend la pasa directo a
// `capturada`, sin ningún flag que lo pida desde aquí.
export function ordenClienteCreateToApi(input: OrdenClienteInput) {
  return {
    numero_orden_cliente: input.numero_orden_cliente,
    fecha_venta: input.fecha_venta,
    empresa_facturadora_id: input.empresa_facturadora_id,
    vendedor_principal_id: input.vendedor_principal_id,
    vendedor_secundario_id: input.vendedor_secundario_id,
    anunciante_id: input.anunciante_id,
    agencia_id: input.agencia_id,
    contrato_id: input.contrato_id,
    marca_id: input.marca_id,
    categoria_id: input.categoria_id,
    producto: input.producto || null,
    direccion_facturacion: input.direccion_facturacion || null,
    facturacion_directa_cliente: input.facturacion_directa_cliente,
    afiliado_factura_directo_al_cliente: input.afiliado_factura_directo_al_cliente,
    // El backend la llama `archivo_orden_original_path` (nombre de la spec BD v2); el
    // front sigue usando `odc_pdf_ref` internamente (ver types.ts) — este es el único
    // lugar que traduce entre ambos.
    archivo_orden_original_path: input.odc_pdf_ref || null,
    fecha_inicio_campania: input.fecha_inicio_campania,
    fecha_fin_campania: input.fecha_fin_campania,
    duracion_spot: input.duracion_spot,
    precio_unitario: input.precio_unitario,
    total_spots: input.total_spots,
    cantidad_spots_bonificables: input.cantidad_spots_bonificables,
    porcentaje_comision_vendedor_principal_snap: input.porcentaje_comision_vendedor_principal_snap,
    porcentaje_comision_vendedor_secundario_snap: input.porcentaje_comision_vendedor_secundario_snap,
    porcentaje_comision_agencia_snap: input.porcentaje_comision_agencia_snap,
    observaciones_predefinidas: input.observaciones_predefinidas || null,
    observaciones_libres: input.observaciones_libres || null,
  };
}

// ── OrdenCliente: edición normal (PUT) ─────────────────────────────────────────
// Lista blanca deliberada (no "omitir los que no van"): los 3 % de comisión y
// `estatus_orden` NO se mandan aquí — tienen su propio canal (comisiones). `odc_pdf_ref`
// tampoco está en la lista porque su nombre en el backend es distinto
// (`archivo_orden_original_path`) — se agrega aparte, abajo.
const CAMPOS_ACTUALIZABLES = [
  "numero_orden_cliente",
  "fecha_venta",
  "empresa_facturadora_id",
  "vendedor_principal_id",
  "vendedor_secundario_id",
  "anunciante_id",
  "agencia_id",
  "contrato_id",
  "marca_id",
  "categoria_id",
  "producto",
  "direccion_facturacion",
  "facturacion_directa_cliente",
  "afiliado_factura_directo_al_cliente",
  "fecha_inicio_campania",
  "fecha_fin_campania",
  "duracion_spot",
  "precio_unitario",
  "total_spots",
  "cantidad_spots_bonificables",
  "observaciones_predefinidas",
  "observaciones_libres",
] as const satisfies readonly (keyof OrdenCliente)[];

export function ordenClienteUpdateToApi(patch: Partial<OrdenCliente>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const campo of CAMPOS_ACTUALIZABLES) {
    if (campo in patch) body[campo] = patch[campo];
  }
  if ("odc_pdf_ref" in patch) body.archivo_orden_original_path = patch.odc_pdf_ref;
  return body;
}

// ── OrdenCliente: cierre ────────────────────────────────────────────────────────
export function cerrarToApi(input: CerrarOCInput) {
  return {
    odc_cerrada_ref: input.odcCerradaRef,
    carta_conciliacion_ref: input.cartaConciliacionRef,
  };
}

// ── OrdenEstacion: alta ─────────────────────────────────────────────────────────
export function ordenEstacionCreateToApi(ocId: string, input: OrdenEstacionInput) {
  return {
    orden_id: ocId,
    estacion_id: input.estacion_id,
    producto_tarifa: input.producto_tarifa,
    duracion_spot: input.duracion_spot,
    precio_spot: input.precio_spot,
    cantidad_spots_bonificables: input.cantidad_spots_bonificables,
    observaciones_estacion: input.observaciones_estacion || null,
    dias: input.periodo_transmision.map((row) => ({
      fecha_transmision: row.fecha,
      hora_inicio: row.hora_inicio,
      hora_fin: row.hora_termino,
      spots_asignados: row.spots_diarios,
      // ADR-111: en el alta, `orden_estacion_audio_id` de la fila (vista previa) en
      // realidad guarda el `ref` de S3 (los audios ni siquiera tienen id real todavía) —
      // el backend lo resuelve contra `audios` de este mismo payload.
      audio_staging_ref: row.orden_estacion_audio_id || null,
    })),
    // ADR-102: transitorio — el backend solo lo exige si `precio_spot` no coincide con
    // la tarifa sugerida del catálogo.
    motivo_cambio_tarifa: input.motivo_cambio_tarifa || null,
    // ADR-109: material a transmitir ya subido a S3 durante la captura (solo en alta).
    audios: (input.audios_staging ?? []).map((a) => ({ ref: a.ref, nombre_archivo: a.nombre_archivo })),
    // ADR-121: "Reporte del afiliado" — ya se puede adjuntar desde el alta.
    reporte_programados_ref: input.reporte_programados_ref ?? null,
  };
}

// ── OrdenEstacion: edición (corrige errores de captura, antes de transmitir) ────
// `estacion_id`/`plaza_id` del `OrdenEstacionInput` se ignoran a propósito: el backend
// real (`OrdenEstacionUpdate`) no los acepta — reasignar la OE a otra estación/OC sería,
// en la práctica, otra OE distinta.
export function ordenEstacionUpdateToApi(input: OrdenEstacionInput) {
  return {
    producto_tarifa: input.producto_tarifa,
    duracion_spot: input.duracion_spot,
    precio_spot: input.precio_spot,
    cantidad_spots_bonificables: input.cantidad_spots_bonificables,
    observaciones_estacion: input.observaciones_estacion || null,
    dias: input.periodo_transmision.map((row) => ({
      fecha_transmision: row.fecha,
      hora_inicio: row.hora_inicio,
      hora_fin: row.hora_termino,
      spots_asignados: row.spots_diarios,
    })),
    motivo_cambio_tarifa: input.motivo_cambio_tarifa || null,
    // ADR-121: corregible mientras la OE siga editable (antes de 2.3 Reales).
    reporte_programados_ref: input.reporte_programados_ref ?? null,
  };
}

// ── OrdenEstacion: 2.1 → 2.3 (ADR-121: 2.2 ya no es un paso manual — se salta) ──
export function realesToApi(input: AvanzarARealesInput) {
  return {
    dias: input.horariosReales.map((row) => ({ fecha_transmision: row.fecha, spots_verificados: row.spots_diarios })),
    notas_transmision: input.notasTransmision,
    reporte_reales_ref: input.reporteRef ?? null,
  };
}
