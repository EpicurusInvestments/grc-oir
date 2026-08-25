/** Selectores puros sobre el estado de `OrdenesContext`: contadores de sidebar, listas
 * filtradas y valores derivados (balance de spots, textos de periodo). Nada aquí muta
 * estado ni toca el DOM — son funciones de `state -> valor`, memoizables con `useMemo` en
 * cada pantalla.
 */

import { IVA_RATE } from "../constants";
import { findAnunciante } from "./catalogosCache";
import type { Incidencia, OrdenCliente, OrdenEstacion, PeriodoTransmisionRow, VerificacionDerivada, VerificacionDiaRow } from "../types";

export interface TotalesOC {
  subtotal: number;
  iva: number;
  total: number;
}

/** subtotal = total_spots × precio_unitario; iva = subtotal × IVA_RATE; total = subtotal + iva.
 * SIEMPRE derivado — nunca se persiste ni se captura a mano. */
export function totalesOC(oc: OrdenCliente): TotalesOC {
  const subtotal = (oc.total_spots || 0) * (oc.precio_unitario || 0);
  const iva = subtotal * IVA_RATE;
  return { subtotal, iva, total: subtotal + iva };
}

export function oiTotalSpots(oe: OrdenEstacion): number {
  return oe.periodo_transmision.reduce((s, p) => s + (p.spots_diarios || 0), 0);
}

export function oiImporte(oe: OrdenEstacion): number {
  return oiTotalSpots(oe) * (oe.precio_spot || 0);
}

export function oiPrimeraFecha(oe: OrdenEstacion): string {
  if (!oe.periodo_transmision.length) return "";
  return [...oe.periodo_transmision].map((p) => p.fecha).sort()[0];
}

export function oiUltimaFecha(oe: OrdenEstacion): string {
  if (!oe.periodo_transmision.length) return "";
  return [...oe.periodo_transmision].map((p) => p.fecha).sort().reverse()[0];
}

export function oiVentanaTipica(oe: OrdenEstacion): { inicio: string; termino: string } {
  const p0 = oe.periodo_transmision[0];
  return { inicio: p0?.hora_inicio ?? "", termino: p0?.hora_termino ?? "" };
}

export function oiPeriodoTexto(oe: OrdenEstacion): string {
  if (!oe.periodo_transmision.length) return "—";
  const f0 = oiPrimeraFecha(oe);
  const fN = oiUltimaFecha(oe);
  const n = oe.periodo_transmision.length;
  return f0 === fN ? `${f0} (1 día)` : `${f0} → ${fN} (${n} días)`;
}

export interface BalanceSpotsOC {
  totalOC: number;
  asignados: number;
  porAsignar: number;
  pctAsignado: number;
  sobreAsignado: boolean;
}

/** Balance de spots de una OC contra TODAS sus OrdenEstacion (sin importar sub-estado). */
export function balanceSpotsOC(oc: OrdenCliente, oesDeLaOC: OrdenEstacion[]): BalanceSpotsOC {
  const asignados = oesDeLaOC.reduce((s, oe) => s + oiTotalSpots(oe), 0);
  const totalOC = oc.total_spots || 0;
  const porAsignar = totalOC - asignados;
  const pctAsignado = totalOC > 0 ? Math.min(100, (asignados / totalOC) * 100) : 0;
  return { totalOC, asignados, porAsignar, pctAsignado, sobreAsignado: asignados > totalOC };
}

/** ¿El % capturado se aparta del default del catálogo? (mismo umbral que el prototipo). */
export function esComisionOverride(snap: number | null | undefined, defaultCatalogo: number): boolean {
  return snap != null && Math.abs(snap - defaultCatalogo) > 0.01;
}

export function oesDeOC(ordenesEstacion: OrdenEstacion[], ocId: string): OrdenEstacion[] {
  return ordenesEstacion.filter((oe) => oe.orden_id === ocId);
}

