/** ADR-285 (petición del usuario, con captura): hooks de TanStack Query para las
 * pantallas de lista de Órdenes — antes TODO el módulo vivía exclusivamente de
 * `OrdenesContext` (un `useReducer` poblado de una sola vez, con el 100% de las filas,
 * ver `cargarEstadoReal.ts`). Estos hooks piden SOLO lo que hace falta: una página real
 * al backend para las tablas, conteos ligeros (`page:1,size:1` + `total`, mismo patrón
 * que `useConteosFacturacion`) para las bandejas del sidebar, y los datos completos de
 * UNA fila (días/verificaciones/historial) solo cuando esa fila se selecciona.
 *
 * El resto del módulo (Verificaciones en su forma vieja, Incidencias, los formularios de
 * alta/edición) sigue usando `OrdenesContext` sin cambios — conviven ambos mecanismos
 * mientras se termina de migrar pantalla por pantalla.
 */

import { useQuery } from "@tanstack/react-query";

import { incidenciaFromApi, ordenClienteFromApi, ordenEstacionFromApi } from "./adapters/fromApi";
import { listarIncidenciasDeOEApi } from "./adapters/escrituraApi";
import { refrescarOrdenCliente, refrescarOrdenEstacion } from "./adapters/refrescar";
import {
  listarDiasOrdenEstacionApi,
  listarHistorialComisionesApi,
  listarVerificacionesApi,
  oesDeLaOCApi,
  paginaIncidenciasApi,
  paginaOrdenesClienteApi,
  paginaOrdenesEstacionApi,
  type FiltrosOrdenCliente,
  type FiltrosOrdenEstacion,
} from "./adapters/ordenesApi";
import type { Incidencia, OrdenCliente, OrdenEstacion } from "./types";

const K_OC = "ordenes:clientes";
const K_OE = "ordenes:estaciones";

export interface PaginaOC {
  items: OrdenCliente[];
  total: number;
}

export interface PaginaOE {
  items: OrdenEstacion[];
  total: number;
}

/** Tabla de "Órdenes de Servicio": una página real, con los nombres/folios ya
 *  resueltos. `oe_count` ya viene calculado del backend — no hace falta `oesDeOC`
 *  sobre un arreglo completo. */
export function useOrdenesClientePagina(filtros: FiltrosOrdenCliente) {
  return useQuery<PaginaOC>({
    queryKey: [K_OC, "pagina", filtros],
    queryFn: async () => {
      const pagina = await paginaOrdenesClienteApi(filtros);
      return { items: pagina.items.map(ordenClienteFromApi), total: pagina.total };
    },
  });
}

/** LA orden seleccionada, independiente de en qué página de la tabla esté — evita
 *  depender de `items.find()` (la fila seleccionada puede no estar en la página
 *  actual, p.ej. al llegar con una OC preseleccionada desde otra pantalla). */
/** LA OE seleccionada, con días Y verificaciones completos — independiente de en qué
 *  página de la tabla esté (mismo criterio que `useOrdenClienteSeleccionada`). Usada por
 *  el detalle, edición, "Capturar reales" y "Clonar", que necesitan el objeto completo,
 *  no solo lo que trae la fila de la página actual. */
export function useOrdenEstacionSeleccionada(oeId: string | null | undefined) {
  return useQuery<OrdenEstacion>({
    queryKey: [K_OE, "detalle-completo", oeId],
    queryFn: () => refrescarOrdenEstacion(oeId as string),
    enabled: !!oeId,
  });
}

export function useOrdenClienteSeleccionada(ordenId: string | null | undefined) {
  return useQuery<OrdenCliente>({
    queryKey: [K_OC, "detalle", ordenId],
    queryFn: () => refrescarOrdenCliente(ordenId as string),
    enabled: !!ordenId,
  });
}

/** Las OE de UNA orden (días incluidos, sin verificaciones — el detalle de "Órdenes de
 *  Servicio" solo necesita el balance de spots ASIGNADOS, nunca lo "real"). Acotado por
 *  `orden_id`, nunca el arreglo completo del sistema. */
