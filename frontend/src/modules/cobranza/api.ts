/** Llamadas a /api/v1/cobranza (y lecturas cruzadas a F0/F1/F2 para los combos y el
 * detalle, mismo criterio que `facturacion/api.ts` leyendo F1).
 *
 * NO se usa `createCatalogApi`: `CobranzaFactura` no tiene alta propia (la crea el
 * handoff de F2) y `Requisicion`/`MovimientoBancario` tienen máquina de estados o canal
 * dedicado — ninguna encaja en el molde de catálogo con `activo` (mismo criterio que F2).
 *
 * Permisos (ADR-044): `/facturas`, `/facturas/{id}/pagos`, `/pagos/{id}`, `/adjuntos` piden
 * `cobranza:*`; `/requisiciones` y `/movimientos-bancarios` piden `pagos:*` (este último
 * siempre en `leer` — el canal dedicado de Tesorería del ADR-073 vive en el backend, no
 * aquí). El backend valida siempre; esto solo afecta qué ve cada área.
 */

import { apiClient } from "@/shared/lib/apiClient";
import type { ListParams, Page } from "@/shared/types";

import type {
  AfiliadoInfo,
  AgenciaInfo,
  AnuncianteInfo,
  CobranzaFactura,
  CobranzaFacturaUpdate,
  EstatusRequisicion,
  FacturaAfiliadoInfo,
  FacturaAgenciaInfo,
  FacturaClienteResumen,
  FacturaVendedorInfo,
  MovimientoBancario,
  MovimientoBancarioCreate,
  OpcionCatalogo,
  OrdenInfo,
  PagoCliente,
  PagoClienteCreate,
  PagoGrupo,
  PagoGrupoDetalle,
  PagoMultipleCreate,
  Requisicion,
  RequisicionCreate,
  RequisicionUpdate,
  VendedorInfo,
} from "./types";

const BASE = "/cobranza";

// ── CobranzaFactura ───────────────────────────────────────────────────────────
export interface FiltrosCobranzaFactura extends ListParams {
  factura_id?: string;
  anunciante_id?: string;
  /** ADR-225: filtra el picker de pago múltiple "por agencia". */
  agencia_id?: string;
  estatus_cobro?: string;
}

/** ADR-277 (petición del usuario): "¿este anunciante tiene adeudo vencido?" —
 * consumido por Ventas al seleccionar el anunciante en el alta de OrdenCliente
 * (alerta no bloqueante; el bloqueo real, si excede `monto_maximo_credito`, lo decide
 * el backend al guardar). */
export interface AdeudoVencidoAnunciante {
  anunciante_id: string;
  tiene_adeudo_vencido: boolean;
  suma_adeudo_vencido: string;
}

export async function adeudoVencidoAnuncianteApi(anunciante_id: string) {
  const { data } = await apiClient.get<AdeudoVencidoAnunciante>(
    `${BASE}/anunciantes/${anunciante_id}/adeudo-vencido`,
  );
  return data;
}

export const cobranzaFacturaApi = {
  async list(params?: FiltrosCobranzaFactura) {
    const { data } = await apiClient.get<Page<CobranzaFactura>>(`${BASE}/facturas`, { params });
    return data;
  },
  async get(id: string) {
    const { data } = await apiClient.get<CobranzaFactura>(`${BASE}/facturas/${id}`);
    return data;
  },
  async update(id: string, payload: CobranzaFacturaUpdate) {
    const { data } = await apiClient.put<CobranzaFactura>(`${BASE}/facturas/${id}`, payload);
    return data;
  },
};

