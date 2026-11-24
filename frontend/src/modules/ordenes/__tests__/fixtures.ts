/** Builders de fixtures PROPIAS para las pruebas de F1 — no dependen de datos externos, así
 * que un ajuste a otra parte del módulo no puede romper una prueba en silencio.
 *
 * Los catálogos de F0 (anunciantes, contratos, marcas, tarifas…) se leen directo de
 * `state/catalogosCache.ts` donde haga falta: las funciones que los consultan
 * (`marcasDeAnunciante`, `tarifaReferencia`…) están cableadas a esos arreglos del módulo, no
 * reciben el catálogo como parámetro — las pruebas que los necesitan deben poblarlos ellas
 * mismas antes de correr (ver `selectors.test.ts`), ya que nacen vacíos.
 */

import type {
  OrdenClienteApiDTO,
  OrdenEstacionApiDTO,
  OrdenEstacionDiaApiDTO,
} from "../adapters/ordenesApiDTO";
import type { Incidencia, OrdenCliente, OrdenClienteInput, OrdenEstacion, PeriodoTransmisionRow } from "../types";

let contador = 0;
function nextId(prefijo: string): string {
  contador += 1;
  return `${prefijo}-${contador}`;
}

export function makeRow(overrides: Partial<PeriodoTransmisionRow> = {}): PeriodoTransmisionRow {
  return {
    fecha: "2025-06-01",
    hora_inicio: "07:00",
    hora_termino: "08:00",
    spots_diarios: 10,
    // ADR-127: los selectors matchean overrides (`horarios_programados`/`horarios_reales`)
    // contra `periodo_transmision` por este id, no por fecha — una fila y su override
    // deben compartir el mismo id explícitamente (ver `selectors.test.ts`) para que el
    // match funcione en las pruebas, igual que en datos reales (`fromApi.ts`).
    orden_estacion_dia_id: nextId("dia"),
    ...overrides,
  };
}

export function makeOC(overrides: Partial<OrdenCliente> = {}): OrdenCliente {
  return {
    id: nextId("oc"),
    folio_orden: "OC-2025-0001",
    numero_orden_cliente: "PO-TEST-001",
    fecha_venta: "2025-05-01",
    empresa_facturadora_id: "ef1",
    vendedor_principal_id: "v1",
    vendedor_secundario_id: null,
    anunciante_id: "an1",
    agencia_id: null,
    contrato_id: null,
    marca_id: null,
    producto: "Producto de prueba",
    categoria_id: null,
    direccion_facturacion: "Calle Falsa 123",
    facturacion_directa_cliente: false,
    afiliado_factura_directo_al_cliente: false,
    fecha_inicio_campania: "2025-06-01",
    fecha_fin_campania: "2025-06-30",
    producto_tarifa: "spot",
    duracion_spot: "30s",
    total_spots: 100,
    cantidad_spots_bonificables: 0,
    precio_unitario: 1000,
    porcentaje_comision_vendedor_principal_snap: null,
    porcentaje_comision_vendedor_secundario_snap: null,
    porcentaje_comision_agencia_snap: null,
    observaciones_predefinidas: "",
    observaciones_libres: "",
    // ADR-100: sin checklist de Vo.Bo. — una orden recién guardada nace directo en
    // capturada (v5: "orden_cliente_con_vobo"), nunca en "orden_cliente_sin_vobo".
    estatus_orden: "orden_cliente_con_vobo",
    estatus_pago_afiliado: "pendiente",
    estatus_pago_agencia: "pendiente",
    created_by: "tester",
    created_at: "2025-05-01",
    oe_count: 0,
    ...overrides,
  };
}

export function makeOE(overrides: Partial<OrdenEstacion> = {}): OrdenEstacion {
  return {
    id: nextId("oe"),
    folio_orden_interna: "OE-2025-0001A",
    orden_id: "oc-1",
    anunciante_id: "an1",
    estacion_id: "est1",
    plaza_id: "pl1",
    duracion_spot: "30s",
    precio_spot: 800,
    cantidad_spots_bonificables: 0,
    porcentaje_participacion_oir: 20,
    periodo_transmision: [makeRow()],
    estatus: "asignada_afiliado",
    created_at: "2025-06-01",
    ...overrides,
  };
}

/** Input de `crearOC` (state/OrdenesContext.tsx) — mismos defaults que `makeOC`, sin los
 * campos que genera el sistema (id, folio, estatus, auditoría). */
export function makeOCInput(overrides: Partial<OrdenClienteInput> = {}): OrdenClienteInput {
  return {
    numero_orden_cliente: "PO-TEST-001",
    fecha_venta: "2025-05-01",
    empresa_facturadora_id: "ef1",
    vendedor_principal_id: "v1",
    vendedor_secundario_id: null,
    anunciante_id: "an1",
    agencia_id: null,
    contrato_id: null,
    marca_id: null,
    producto: "Producto de prueba",
    categoria_id: null,
    direccion_facturacion: "Calle Falsa 123",
    facturacion_directa_cliente: false,
    afiliado_factura_directo_al_cliente: false,
    fecha_inicio_campania: "2025-06-01",
    fecha_fin_campania: "2025-06-30",
    producto_tarifa: "spot",
    duracion_spot: "30s",
    total_spots: 100,
    cantidad_spots_bonificables: 0,
    precio_unitario: 1000,
    porcentaje_comision_vendedor_principal_snap: null,
    porcentaje_comision_vendedor_secundario_snap: null,
    porcentaje_comision_agencia_snap: null,
    observaciones_predefinidas: "",
    observaciones_libres: "",
    ...overrides,
  };
}