export function useOesDeLaOC(ordenId: string | null | undefined) {
  return useQuery<OrdenEstacion[]>({
    queryKey: [K_OE, "de-oc", ordenId],
    queryFn: async () => {
      const dtos = await oesDeLaOCApi(ordenId as string);
      const dias = await Promise.all(dtos.map((d) => listarDiasOrdenEstacionApi(d.orden_estacion_id)));
      return dtos.map((dto, i) => ordenEstacionFromApi(dto, dias[i], []));
    },
    enabled: !!ordenId,
  });
}

/** Incidencias de las OE de una orden (detalle de "Órdenes de Servicio") — se piden
 *  por cada OE hija (típicamente pocas, 1-5) en vez de traer TODAS las incidencias del
 *  sistema y filtrar en memoria. */
export function useIncidenciasDeLaOC(oes: OrdenEstacion[] | undefined) {
  const ids = (oes ?? []).map((oe) => oe.id);
  return useQuery<Incidencia[]>({
    queryKey: [K_OE, "incidencias-de-oc", ids],
    queryFn: async () => {
      const lotes = await Promise.all(ids.map((id) => listarIncidenciasDeOEApi(id)));
      return lotes.flat().map(incidenciaFromApi);
    },
    enabled: ids.length > 0,
  });
}

export function useHistorialComisionesOC(ordenId: string | null | undefined) {
  return useQuery({
    queryKey: [K_OC, "historial-comisiones", ordenId],
    queryFn: () => listarHistorialComisionesApi(ordenId as string),
    enabled: !!ordenId,
  });
}

/** Tabla de "Órdenes de Transmisión": una página real. A diferencia de la de Órdenes de
 *  Servicio, aquí SÍ hace falta `dias` por fila (la tabla muestra período/spots/importe
 *  de cada estación) — se pide en paralelo, acotado a la página actual (~20 filas), no
 *  al arreglo completo del sistema (el problema original reportado). */
export function useOrdenesEstacionPagina(filtros: FiltrosOrdenEstacion) {
  return useQuery<PaginaOE>({
    queryKey: [K_OE, "pagina", filtros],
    queryFn: async () => {
      const pagina = await paginaOrdenesEstacionApi(filtros);
      const dias = await Promise.all(
        pagina.items.map((dto) => listarDiasOrdenEstacionApi(dto.orden_estacion_id)),
      );
      return {
        items: pagina.items.map((dto, i) => ordenEstacionFromApi(dto, dias[i], [])),
        total: pagina.total,
      };
    },
  });
}

/** Días + verificaciones de UNA OE (panel de detalle de "Órdenes de Transmisión" y de
 *  "Verificaciones") — mismo dato que ya arma `refrescarOrdenEstacion`, pero como query
 *  cacheable en vez de una promesa suelta. */
export function useDetalleOE(oeId: string | null | undefined) {
  return useQuery<{ dias: Awaited<ReturnType<typeof listarDiasOrdenEstacionApi>>; verificaciones: Awaited<ReturnType<typeof listarVerificacionesApi>> }>({
    queryKey: [K_OE, "detalle", oeId],
    queryFn: async () => {
      const [dias, verificaciones] = await Promise.all([
        listarDiasOrdenEstacionApi(oeId as string),
        listarVerificacionesApi(oeId as string),
      ]);
      return { dias, verificaciones };
    },
    enabled: !!oeId,
  });
}

/** Tabla de "Verificaciones": igual que `useOrdenesEstacionPagina`, pero TAMBIÉN pide
 *  verificaciones por fila (día a día programado vs. real, no solo `dias`) — más caro
 *  que la tabla de "Órdenes de Transmisión", pero acotado a la página actual (~20 filas),
 *  nunca al arreglo completo del sistema (el problema original reportado). Siempre fuerza
 *  `estatus: "cerrada"` (2.3) — Verificaciones nunca muestra otra cosa. Reutiliza
 *  `verificacionDerivada()`/`diaVerificacion()` sin cambios: a esos selectores no les
 *  importa de dónde vino el dato, siempre que la OE traiga `periodo_transmision` +
 *  `horarios_reales` completos. Orden intra-página por `updated_at` (cuándo la OI llegó a
 *  2.3), no por `created_at` (el que da el backend) — mismo criterio que ya probaba
 *  `VerificacionListPage.test.tsx` antes de ADR-285; se reordena aquí, sobre la página ya
 *  traída, no sobre el arreglo completo. */
