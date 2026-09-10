/** Llamadas a /api/v1/cobranza (y lecturas cruzadas a F0/F1/F2 para los combos y el
 * detalle, mismo criterio que `facturacion/api.ts` leyendo F1).
 *
 * NO se usa `createCatalogApi`: `CobranzaFactura` no tiene alta propia (la crea el
 * handoff de F2) y `Requisicion`/`MovimientoBancario` tienen máquina de estados o canal
 * dedicado — ninguna encaja en el molde de catálogo con `activo` (mismo criterio que F2).
 *
 * Permisos (ADR-044): `/facturas`, `/facturas/{id}/pagos`, `/pagos/{id}`, `/adjuntos` piden
 * `cobranza:*`; `/requisiciones` y `/movimientos-bancarios` piden `pagos:*` (este último
 * siempre en `leer` — el canal dedicado de Tesorería del ADR-069 vive en el backend, no
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
  MovimientoBancario,
  MovimientoBancarioCreate,
  OpcionCatalogo,
  OrdenInfo,
  PagoCliente,
  PagoClienteConCobranza,
  PagoClienteCreate,
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
  estatus_cobro?: string;
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
  async eliminar(pagoId: string): Promise<void> {
    await apiClient.delete(`${BASE}/pagos/${pagoId}`);
  },
};

/** Historial global de pagos (vista "Pagos recibidos" del mockup). El backend NO tiene un
 *  `GET` de pagos sin acotar a una `CobranzaFactura` (el endpoint real es
 *  `/facturas/{cobranza_id}/pagos`), así que esto arma la vista trayendo las cobranzas con
 *  algo cobrado y pidiendo sus pagos en paralelo. Limitación conocida de esta primera
 *  tanda: no escala a un catálogo de cobranzas enorme (hoy topa en 100, como los combos de
 *  este módulo) — un endpoint agregado quedaría para cuando el volumen lo justifique. */
export async function historialPagosCliente(): Promise<PagoClienteConCobranza[]> {
  const cobranzas = await cobranzaFacturaApi.list({ page: 1, size: 100 });
  const conPagos = cobranzas.items.filter((c) => Number(c.importe_cobrado) > 0);
  const porCobranza = await Promise.all(
    conPagos.map((c) => pagoClienteApi.list(c.cobranza_id, { size: 100 })),
  );
  const combinado: PagoClienteConCobranza[] = [];
  conPagos.forEach((cobranza, i) => {
    for (const pago of porCobranza[i]?.items ?? []) {
      combinado.push({ ...pago, cobranza });
    }
  });
  combinado.sort((a, b) => (a.fecha_pago_cliente < b.fecha_pago_cliente ? 1 : -1));
  return combinado;
}

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
   *  (ADR-069). Áreas sin ese permiso reciben 403 desde el backend. */
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

/** Solo las `autorizada`: son las únicas que se pueden pagar (precondición del backend
 *  al crear la requisición, aunque no la valide por FK — el combo ya la respeta). */
export async function facturasAfiliadoPagables(): Promise<FacturaAfiliadoInfo[]> {
  const { data } = await apiClient.get<Page<FacturaAfiliadoInfo>>("/facturacion/afiliados", {
    params: { estatus_factura_afiliado: "autorizada", size: 100 },
  });
  return data.items;
}

export async function facturasAgenciaPagables(): Promise<FacturaAgenciaInfo[]> {
  const { data } = await apiClient.get<Page<FacturaAgenciaInfo>>("/facturacion/agencias", {
    params: { estatus_factura_agencia: "autorizada", size: 100 },
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