// ── Fixtures DTO (forma cruda del backend, ADR-285) ──────────────────────────────
// A diferencia de `makeOC`/`makeOE` (forma v5, para pruebas que siembran
// `OrdenesProvider` directo), estas construyen la respuesta HTTP tal cual la manda el
// backend — para mockear `paginaOrdenesClienteApi`/`paginaOrdenesEstacionApi` y
// compañía (los hooks de `hooks.ts` las convierten con `fromApi.ts`, igual que en
// producción).
export function makeOCDTO(overrides: Partial<OrdenClienteApiDTO> = {}): OrdenClienteApiDTO {
  return {
    orden_id: nextId("oc"),
    folio_orden: "OC-2025-0001",
    numero_orden_cliente: "PO-TEST-001",
    fecha_venta: "2025-05-01",
    anio_venta: 2025,
    mes_venta: 5,
    empresa_facturadora_id: "ef1",
    vendedor_principal_id: "v1",
    vendedor_secundario_id: null,
    anunciante_id: "an1",
    agencia_id: null,
    contrato_id: null,
    marca_id: null,
    categoria_id: null,
    producto: "Producto de prueba",
    direccion_facturacion: "Calle Falsa 123",
    facturacion_directa_cliente: false,
    afiliado_factura_directo_al_cliente: false,
    fecha_inicio_campania: "2025-06-01",
    fecha_fin_campania: "2025-06-30",
    total_dias_campania: 30,
    producto_tarifa: "spot",
    duracion_spot: "30s",
    precio_unitario: "1000.00",
    total_spots: 100,
    cantidad_spots_bonificables: 0,
    subtotal_spots_bonificables: "0.00",
    subtotal: "100000.00",
    iva: "16000.00",
    total: "116000.00",
    observaciones_predefinidas: null,
    observaciones_libres: null,
    estatus_orden: "capturada",
    estatus_pago_afiliado: "pendiente",
    estatus_pago_agencia: "pendiente",
    archivo_orden_original_path: null,
    created_by: "tester",
    created_at: "2025-05-01T00:00:00",
    updated_at: null,
    porcentaje_comision_vendedor_principal_snap: null,
    porcentaje_comision_vendedor_secundario_snap: null,
    porcentaje_comision_agencia_snap: null,
    odc_cerrada_ref: null,
    carta_conciliacion_ref: null,
    cierre_sin_odc_cerrada: false,
    cierre_sin_carta_conciliacion: false,
    fecha_cierre: null,
    oe_count: 0,
    ...overrides,
  };
}

export function makeOEDTO(overrides: Partial<OrdenEstacionApiDTO> = {}): OrdenEstacionApiDTO {
  return {
    orden_estacion_id: nextId("oe"),
    folio_orden_estacion: "OE-2025-0001A",
    orden_id: "oc-1",
    numero_orden_estacion: null,
    contrato_id: null,
    anunciante_id: "an1",
    vendedor_id: "v1",
    agencia_id: null,
    categoria_id: null,
    producto: null,
    producto_tarifa: "spot",
    estacion_id: "est1",
    plaza_id: "pl1",
    duracion_spot: "30s",
    precio_spot: "800.00",
    cantidad_spots_bonificables: 0,
    importe_estacion: "8000.00",
    porcentaje_participacion_oir: "20.00",
    importe_oir: "1600.00",
    iva_oir: "256.00",
    total_oir: "1856.00",
    importe_emisora: "6400.00",
    iva_emisora: "1024.00",
    total_emisora: "7424.00",
    estatus: "asignada",
    observaciones_estacion: null,
    created_by: "tester",
    created_at: "2025-06-01T00:00:00",
    updated_at: null,
    testigos_url: null,
    testigos_ubicacion_alterna: null,
    notas_transmision: null,
    reporte_programados_ref: null,
    reporte_reales_ref: null,
    ...overrides,
  };
}

export function makeDiaDTO(overrides: Partial<OrdenEstacionDiaApiDTO> = {}): OrdenEstacionDiaApiDTO {
  return {
    orden_estacion_dia_id: nextId("dia"),
    orden_estacion_id: "oe-1",
    fecha_transmision: "2025-06-01",
    hora_inicio: "07:00:00",
    hora_fin: "08:00:00",
    spots_solicitados: 10,
    spots_asignados: 10,
    spots_programados: null,
    orden_estacion_audio_id: null,
    cancelada: false,
    created_at: "2025-06-01T00:00:00",
    updated_at: null,
    ...overrides,
  };
}

export function makeIncidencia(overrides: Partial<Incidencia> = {}): Incidencia {
  return {
    id: nextId("inc"),
    orden_interna_id: "oe-1",
    tipo: "descuento",
    fecha_transmision: "2025-06-01",
    spots_asignados: 10,
    spots_reales: 8,
    diferencia: -2,
    monto_ajuste: -1600,
    nota_excepcion: "Prueba",
    created_at: "2025-06-05",
    ...overrides,
  };
}