export function useVerificacionesPagina(filtros: FiltrosOrdenEstacion) {
  return useQuery<PaginaOE>({
    queryKey: [K_OE, "pagina-verificaciones", filtros],
    queryFn: async () => {
      const pagina = await paginaOrdenesEstacionApi({ ...filtros, estatus: "cerrada" });
      const [dias, verificaciones] = await Promise.all([
        Promise.all(pagina.items.map((dto) => listarDiasOrdenEstacionApi(dto.orden_estacion_id))),
        Promise.all(pagina.items.map((dto) => listarVerificacionesApi(dto.orden_estacion_id))),
      ]);
      const items = pagina.items
        .map((dto, i) => ordenEstacionFromApi(dto, dias[i], verificaciones[i]))
        .sort((a, b) => (b.updated_at ?? b.created_at).localeCompare(a.updated_at ?? a.created_at));
      return { items, total: pagina.total };
    },
  });
}

// ── Conteos del sidebar ──────────────────────────────────────────────────────
/** Totales por bandeja, para los contadores del menú — mismo criterio que
 *  `useConteosFacturacion`: `size: 1`, lo único que importa es `total`. */
export function useConteosOrdenes() {
  const soloTotal = { page: 1, size: 1 };
  const ordenesCliente = useQuery({
    queryKey: [K_OC, "pagina", soloTotal],
    queryFn: () => paginaOrdenesClienteApi(soloTotal),
    retry: false,
  });
  const ordenesEstacion = useQuery({
    queryKey: [K_OE, "pagina", soloTotal],
    queryFn: () => paginaOrdenesEstacionApi(soloTotal),
    retry: false,
  });
  const verificaciones = useQuery({
    queryKey: [K_OE, "pagina", { ...soloTotal, estatus: "cerrada" }],
    queryFn: () => paginaOrdenesEstacionApi({ ...soloTotal, estatus: "cerrada" }),
    retry: false,
  });
  // `borrador`/`cancelada` (pendientesAsignar) y `en_revision` (pendientesVerificar)
  // son valores defensivos que los datos reales nunca usan (mismo criterio ya
  // documentado en `vocabulario.ts`: "los datos sembrados nunca usan estos valores") —
  // se cuenta solo el valor que sí ocurre en la práctica, para no multiplicar
  // consultas por casos que no existen hoy.
  const pendientesAsignar = useQuery({
    queryKey: [K_OE, "pagina", { ...soloTotal, estatus: "asignada" }],
    queryFn: () => paginaOrdenesEstacionApi({ ...soloTotal, estatus: "asignada" }),
    retry: false,
  });
  const pendientesVerificar = useQuery({
    queryKey: [K_OE, "pagina", { ...soloTotal, estatus: "en_transmision" }],
    queryFn: () => paginaOrdenesEstacionApi({ ...soloTotal, estatus: "en_transmision" }),
    retry: false,
  });
  const listasCerrar = useQuery({
    queryKey: [K_OC, "pagina", { ...soloTotal, listas_para_cerrar: true }],
    queryFn: () => paginaOrdenesClienteApi({ ...soloTotal, listas_para_cerrar: true }),
    retry: false,
  });
  const listasFacturar = useQuery({
    queryKey: [K_OC, "pagina", { ...soloTotal, estatus_orden: "orden_cerrada" }],
    queryFn: () => paginaOrdenesClienteApi({ ...soloTotal, estatus_orden: "orden_cerrada" }),
    retry: false,
  });
  const incidencias = useQuery({
    queryKey: ["ordenes:incidencias", "pagina", soloTotal],
    queryFn: () => paginaIncidenciasApi(soloTotal),
    retry: false,
  });

  return {
    ordenesCliente: ordenesCliente.data?.total ?? 0,
    ordenesEstacion: ordenesEstacion.data?.total ?? 0,
    verificaciones: verificaciones.data?.total ?? 0,
    incidencias: incidencias.data?.total ?? 0,
    pendientesAsignar: pendientesAsignar.data?.total ?? 0,
    pendientesVerificar: pendientesVerificar.data?.total ?? 0,
    listasCerrar: listasCerrar.data?.total ?? 0,
    listasFacturar: listasFacturar.data?.total ?? 0,
  };
}
