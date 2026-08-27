/** Hooks de F2 (TanStack Query).
 *
 * No se usa `useCatalog`: ese helper asume el CRUD de catálogo con baja lógica
 * (`setEstado`), que ninguna entidad de F2 tiene. Las transiciones de estado son
 * mutaciones propias, cada una con su endpoint.
 *
 * Toda mutación invalida la lista de su entidad. `timbrar` invalida ADEMÁS las órdenes:
 * el backend promueve la `OrdenCliente` a `facturada` en la misma transacción (el handoff
 * de F2), así que la pantalla de Órdenes queda obsoleta si no se refresca.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  afiliadosActivos,
  agenciasActivas,
  costoApi,
  cuentasContables,
  facturaAfiliadoApi,
  facturaAgenciaApi,
  facturaClienteApi,
  metodosDePago,
  ordenesFacturables,
  ordenesPorFacturar,
  type FiltrosCosto,
  type FiltrosFacturaAfiliado,
  type FiltrosFacturaAgencia,
  type FiltrosFacturaCliente,
} from "./api";
import type {
  CostoAdicionalCreate,
  EstatusProveedor,
  FacturaAfiliadoCreate,
  FacturaAgenciaCreate,
  FacturaClienteCreate,
  TimbrarInput,
} from "./types";

const K_CLIENTES = "facturacion:clientes";
const K_AFILIADOS = "facturacion:afiliados";
const K_AGENCIAS = "facturacion:agencias";
const K_COSTOS = "facturacion:costos";
/** Clave de las órdenes (F1). Se invalida tras timbrar — ver docstring del módulo. */
const K_ORDENES = "ordenes";

// ── FacturaCliente ────────────────────────────────────────────────────────────
export function useFacturasCliente(filtros: FiltrosFacturaCliente) {
  const qc = useQueryClient();
  const invalidar = () => qc.invalidateQueries({ queryKey: [K_CLIENTES] });
  const invalidarTodo = () => {
    invalidar();
    qc.invalidateQueries({ queryKey: [K_ORDENES] });
  };

  const list = useQuery({
    queryKey: [K_CLIENTES, "list", filtros],
    queryFn: () => facturaClienteApi.list(filtros),
  });

  const crear = useMutation({
    mutationFn: (data: FacturaClienteCreate) => facturaClienteApi.create(data),
    onSuccess: invalidar,
  });

  const enviarATimbrado = useMutation({
    mutationFn: (id: string) => facturaClienteApi.enviarATimbrado(id),
    onSuccess: invalidar,
  });

  const timbrar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: TimbrarInput }) =>
      facturaClienteApi.timbrar(id, data),
    onSuccess: invalidarTodo, // el handoff cambió también la OrdenCliente
  });

  const entregar = useMutation({
    mutationFn: ({ id, fecha }: { id: string; fecha?: string | null }) =>
      facturaClienteApi.entregar(id, fecha),
    onSuccess: invalidar,
  });

  const cancelar = useMutation({
    mutationFn: (id: string) => facturaClienteApi.cancelar(id),
    // Espejo de `timbrar`: la cancelación puede devolver la OrdenCliente a
    // `orden_cerrada` (ADR-047), así que quedan obsoletas la pantalla de F1 y la bandeja
    // "Listas para facturar", donde esa orden vuelve a aparecer.
    onSuccess: () => {
      invalidarTodo();
      qc.invalidateQueries({ queryKey: [K_POR_FACTURAR] });
    },
  });

  return { list, crear, enviarATimbrado, timbrar, entregar, cancelar };
}

// ── FacturaAfiliado ───────────────────────────────────────────────────────────
export function useFacturasAfiliado(filtros: FiltrosFacturaAfiliado) {
  const qc = useQueryClient();
  const invalidar = () => qc.invalidateQueries({ queryKey: [K_AFILIADOS] });

  const list = useQuery({
    queryKey: [K_AFILIADOS, "list", filtros],
    queryFn: () => facturaAfiliadoApi.list(filtros),
  });

  const crear = useMutation({
    mutationFn: (data: FacturaAfiliadoCreate) => facturaAfiliadoApi.create(data),
    onSuccess: invalidar,
  });

  const cambiarEstatus = useMutation({
    mutationFn: ({ id, estatus }: { id: string; estatus: EstatusProveedor }) =>
      facturaAfiliadoApi.cambiarEstatus(id, estatus),
    onSuccess: invalidar,
  });

  const autorizar = useMutation({
    mutationFn: (id: string) => facturaAfiliadoApi.autorizar(id),
    onSuccess: invalidar,
  });

  return { list, crear, cambiarEstatus, autorizar };
}

export function useAsignacionesAfiliado(facturaId: string | null) {
  return useQuery({
    queryKey: [K_AFILIADOS, "ordenes", facturaId],
    queryFn: () => facturaAfiliadoApi.asignaciones(facturaId as string),
    enabled: facturaId != null,
  });
}

