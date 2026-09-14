/** Hooks de F3 (TanStack Query).
 *
 * No se usa `useCatalog`: ninguna entidad de este módulo es un CRUD de catálogo con baja
 * lógica (mismo criterio que F2). Toda mutación invalida la lista de su propia entidad;
 * `crear`/`eliminar` de `PagoCliente` invalidan ADEMÁS `CobranzaFactura` (el backend
 * recalcula `estatus_cobro`/`fecha_cobro` del padre en la misma transacción — y si el pago
 * completa el total, la cascada del handoff llega hasta `OrdenCliente`, así que también se
 * invalidan las claves de F1/F2).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  afiliadosInfo,
  agenciasInfo,
  anunciantesInfo,
  cobranzaFacturaApi,
  facturaClienteResumen,
  facturasAfiliadoPagables,
  facturasAgenciaPagables,
  historialPagosCliente,
  metodosDePago,
  movimientoBancarioApi,
  ordenesInfo,
  pagoClienteApi,
  requisicionApi,
  vendedoresInfo,
  type FiltrosCobranzaFactura,
  type FiltrosMovimientoBancario,
  type FiltrosRequisicion,
} from "./api";
import type {
  CobranzaFacturaUpdate,
  EstatusRequisicion,
  MovimientoBancarioCreate,
  PagoClienteCreate,
  RequisicionCreate,
  RequisicionUpdate,
} from "./types";

const K_COBRANZA = "cobranza:facturas";
const K_PAGOS = "cobranza:pagos";
const K_REQUISICIONES = "cobranza:requisiciones";
const K_MOVIMIENTOS = "cobranza:movimientos";
/** Claves de otras fases, invalidadas cuando el handoff las toca (ver docstring). */
const K_FACTURACION_CLIENTES = "facturacion:clientes";
const K_ORDENES = "ordenes";

// ── CobranzaFactura ───────────────────────────────────────────────────────────
export function useCobranzaFacturas(filtros: FiltrosCobranzaFactura) {
  const qc = useQueryClient();

  const list = useQuery({
    queryKey: [K_COBRANZA, "list", filtros],
    queryFn: () => cobranzaFacturaApi.list(filtros),
  });

  const actualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: CobranzaFacturaUpdate }) =>
      cobranzaFacturaApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: [K_COBRANZA] }),
  });

  return { list, actualizar };
}

export function useCobranzaFactura(id: string | null) {
  return useQuery({
    queryKey: [K_COBRANZA, "get", id],
    queryFn: () => cobranzaFacturaApi.get(id as string),
    enabled: id != null,
  });
}

/** Resuelve el `cobranza_id` a partir del `factura_id` de F2 — lo usa el deep-link
 *  "Pasa a CxC (Fase 3)" de `FacturasClientePage`, que solo conoce la factura, no la
 *  cobranza que el handoff creó para ella. */
export function useCobranzaFacturaPorFacturaId(facturaId: string | null) {
  return useQuery({
    queryKey: [K_COBRANZA, "por-factura", facturaId],
    queryFn: () => cobranzaFacturaApi.list({ factura_id: facturaId as string, page: 1, size: 1 }),
    enabled: facturaId != null,
  });
}

// ── PagoCliente ───────────────────────────────────────────────────────────────
export function usePagosCliente(cobranzaId: string | null) {
  const qc = useQueryClient();
  const invalidarTodo = () => {
    qc.invalidateQueries({ queryKey: [K_PAGOS] });
    qc.invalidateQueries({ queryKey: [K_COBRANZA] });
    // La cascada del handoff (ADR-072) puede llegar hasta FacturaCliente/OrdenCliente
    // cuando el pago completa el total — se invalidan también, igual que `timbrar` en F2.
    qc.invalidateQueries({ queryKey: [K_FACTURACION_CLIENTES] });
    qc.invalidateQueries({ queryKey: [K_ORDENES] });
  };

  const list = useQuery({
    queryKey: [K_PAGOS, "list", cobranzaId],
    queryFn: () => pagoClienteApi.list(cobranzaId as string, { size: 100 }),
    enabled: cobranzaId != null,
  });

  const crear = useMutation({
    mutationFn: (data: PagoClienteCreate) => pagoClienteApi.crear(cobranzaId as string, data),
    onSuccess: invalidarTodo,
  });

  const eliminar = useMutation({
    mutationFn: (pagoId: string) => pagoClienteApi.eliminar(pagoId),
    onSuccess: invalidarTodo,
  });

  return { list, crear, eliminar };
}

