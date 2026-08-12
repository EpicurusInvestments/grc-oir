/** Builders de fixtures PROPIAS para las pruebas de F1 — no dependen de datos externos, así
 * que un ajuste a otra parte del módulo no puede romper una prueba en silencio.
 *
 * Los catálogos de F0 (anunciantes, contratos, marcas, tarifas…) se leen directo de
 * `state/catalogosCache.ts` donde haga falta: las funciones que los consultan
 * (`marcasDeAnunciante`, `tarifaReferencia`…) están cableadas a esos arreglos del módulo, no
 * reciben el catálogo como parámetro — las pruebas que los necesitan deben poblarlos ellas
 * mismas antes de correr (ver `selectors.test.ts`), ya que nacen vacíos.
 */

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
    duracion_spot: "30s",
    total_spots: 100,
    precio_unitario: 1000,
    porcentaje_comision_vendedor_principal_snap: null,
    porcentaje_comision_vendedor_secundario_snap: null,
    porcentaje_comision_agencia_snap: null,
    observaciones_predefinidas: "",
    observaciones_libres: "",
    revision_checklist: {},
    estatus_orden: "orden_cliente_sin_vobo",
    estatus_pago_afiliado: "pendiente",
    estatus_pago_agencia: "pendiente",
    created_by: "tester",
    created_at: "2025-05-01",
    ...overrides,
  };
}

export function makeOE(overrides: Partial<OrdenEstacion> = {}): OrdenEstacion {
  return {
    id: nextId("oe"),
    folio_orden_interna: "OE-2025-0001A",
    orden_id: "oc-1",
    estacion_id: "est1",
    plaza_id: "pl1",
    precio_spot: 800,
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
    duracion_spot: "30s",
    total_spots: 100,
    precio_unitario: 1000,
    porcentaje_comision_vendedor_principal_snap: null,
    porcentaje_comision_vendedor_secundario_snap: null,
    porcentaje_comision_agencia_snap: null,
    observaciones_predefinidas: "",
    observaciones_libres: "",
    revision_checklist: {},
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