// ── PagoCliente ───────────────────────────────────────────────────────────────
export const pagoClienteApi = {
  async list(cobranzaId: string, params?: ListParams) {
    const { data } = await apiClient.get<Page<PagoCliente>>(
      `${BASE}/facturas/${cobranzaId}/pagos`,
      { params },
    );
    return data;
  },
  async crear(cobranzaId: string, payload: PagoClienteCreate) {
    const { data } = await apiClient.post<PagoCliente>(
      `${BASE}/facturas/${cobranzaId}/pagos`,
      payload,
    );
    return data;
  },
  /** ADR-271: solo borra pagos SIN ASIGNAR (el backend rechaza con 400 si ya está
   *  asignado a una factura — para esos, usar `cancelar`). */
  async eliminar(pagoId: string): Promise<void> {
    await apiClient.delete(`${BASE}/pagos/${pagoId}`);
  },
  /** ADR-271 (petición del usuario, "Cancelación de Pago") — "Pagos recibidos"
   *  agrupado por pago global (una fila por pago, no por factura aplicada). */
  async listarAgrupado() {
    const { data } = await apiClient.get<PagoGrupo[]>(`${BASE}/pagos`);
    return data;
  },
  /** Detalle de un pago global: sus facturas aplicadas + el total real del pago. */
  async detalleAgrupado(pagoId: string) {
    const { data } = await apiClient.get<PagoGrupoDetalle>(`${BASE}/pagos/${pagoId}/detalle`);
    return data;
  },
  /** Cancela TODO el pago global (todas las filas que comparten `pago_multiple_id`, o
   *  la única fila si es individual) — baja lógica, las filas se quedan con
   *  `estatus_pago='cancelado'`. ADR-286 (petición del usuario): motivo obligatorio;
   *  SÍ puede deshacer una factura ya `cobrada` — RECHAZA con 409 solo si ya se
   *  autorizó/pagó una comisión (agencia/vendedor/afiliado) con base en ese estado. */
  async cancelar(pagoId: string, motivo: string): Promise<void> {
    await apiClient.post(`${BASE}/pagos/${pagoId}/cancelar`, { motivo });
  },
  /** ADR-225: un `PagoCliente` por cada factura seleccionada, mismo `pago_multiple_id`. */
  async crearMultiple(payload: PagoMultipleCreate) {
    const { data } = await apiClient.post<PagoCliente[]>(`${BASE}/pagos/multiples`, payload);
    return data;
  },
  /** ADR-229 (petición del usuario): captura un pago SIN elegir factura todavía. */
  async crearSinAsignar(payload: PagoClienteCreate) {
    const { data } = await apiClient.post<PagoCliente>(`${BASE}/pagos/no-asignados`, payload);
    return data;
  },
  async listarNoAsignados(params?: ListParams) {
    const { data } = await apiClient.get<Page<PagoCliente>>(`${BASE}/pagos/no-asignados`, {
      params,
    });
    return data;
  },
  /** ADR-231 (petición del usuario): `montoAplicado` puede ser MENOR al monto total
   *  del huérfano — el resto se queda en el propio huérfano (más chico). */
  async asignar(pagoId: string, cobranzaId: string, montoAplicado: string) {
    const { data } = await apiClient.post<PagoCliente>(`${BASE}/pagos/${pagoId}/asignar`, {
      cobranza_id: cobranzaId,
      monto_aplicado: montoAplicado,
    });
    return data;
  },
};

// ── Adjuntos de Cobranza (comprobante de pago, estado de cuenta) ──────────────
export type TipoAdjuntoCobranza = "comprobante_pago" | "estado_cuenta";

export interface AdjuntoCobranzaSubido {
  ref: string;
  nombre_archivo: string;
}