/** Historial completo de pagos (vista "Pagos recibidos" del mockup), agregado por el
 *  front ante la ausencia de un endpoint "todos los pagos" (ver `historialPagosCliente`
 *  en `api.ts`). Sin paginar en el backend: el filtrado/orden se hace en el cliente sobre
 *  el arreglo ya combinado. */
export function useHistorialPagosCliente() {
  return useQuery({
    queryKey: [K_PAGOS, "historial"],
    queryFn: historialPagosCliente,
  });
}

// ── Combos ────────────────────────────────────────────────────────────────────
export const useAnunciantesInfo = () =>
  useQuery({ queryKey: ["cobranza:anunciantes"], queryFn: anunciantesInfo });

export const useMetodosDePago = () =>
  useQuery({ queryKey: ["cobranza:metodos-pago"], queryFn: metodosDePago });

export const useAfiliadosInfo = () =>
  useQuery({ queryKey: ["cobranza:afiliados"], queryFn: afiliadosInfo });

export const useAgenciasInfo = () =>
  useQuery({ queryKey: ["cobranza:agencias"], queryFn: agenciasInfo });

export const useVendedoresInfo = () =>
  useQuery({ queryKey: ["cobranza:vendedores"], queryFn: vendedoresInfo });

export const useFacturasAfiliadoPagables = () =>
  useQuery({ queryKey: ["cobranza:facturas-afiliado-pagables"], queryFn: facturasAfiliadoPagables });

export const useFacturasAgenciaPagables = () =>
  useQuery({ queryKey: ["cobranza:facturas-agencia-pagables"], queryFn: facturasAgenciaPagables });

export const useOrdenesInfo = () =>
  useQuery({ queryKey: ["cobranza:ordenes"], queryFn: ordenesInfo });

export const useFacturaClienteResumen = (facturaId: string | null | undefined) =>
  useQuery({
    queryKey: ["cobranza:factura-resumen", facturaId],
    queryFn: () => facturaClienteResumen(facturaId as string),
    enabled: !!facturaId,
  });

// ── Requisicion ───────────────────────────────────────────────────────────────
export function useRequisiciones(filtros: FiltrosRequisicion) {
  const qc = useQueryClient();
  const invalidar = () => qc.invalidateQueries({ queryKey: [K_REQUISICIONES] });

  const list = useQuery({
    queryKey: [K_REQUISICIONES, "list", filtros],
    queryFn: () => requisicionApi.list(filtros),
  });

  const crear = useMutation({
    mutationFn: (data: RequisicionCreate) => requisicionApi.create(data),
    onSuccess: invalidar,
  });

  const actualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RequisicionUpdate }) =>
      requisicionApi.update(id, data),
    onSuccess: invalidar,
  });

  const cambiarEstatus = useMutation({
    mutationFn: ({
      id,
      estatus,
      fecha_pago_requisicion,
    }: {
      id: string;
      estatus: EstatusRequisicion;
      fecha_pago_requisicion?: string | null;
    }) => requisicionApi.cambiarEstatus(id, estatus, fecha_pago_requisicion),
    onSuccess: invalidar,
  });

  const autorizar = useMutation({
    mutationFn: (id: string) => requisicionApi.autorizar(id),
    onSuccess: invalidar,
  });

  return { list, crear, actualizar, cambiarEstatus, autorizar };
}