// ── FacturaAgencia ────────────────────────────────────────────────────────────
export function useFacturasAgencia(filtros: FiltrosFacturaAgencia) {
  const qc = useQueryClient();
  const invalidar = () => qc.invalidateQueries({ queryKey: [K_AGENCIAS] });

  const list = useQuery({
    queryKey: [K_AGENCIAS, "list", filtros],
    queryFn: () => facturaAgenciaApi.list(filtros),
  });

  const crear = useMutation({
    mutationFn: (data: FacturaAgenciaCreate) => facturaAgenciaApi.create(data),
    onSuccess: invalidar,
  });

  const cambiarEstatus = useMutation({
    mutationFn: ({ id, estatus }: { id: string; estatus: EstatusProveedor }) =>
      facturaAgenciaApi.cambiarEstatus(id, estatus),
    onSuccess: invalidar,
  });

  const autorizar = useMutation({
    mutationFn: (id: string) => facturaAgenciaApi.autorizar(id),
    onSuccess: invalidar,
  });

  return { list, crear, cambiarEstatus, autorizar };
}

// ── CostoAdicional ────────────────────────────────────────────────────────────
export function useCostos(filtros: FiltrosCosto) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: [K_COSTOS, "list", filtros],
    queryFn: () => costoApi.list(filtros),
  });
  const crear = useMutation({
    mutationFn: (data: CostoAdicionalCreate) => costoApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [K_COSTOS] }),
  });
  return { list, crear };
}

// ── Bandeja "Listas para facturar" ────────────────────────────────────────────
/** Se invalida sola cuando se crea una factura: `crear` invalida la clave del módulo de
 *  clientes, y esta bandeja usa su propia clave, así que se invalida explícitamente
 *  desde la pantalla que crea (ver `ListasParaFacturarPage`). */
export const K_POR_FACTURAR = "facturacion:por-facturar";

export function useOrdenesPorFacturar(params: { page?: number; size?: number; q?: string }) {
  return useQuery({
    queryKey: [K_POR_FACTURAR, "list", params],
    queryFn: () => ordenesPorFacturar(params),
  });
}

// ── Contadores del sidebar ────────────────────────────────────────────────────
/** Totales por sección, para los contadores del menú.
 *
 * Pide `size: 1` a propósito: lo único que se usa es el `total` de la respuesta, así que
 * no tiene sentido traerse 20 filas que nadie va a pintar.
 *
 * Las claves comparten PREFIJO con las de cada lista, de modo que cualquier mutación del
 * módulo —crear, timbrar, cancelar— ya las invalida y el contador baja o sube solo, sin
 * lógica extra.
 *
 * Si el área del usuario no tiene permiso sobre una sección, esa consulta falla con 403 y
 * su contador queda en 0: es un indicador, no una pantalla, y no vale la pena romper el
 * menú por eso.
 */
export function useConteosFacturacion(): Record<string, number> {
  const soloTotal = { page: 1, size: 1 };
  const clientes = useQuery({
    queryKey: [K_CLIENTES, "list", soloTotal],
    queryFn: () => facturaClienteApi.list(soloTotal),
    retry: false,
  });
  const afiliados = useQuery({
    queryKey: [K_AFILIADOS, "list", soloTotal],
    queryFn: () => facturaAfiliadoApi.list(soloTotal),
    retry: false,
  });
  const agencias = useQuery({
    queryKey: [K_AGENCIAS, "list", soloTotal],
    queryFn: () => facturaAgenciaApi.list(soloTotal),
    retry: false,
  });
  const costos = useQuery({
    queryKey: [K_COSTOS, "list", soloTotal],
    queryFn: () => costoApi.list(soloTotal),
    retry: false,
  });
  const porFacturar = useQuery({
    queryKey: [K_POR_FACTURAR, "list", soloTotal],
    queryFn: () => ordenesPorFacturar(soloTotal),
    retry: false,
  });

  return {
    facturas_cliente: clientes.data?.total ?? 0,
    listas_para_facturar: porFacturar.data?.total ?? 0,
    facturas_afiliado: afiliados.data?.total ?? 0,
    facturas_agencia: agencias.data?.total ?? 0,
    costos_adicionales: costos.data?.total ?? 0,
  };
}

// ── Combos ────────────────────────────────────────────────────────────────────
export const useOrdenesFacturables = () =>
  useQuery({ queryKey: ["facturacion:ordenes-facturables"], queryFn: ordenesFacturables });

export const useCuentasContables = () =>
  useQuery({ queryKey: ["facturacion:cuentas"], queryFn: cuentasContables });

export const useMetodosDePago = () =>
  useQuery({ queryKey: ["facturacion:metodos-pago"], queryFn: metodosDePago });

export const useAfiliados = () =>
  useQuery({ queryKey: ["facturacion:afiliados-catalogo"], queryFn: afiliadosActivos });

export const useAgencias = () =>
  useQuery({ queryKey: ["facturacion:agencias-catalogo"], queryFn: agenciasActivas });
