/** Llamadas a /api/v1/facturacion.
 *
 * NO se usa `createCatalogApi` ni `CatalogApi`: esas piezas asumen un CRUD de catálogo con
 * baja lógica (`setEstado`), y ninguna entidad de F2 la tiene (ADR-035, mismo criterio que
 * F1). Las transiciones de estado tampoco caben en ese molde: cada una es un endpoint
 * dedicado con su propio payload.
 *
 * Ojo con los permisos: `/clientes/*` exige `facturacion:*` y el resto `costos:*`
 * (ADR-044). El backend valida siempre; aquí eso solo afecta a qué ve cada área.
 */

import { apiClient } from "@/shared/lib/apiClient";
import type { ListParams, Page } from "@/shared/types";

import type {
  CostoAdicional,
  CostoAdicionalCreate,
  EstatusProveedor,
  FacturaAfiliado,
  FacturaAfiliadoCreate,
  FacturaAfiliadoOrden,
  FacturaAgencia,
  FacturaAgenciaCreate,
  FacturaCliente,
  FacturaClienteCreate,
  OpcionCatalogo,
  OrdenFacturable,
  TimbrarInput,
} from "./types";

const BASE = "/facturacion";

// ── FacturaCliente ────────────────────────────────────────────────────────────
export interface FiltrosFacturaCliente extends ListParams {
  estado_facturacion?: string;
  orden_id?: string;
}