// ── MovimientoBancario ────────────────────────────────────────────────────────
export function useMovimientosBancarios(filtros: FiltrosMovimientoBancario) {
  const qc = useQueryClient();
  const invalidar = () => qc.invalidateQueries({ queryKey: [K_MOVIMIENTOS] });

  const list = useQuery({
    queryKey: [K_MOVIMIENTOS, "list", filtros],
    queryFn: () => movimientoBancarioApi.list(filtros),
  });

  const crear = useMutation({
    mutationFn: (data: MovimientoBancarioCreate) => movimientoBancarioApi.crear(data),
    onSuccess: invalidar,
  });

  const conciliar = useMutation({
    mutationFn: (id: string) => movimientoBancarioApi.conciliar(id),
    onSuccess: invalidar,
  });

  return { list, crear, conciliar };
}

// ── Contadores del sidebar ────────────────────────────────────────────────────
/** Totales por sección — mismo criterio que `useConteosFacturacion` de F2: pide
 *  `size: 1` (solo interesa `.total`) y `retry: false` (si el área no tiene permiso sobre
 *  una sección, esa consulta 403 y el contador queda en 0, sin romper el menú). */
export function useConteosCobranza(): Record<string, number> {
  const soloTotal = { page: 1, size: 1 };
  const cobranza = useQuery({
    queryKey: [K_COBRANZA, "list", soloTotal],
    queryFn: () => cobranzaFacturaApi.list(soloTotal),
    retry: false,
  });
  const vencidas = useQuery({
    queryKey: [K_COBRANZA, "list", { ...soloTotal, estatus_cobro: "vencida" }],
    // "vencida" no es un valor de `estatus_cobro` en el backend (es un badge): se cuenta
    // trayendo pendientes+parciales y filtrando aquí. Ver `CobranzaFacturasPage`.
    queryFn: () => cobranzaFacturaApi.list({ page: 1, size: 100 }),
    retry: false,
  });
  const requisiciones = useQuery({
    queryKey: [K_REQUISICIONES, "list", soloTotal],
    queryFn: () => requisicionApi.list(soloTotal),
    retry: false,
  });
  const porAutorizar = useQuery({
    queryKey: [K_REQUISICIONES, "list", { ...soloTotal, estatus_requisicion: "pendiente" }],
    queryFn: () => requisicionApi.list({ page: 1, size: 1, estatus_requisicion: "pendiente" }),
    retry: false,
  });
  const porPagar = useQuery({
    queryKey: [K_REQUISICIONES, "list", { ...soloTotal, estatus_requisicion: "autorizada" }],
    queryFn: () => requisicionApi.list({ page: 1, size: 1, estatus_requisicion: "autorizada" }),
    retry: false,
  });
  const movimientos = useQuery({
    queryKey: [K_MOVIMIENTOS, "list", soloTotal],
    queryFn: () => movimientoBancarioApi.list(soloTotal),
    retry: false,
  });
  const sinConciliar = useQuery({
    queryKey: [K_MOVIMIENTOS, "list", { ...soloTotal, conciliado: false }],
    queryFn: () => movimientoBancarioApi.list({ page: 1, size: 1, conciliado: false }),
    retry: false,
  });
  // Sin un `size:1` posible aquí: no hay un `GET` de "todos los pagos" que devuelva un
  // `total` (mismo hueco que `historialPagosCliente` resuelve para la propia pantalla) —
  // comparte la MISMA query key que `useHistorialPagosCliente`, así que entrar a "Pagos
  // recibidos" no dispara una segunda consulta, solo reusa esta.
  const pagos = useQuery({
    queryKey: [K_PAGOS, "historial"],
    queryFn: historialPagosCliente,
    retry: false,
  });

  return {
    cobranza_factura: cobranza.data?.total ?? 0,
    cobranzas_vencidas: (vencidas.data?.items ?? []).filter(
      (c) => c.vencida && c.estatus_cobro !== "cobrada",
    ).length,
    pago_cliente: pagos.data?.length ?? 0,
    requisicion: requisiciones.data?.total ?? 0,
    por_autorizar: porAutorizar.data?.total ?? 0,
    por_pagar: porPagar.data?.total ?? 0,
    movimiento_bancario: movimientos.data?.total ?? 0,
    sin_conciliar: sinConciliar.data?.total ?? 0,
  };
}
