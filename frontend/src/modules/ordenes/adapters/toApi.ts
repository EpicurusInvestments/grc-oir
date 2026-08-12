/** Construye los bodies de request (vocabulario spec) a partir de los tipos v5 que ya
 * capturan los formularios — dirección INVERSA de `fromApi.ts` (esa LEE de la API; esta
 * ESCRIBE a la API). Ningún formulario cambia: siguen produciendo `OrdenClienteInput`/
 * `OrdenEstacionInput`/etc. tal cual; estas funciones son el único lugar que sabe cómo
 * traducirlos al contrato real del backend (Tanda 5).
 */

import type { AvanzarARealesInput, CerrarOCInput } from "../state/OrdenesContext";
import type { OrdenCliente, OrdenClienteInput, OrdenEstacionInput, PeriodoTransmisionRow } from "../types";

// ── OrdenCliente: alta ────────────────────────────────────────────────────────
export function ordenClienteCreateToApi(input: OrdenClienteInput, darVobo: boolean) {
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
    fecha_inicio_campania: input.fecha_inicio_campania,
    fecha_fin_campania: input.fecha_fin_campania,
    duracion_spot: input.duracion_spot,
    precio_unitario: input.precio_unitario,
    total_spots: input.total_spots,
    porcentaje_comision_vendedor_principal_snap: input.porcentaje_comision_vendedor_principal_snap,
    porcentaje_comision_vendedor_secundario_snap: input.porcentaje_comision_vendedor_secundario_snap,
    porcentaje_comision_agencia_snap: input.porcentaje_comision_agencia_snap,
    observaciones_predefinidas: input.observaciones_predefinidas || null,
    observaciones_libres: input.observaciones_libres || null,
    revision_checklist: input.revision_checklist,
    dar_vobo: darVobo,
  };
}

// ── OrdenCliente: edición normal (PUT) ─────────────────────────────────────────
// Lista blanca deliberada (no "omitir los que no van"): los 3 % de comisión, el
// checklist, `estatus_orden` y los refs simulados NO se mandan aquí — cada uno tiene su
// propio canal (comisiones, vobo/dar-vobo, cierre) o no existe en el backend real.
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
  "observaciones_predefinidas",
  "observaciones_libres",
] as const satisfies readonly (keyof OrdenCliente)[];

export function ordenClienteUpdateToApi(patch: Partial<OrdenCliente>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const campo of CAMPOS_ACTUALIZABLES) {
    if (campo in patch) body[campo] = patch[campo];
  }
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
    precio_spot: input.precio_spot,
    observaciones_estacion: input.observaciones_estacion || null,
    dias: input.periodo_transmision.map((row) => ({
      fecha_transmision: row.fecha,
      hora_inicio: row.hora_inicio,
      hora_fin: row.hora_termino,
      spots_asignados: row.spots_diarios,
    })),
  };
}

// ── OrdenEstacion: 2.1 → 2.2 ────────────────────────────────────────────────────
export function programadosToApi(horarios: PeriodoTransmisionRow[], reporteRef: string | null | undefined) {
  return {
    dias: horarios.map((row) => ({ fecha_transmision: row.fecha, spots_programados: row.spots_diarios })),
    reporte_programados_ref: reporteRef ?? null,
  };
}

// ── OrdenEstacion: 2.2 → 2.3 ────────────────────────────────────────────────────
export function realesToApi(input: AvanzarARealesInput) {
  return {
    dias: input.horariosReales.map((row) => ({ fecha_transmision: row.fecha, spots_verificados: row.spots_diarios })),
    testigos_url: input.testigosUrl,
    testigos_ubicacion_alterna: input.testigosUbicacionAlterna,
    notas_transmision: input.notasTransmision,
    reporte_reales_ref: input.reporteRef ?? null,
  };
}