export const facturaClienteApi = {
  async list(params?: FiltrosFacturaCliente) {
    const { data } = await apiClient.get<Page<FacturaCliente>>(`${BASE}/clientes`, { params });
    return data;
  },
  async create(payload: FacturaClienteCreate) {
    const { data } = await apiClient.post<FacturaCliente>(`${BASE}/clientes`, payload);
    return data;
  },
  async enviarATimbrado(id: string) {
    const { data } = await apiClient.post<FacturaCliente>(
      `${BASE}/clientes/${id}/enviar-a-timbrado`,
    );
    return data;
  },
  async timbrar(id: string, payload: TimbrarInput) {
    const { data } = await apiClient.post<FacturaCliente>(`${BASE}/clientes/${id}/timbrar`, payload);
    return data;
  },
  async entregar(id: string, fecha_entrega_factura?: string | null) {
    const { data } = await apiClient.post<FacturaCliente>(`${BASE}/clientes/${id}/entregar`, {
      fecha_entrega_factura: fecha_entrega_factura ?? null,
    });
    return data;
  },
  async cancelar(id: string) {
    const { data } = await apiClient.post<FacturaCliente>(`${BASE}/clientes/${id}/cancelar`);
    return data;
  },
  /** Descarga el archivo para el timbrador. OJO: hoy es un BORRADOR, no el layout real. */
  async descargarArchivoPlano(id: string, numeroFactura: string) {
    const { data } = await apiClient.get(`${BASE}/clientes/${id}/archivo-plano`, {
      responseType: "blob",
    });
    // `<a download>` y no `window.open`: una blob URL no lleva nombre de archivo y el
    // navegador propondría uno genérico (mismo motivo que en los adjuntos de F1).
    const url = URL.createObjectURL(data as Blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = `BORRADOR_${numeroFactura}.txt`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    URL.revokeObjectURL(url);
  },
};

// ── FacturaAfiliado ───────────────────────────────────────────────────────────
export interface FiltrosFacturaAfiliado extends ListParams {
  estatus_factura_afiliado?: string;
  afiliado_id?: string;
}

export const facturaAfiliadoApi = {
  async list(params?: FiltrosFacturaAfiliado) {
    const { data } = await apiClient.get<Page<FacturaAfiliado>>(`${BASE}/afiliados`, { params });
    return data;
  },
  async create(payload: FacturaAfiliadoCreate) {
    const { data } = await apiClient.post<FacturaAfiliado>(`${BASE}/afiliados`, payload);
    return data;
  },
  async asignaciones(id: string) {
    const { data } = await apiClient.get<FacturaAfiliadoOrden[]>(`${BASE}/afiliados/${id}/ordenes`);
    return data;
  },
  /** Transiciones operativas de CxP. `autorizada` NO pasa por aquí (403). */
  async cambiarEstatus(id: string, estatus: EstatusProveedor) {
    const { data } = await apiClient.post<FacturaAfiliado>(`${BASE}/afiliados/${id}/estatus`, {
      estatus,
    });
    return data;
  },
  /** Canal dedicado: solo Dirección/Admin (ADR-046). */
  async autorizar(id: string) {
    const { data } = await apiClient.post<FacturaAfiliado>(`${BASE}/afiliados/${id}/autorizar`);
    return data;
  },
};

// ── FacturaAgencia ────────────────────────────────────────────────────────────
export interface FiltrosFacturaAgencia extends ListParams {
  estatus_factura_agencia?: string;
  orden_id?: string;
}

export const facturaAgenciaApi = {
  async list(params?: FiltrosFacturaAgencia) {
    const { data } = await apiClient.get<Page<FacturaAgencia>>(`${BASE}/agencias`, { params });
    return data;
  },
  async create(payload: FacturaAgenciaCreate) {
    const { data } = await apiClient.post<FacturaAgencia>(`${BASE}/agencias`, payload);
    return data;
  },
  async cambiarEstatus(id: string, estatus: EstatusProveedor) {
    const { data } = await apiClient.post<FacturaAgencia>(`${BASE}/agencias/${id}/estatus`, {
      estatus,
    });
    return data;
  },
  async autorizar(id: string) {
    const { data } = await apiClient.post<FacturaAgencia>(`${BASE}/agencias/${id}/autorizar`);
    return data;
  },
};

// ── CostoAdicional ────────────────────────────────────────────────────────────
export interface FiltrosCosto extends ListParams {
  tipo_costo?: string;
  periodo_contable?: string;
}

export const costoApi = {
  async list(params?: FiltrosCosto) {
    const { data } = await apiClient.get<Page<CostoAdicional>>(`${BASE}/costos`, { params });
    return data;
  },
  async create(payload: CostoAdicionalCreate) {
    const { data } = await apiClient.post<CostoAdicional>(`${BASE}/costos`, payload);
    return data;
  },
};

// ── Apoyo para los combos (leen de F1 y F0 por la API, sin importar sus módulos) ──
/** Órdenes que se pueden facturar: solo las `orden_cerrada` (precondición del backend). */
export async function ordenesFacturables(): Promise<OrdenFacturable[]> {
  const { data } = await apiClient.get<Page<OrdenFacturable>>("/ordenes/clientes", {
    params: { estatus_orden: "orden_cerrada", size: 100 },
  });
  return data.items;
}

export async function cuentasContables(): Promise<OpcionCatalogo[]> {
  const { data } = await apiClient.get<Page<{ cuenta_contable_id: string; codigo_cuenta: string; nombre_cuenta: string }>>(
    "/catalogos/cuentas-contables",
    { params: { activo: true, size: 100 } },
  );
  return data.items.map((c) => ({
    id: c.cuenta_contable_id,
    etiqueta: `${c.codigo_cuenta} · ${c.nombre_cuenta}`,
  }));
}

/** Claves de método de pago sugeridas desde `ConstantesSistema` (no hay FK — ver ADR de F2). */
export async function metodosDePago(): Promise<OpcionCatalogo[]> {
  const { data } = await apiClient.get<Page<{ clave: string; descripcion: string }>>(
    "/catalogos/constantes",
    { params: { grupo: "MetodoPago", activo: true, size: 100 } },
  );
  return data.items.map((c) => ({ id: c.clave, etiqueta: `${c.clave} · ${c.descripcion}` }));
}

export async function afiliadosActivos(): Promise<OpcionCatalogo[]> {
  const { data } = await apiClient.get<Page<{ afiliado_id: string; nombre_afiliado: string }>>(
    "/catalogos/afiliados",
    { params: { activo: true, size: 100 } },
  );
  return data.items.map((a) => ({ id: a.afiliado_id, etiqueta: a.nombre_afiliado }));
}

export async function agenciasActivas(): Promise<OpcionCatalogo[]> {
  const { data } = await apiClient.get<Page<{ agencia_id: string; nombre_agencia: string }>>(
    "/catalogos/agencias",
    { params: { activo: true, size: 100 } },
  );
  return data.items.map((a) => ({ id: a.agencia_id, etiqueta: a.nombre_agencia }));
}