export function todasReconciliadas(oes: OrdenEstacion[]): boolean {
  return oes.length > 0 && oes.every((oe) => oe.estatus === "reales_conciliados");
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Programados/Reales (Tanda 4): "lo programado efectivo" de un día es la fila de
 * `periodo_transmision` SALVO que exista un override en `horarios_programados` para esa
 * fecha — contra ESE valor se compara lo real, no contra lo asignado en crudo.
 * ───────────────────────────────────────────────────────────────────────────── */

export function programadoEfectivo(oe: OrdenEstacion, row: PeriodoTransmisionRow): PeriodoTransmisionRow {
  return oe.horarios_programados?.find((h) => h.fecha === row.fecha) ?? row;
}

/** Total de spots REALES de una OI ya en 2.3 (aplica los overrides de `horarios_reales`
 * sobre el programado efectivo de cada día). Es "lo transmitido" para el cierre de la OC. */
export function totalRealDeOE(oe: OrdenEstacion): number {
  return oe.periodo_transmision.reduce((s, row) => {
    const programado = programadoEfectivo(oe, row);
    const real = oe.horarios_reales?.find((h) => h.fecha === row.fecha) ?? programado;
    return s + (real.spots_diarios || 0);
  }, 0);
}

/** Suma de `monto_ajuste` de las incidencias de un conjunto de OrdenEstacion (para el
 * resumen de cierre: "ajuste neto por incidencias"). */
export function ajusteIncidenciasDeOEs(incidencias: Incidencia[], oes: OrdenEstacion[]): number {
  const ids = new Set(oes.map((oe) => oe.id));
  return incidencias.filter((i) => ids.has(i.orden_interna_id)).reduce((s, i) => s + i.monto_ajuste, 0);
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Verificaciones (Tanda 5): proyección derivada de cada OI que llegó a 2.3 — ver el
 * comentario de `VerificacionDerivada` en types.ts para el porqué no es una entidad
 * persistida/mock. Reutiliza la misma noción de "programado efectivo" que Reales.
 * ───────────────────────────────────────────────────────────────────────────── */

function diaVerificacion(oe: OrdenEstacion, row: PeriodoTransmisionRow): VerificacionDiaRow {
  const programado = programadoEfectivo(oe, row);
  const real = oe.horarios_reales?.find((h) => h.fecha === row.fecha) ?? programado;
  return { fecha: row.fecha, programado, real, diferenciaSpots: real.spots_diarios - programado.spots_diarios };
}

/** Proyecta una OI en 2.3 a su "Verificación" derivada (día a día, programado vs. real). */
export function verificacionDerivada(oe: OrdenEstacion): VerificacionDerivada {
  const dias = oe.periodo_transmision.map((row) => diaVerificacion(oe, row));
  return {
    ordenEstacionId: oe.id,
    folioOrdenInterna: oe.folio_orden_interna,
    fechaInicio: oiPrimeraFecha(oe),
    dias,
    totalProgramado: dias.reduce((s, d) => s + d.programado.spots_diarios, 0),
    totalReal: dias.reduce((s, d) => s + d.real.spots_diarios, 0),
    reconciliada: true,
    actualizadaEn: oe.updated_at ?? oe.created_at,
  };
}

/** Todas las verificaciones derivadas (una por cada OI que llegó a 2.3 — reales conciliados). */
export function verificacionesDerivadas(ordenesEstacion: OrdenEstacion[]): VerificacionDerivada[] {
  return ordenesEstacion.filter((oe) => oe.estatus === "reales_conciliados").map(verificacionDerivada);
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Contadores de sidebar / vistas operativas.
 * ───────────────────────────────────────────────────────────────────────────── */

export interface OrdenesCounts {
  ordenesCliente: number;
  ordenesEstacion: number;
  /** Una "Verificación" (vista derivada) por cada OE que llegó a 2.3. */
  verificaciones: number;
  incidencias: number;
  pendientesAsignar: number;
  pendientesVerificar: number;
  listasCerrar: number;
  listasFacturar: number;
}

export function calcularContadores(
  ordenesCliente: OrdenCliente[],
  ordenesEstacion: OrdenEstacion[],
  totalIncidencias: number,
): OrdenesCounts {
  return {
    ordenesCliente: ordenesCliente.length,
    ordenesEstacion: ordenesEstacion.length,
    verificaciones: ordenesEstacion.filter((oe) => oe.estatus === "reales_conciliados").length,
    incidencias: totalIncidencias,
    pendientesAsignar: ordenesEstacion.filter((oe) => oe.estatus === "asignada_afiliado").length,
    pendientesVerificar: ordenesEstacion.filter((oe) => oe.estatus === "programados_conciliados").length,
    listasCerrar: ordenesCliente.filter((oc) => {
      if (oc.estatus_orden !== "orden_interna") return false;
      return todasReconciliadas(oesDeOC(ordenesEstacion, oc.id));
    }).length,
    listasFacturar: ordenesCliente.filter((oc) => oc.estatus_orden === "orden_cerrada").length,
  };
}

/* ─────────────────────────────────────────────────────────────────────────────
 * Filtro + búsqueda de la lista de Órdenes del cliente.
 * ───────────────────────────────────────────────────────────────────────────── */

export type FiltroOrdenCliente = "todas" | "activas" | "listas_cerrar" | "listas_facturar";

const ESTADOS_INACTIVOS = new Set(["facturada_archivo_plano", "facturada_timbrada", "cobrada", "cancelada"]);

export function filtrarOrdenesCliente(
  ordenesCliente: OrdenCliente[],
  ordenesEstacion: OrdenEstacion[],
  opts: { filtro: FiltroOrdenCliente; search: string },
): OrdenCliente[] {
  const q = opts.search.trim().toLowerCase();
  return ordenesCliente.filter((oc) => {
    if (opts.filtro === "listas_cerrar") {
      if (oc.estatus_orden !== "orden_interna" || !todasReconciliadas(oesDeOC(ordenesEstacion, oc.id))) return false;
    }
    if (opts.filtro === "listas_facturar" && oc.estatus_orden !== "orden_cerrada") return false;
    if (opts.filtro === "activas" && ESTADOS_INACTIVOS.has(oc.estatus_orden)) return false;
    if (q) {
      const anunciante = findAnunciante(oc.anunciante_id);
      const haystack = `${oc.folio_orden} ${oc.numero_orden_cliente} ${anunciante?.nombre_comercial ?? ""}`.toLowerCase();
      return haystack.includes(q);
    }
    return true;
  });
}