export const adjuntosCobranzaApi = {
  async subir(tipo: TipoAdjuntoCobranza, archivo: File): Promise<AdjuntoCobranzaSubido> {
    const fd = new FormData();
    fd.append("archivo", archivo);
    const { data } = await apiClient.post<AdjuntoCobranzaSubido>(
      `${BASE}/adjuntos?tipo=${tipo}`,
      fd,
    );
    return data;
  },
  async ver(ref: string): Promise<void> {
    const { data } = await apiClient.get<Blob>(`${BASE}/adjuntos`, {
      params: { ref },
      responseType: "blob",
    });
    const url = URL.createObjectURL(data);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombreDeAdjuntoCobranzaRef(ref);
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};

export function nombreDeAdjuntoCobranzaRef(ref: string): string {
  const base = ref.split("/").pop() ?? ref;
  const idx = base.indexOf("_");
  return idx >= 0 ? base.slice(idx + 1) : base;
}

// ── Requisicion ───────────────────────────────────────────────────────────────
export interface FiltrosRequisicion extends ListParams {
  tipo_requisicion?: string;
  estatus_requisicion?: string;
  afiliado_id?: string;
  agencia_id?: string;
  vendedor_comision_id?: string;
}

export const requisicionApi = {
  async list(params?: FiltrosRequisicion) {
    const { data } = await apiClient.get<Page<Requisicion>>(`${BASE}/requisiciones`, { params });
    return data;
  },
  async create(payload: RequisicionCreate) {
    const { data } = await apiClient.post<Requisicion>(`${BASE}/requisiciones`, payload);
    return data;
  },
  async update(id: string, payload: RequisicionUpdate) {
    const { data } = await apiClient.put<Requisicion>(`${BASE}/requisiciones/${id}`, payload);
    return data;
  },
  /** Transiciones OPERATIVAS: `pendiente→cancelada`, `autorizada→pagada|cancelada`.
   *  `autorizada` NO pasa por aquí (403, remite al canal dedicado). */
  async cambiarEstatus(
    id: string,
    estatus: EstatusRequisicion,
    fecha_pago_requisicion?: string | null,
  ) {
    const { data } = await apiClient.post<Requisicion>(`${BASE}/requisiciones/${id}/estatus`, {
      estatus,
      fecha_pago_requisicion: fecha_pago_requisicion ?? null,
    });
    return data;
  },
  /** Canal dedicado: solo Dirección/Admin (ADR-046). */
  async autorizar(id: string) {
    const { data } = await apiClient.post<Requisicion>(`${BASE}/requisiciones/${id}/autorizar`);
    return data;
  },
};

// ── MovimientoBancario ────────────────────────────────────────────────────────
export interface FiltrosMovimientoBancario extends ListParams {
  tipo_movimiento?: string;
  conciliado?: boolean;
  fecha_desde?: string;
  fecha_hasta?: string;
}

export const movimientoBancarioApi = {
  async list(params?: FiltrosMovimientoBancario) {
    const { data } = await apiClient.get<Page<MovimientoBancario>>(
      `${BASE}/movimientos-bancarios`,
      { params },
    );
    return data;
  },
  /** Captura manual — el ROUTER pide `pagos:leer`; el servicio exige Tesorería/Admin
   *  (ADR-073). Áreas sin ese permiso reciben 403 desde el backend. */
  async crear(payload: MovimientoBancarioCreate) {
    const { data } = await apiClient.post<MovimientoBancario>(
      `${BASE}/movimientos-bancarios`,
      payload,
    );
    return data;
  },
  async conciliar(id: string) {
    const { data } = await apiClient.post<MovimientoBancario>(
      `${BASE}/movimientos-bancarios/${id}/conciliar`,
    );
    return data;
  },
};

// ── Apoyo para combos y detalle (leen de F0/F1/F2 por la API, sin importar sus módulos) ──
export async function anunciantesInfo(): Promise<AnuncianteInfo[]> {
  const { data } = await apiClient.get<Page<AnuncianteInfo>>("/catalogos/anunciantes", {
    params: { activo: true, size: 100 },
  });
  return data.items;
}

/** Claves de método de pago sugeridas desde `ConstantesSistema` (no hay FK — mismo
 *  ajuste que F2). */
export async function metodosDePago(): Promise<OpcionCatalogo[]> {
  const { data } = await apiClient.get<Page<{ clave: string; descripcion: string }>>(
    "/catalogos/constantes",
    { params: { grupo: "MetodoPago", activo: true, size: 100 } },
  );
  return data.items.map((c) => ({ id: c.clave, etiqueta: `${c.clave} · ${c.descripcion}` }));
}

export async function afiliadosInfo(): Promise<AfiliadoInfo[]> {
  const { data } = await apiClient.get<Page<AfiliadoInfo>>("/catalogos/afiliados", {
    params: { activo: true, size: 100 },
  });
  return data.items;
}

export async function agenciasInfo(): Promise<AgenciaInfo[]> {
  const { data } = await apiClient.get<Page<AgenciaInfo>>("/catalogos/agencias", {
    params: { activo: true, size: 100 },
  });
  return data.items;
}

export async function vendedoresInfo(): Promise<VendedorInfo[]> {
  const { data } = await apiClient.get<Page<VendedorInfo>>("/catalogos/vendedores", {
    params: { activo: true, size: 100 },
  });
  return data.items;
}

/** Solo las `autorizada` y SIN ninguna requisición ya ligada (petición del usuario, con
 *  captura: "ya no deberían aparecer las facturas que ya tienen requisición de compra"
 *  — antes solo filtraba por estatus y una factura ya usada seguía apareciendo). */
export async function facturasAfiliadoPagables(): Promise<FacturaAfiliadoInfo[]> {
  const { data } = await apiClient.get<FacturaAfiliadoInfo[]>(
    "/cobranza/requisiciones/facturas-afiliado-disponibles",
  );
  return data;
}

export async function facturasAgenciaPagables(): Promise<FacturaAgenciaInfo[]> {
  const { data } = await apiClient.get<FacturaAgenciaInfo[]>(
    "/cobranza/requisiciones/facturas-agencia-disponibles",
  );
  return data;
}

/** Petición del usuario: para que "Comisión vendedor" pueda elegir a cuál
 *  `FacturaVendedor` corresponde (y así cerrarla al pagar la requisición). */
export async function facturasVendedorPagables(): Promise<FacturaVendedorInfo[]> {
  const { data } = await apiClient.get<FacturaVendedorInfo[]>(
    "/cobranza/requisiciones/facturas-vendedor-disponibles",
  );
  return data;
}

/** Fix (reportado por el usuario, con captura): la columna "Origen" de la lista de
 *  Requisiciones resolvía el folio de la factura con los mismos hooks `xxxPagables`
 *  de arriba — pero esos, desde ADR-217, EXCLUYEN cualquier factura ya ligada a una
 *  requisición, así que apenas se creaba la requisición, su propia factura
 *  desaparecía del catálogo y la columna se quedaba en "—". Estas 2 funciones NO
 *  filtran por requisición ya ligada (solo por `estatus == autorizada`, igual que
 *  antes de ADR-217): úsense SOLO para resolver nombres/folios ya existentes, nunca
 *  para ofrecer opciones de un combo de alta (ahí sí se quiere el filtro). */
export async function facturasAfiliadoInfo(): Promise<FacturaAfiliadoInfo[]> {
  const { data } = await apiClient.get<Page<FacturaAfiliadoInfo>>("/facturacion/afiliados", {
    params: { estatus_factura_afiliado: "autorizada", size: 100 },
  });
  return data.items;
}

export async function facturasAgenciaInfo(): Promise<FacturaAgenciaInfo[]> {
  const { data } = await apiClient.get<Page<FacturaAgenciaInfo>>("/facturacion/agencias", {
    params: { estatus_factura_agencia: "autorizada", size: 100 },
  });
  return data.items;
}

/** Petición del usuario: "Pagos vendedor" (antes "Comisión vendedor") se simplificó al
 *  mismo patrón que `pago_agencia` — "Origen del pago" ahora resuelve la factura del
 *  vendedor (ya no la orden directa), con el mismo criterio sin filtro que las otras
 *  2 funciones `xxxInfo` de arriba. */
export async function facturasVendedorInfo(): Promise<FacturaVendedorInfo[]> {
  const { data } = await apiClient.get<Page<FacturaVendedorInfo>>("/facturacion/vendedores", {
    params: { estatus_factura_vendedor: "autorizada", size: 100 },
  });
  return data.items;
}

/** Órdenes para el combo de comisiones (comision_vendedor/comision_agencia): sin filtrar
 *  por estatus_orden — la comisión puede corresponder a una orden ya facturada o cobrada,
 *  no solo cerrada. Trae hasta 100; sin live-search en el backend (limitación conocida). */
export async function ordenesInfo(): Promise<OrdenInfo[]> {
  const { data } = await apiClient.get<Page<OrdenInfo>>("/ordenes/clientes", {
    params: { size: 100 },
  });
  return data.items;
}

/** Datos descriptivos de la `FacturaCliente` de una cobranza, para el bloque "Heredado de
 *  factura" del detalle — `CobranzaFacturaRead` ya trae `numero_factura`, pero no estos. */
export async function facturaClienteResumen(facturaId: string): Promise<FacturaClienteResumen> {
  const { data } = await apiClient.get<FacturaClienteResumen>(`/facturacion/clientes/${facturaId}`);
  return data;
}
