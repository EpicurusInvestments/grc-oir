/** Estado en memoria de F1 — Órdenes, sincronizado con el backend real.
 *
 * Se monta SOLO dentro de `OrdenesExplorerPage` (no en `app/providers.tsx`): F0 no lo
 * necesita. `OrdenesExplorerPage` resuelve `initialState` con un fetch al backend real
 * ANTES de montar este provider (el inicializador de `useReducer` debe ser síncrono).
 *
 * Los 6 métodos de escritura son `async`: llaman al backend real y luego despachan una de
 * las 4 acciones "tontas" (`REEMPLAZAR_OC`/`REEMPLAZAR_OE`/`AGREGAR_INCIDENCIAS`/
 * `REEMPLAZAR_HISTORIAL_OC`) para reflejar en el estado local lo que el backend ya calculó
 * y persistió — el reducer nunca recalcula nada, solo inserta/reemplaza el objeto que ya
 * llegó armado desde `adapters/refrescar.ts`.
 */

import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";

import {
  actualizarComisionesApi,
  actualizarOrdenClienteApi,
  avanzarProgramadosApi,
  avanzarRealesApi,
  cerrarOrdenClienteApi,
  crearOrdenClienteApi,
  crearOrdenEstacionApi,
  darVoboApi,
  listarIncidenciasDeOEApi,
  toggleVoboApi,
} from "../adapters/escrituraApi";
import { incidenciaFromApi } from "../adapters/fromApi";
import { listarHistorialComisionesApi } from "../adapters/ordenesApi";
import { refrescarOrdenCliente, refrescarOrdenEstacion } from "../adapters/refrescar";
import {
  cerrarToApi,
  ordenClienteCreateToApi,
  ordenClienteUpdateToApi,
  ordenEstacionCreateToApi,
  programadosToApi,
  realesToApi,
} from "../adapters/toApi";
import type {
  EstadoOC,
  Incidencia,
  OrdenCliente,
  OrdenClienteInput,
  OrdenEstacion,
  OrdenEstacionInput,
  PeriodoTransmisionRow,
} from "../types";
import type { HistorialCambio } from "@/shared/types";

export type HistorialComision = HistorialCambio & { entidad_id: string };

export interface OrdenesState {
  ordenesCliente: OrdenCliente[];
  ordenesEstacion: OrdenEstacion[];
  incidencias: Incidencia[];
  historialComisiones: HistorialComision[];
}

/** Input de `avanzarAReales`: qué capturó el usuario en el paso D. */
export interface AvanzarARealesInput {
  horariosReales: PeriodoTransmisionRow[];
  testigosUrl: string | null;
  testigosUbicacionAlterna: string | null;
  notasTransmision: string | null;
  reporteRef?: string | null;
}

/** Input de `cerrarOC`: documentos + comisiones efectivas (ya con el auto-fill de defaults
 * del catálogo resuelto por el formulario de cierre). `documentosFaltantes`/`comisiones`
 * se IGNORAN al construir el request real: el backend calcula `cierre_sin_*` de si los
 * refs vienen `null` y rellena cualquier % de comisión que siga vacío con el default del
 * catálogo — ver `adapters/toApi.ts#cerrarToApi`. Se mantienen en el tipo porque
 * `CierreOCForm` los usa para su propio cálculo local antes de enviar. */
export interface CerrarOCInput {
  odcCerradaRef: string | null;
  cartaConciliacionRef: string | null;
  documentosFaltantes: ("odc_cerrada" | "carta_conciliacion")[];
  comisiones: { vp: number | null; vs: number | null; ag: number | null };
}

type Action =
  | { type: "REEMPLAZAR_OC"; oc: OrdenCliente }
  | { type: "REEMPLAZAR_OE"; oe: OrdenEstacion }
  | { type: "AGREGAR_INCIDENCIAS"; incidencias: Incidencia[] }
  | { type: "REEMPLAZAR_HISTORIAL_OC"; ordenId: string; historial: HistorialComision[] };

function reducer(state: OrdenesState, action: Action): OrdenesState {
  switch (action.type) {
    case "REEMPLAZAR_OC": {
      const existe = state.ordenesCliente.some((o) => o.id === action.oc.id);
      return {
        ...state,
        ordenesCliente: existe
          ? state.ordenesCliente.map((o) => (o.id === action.oc.id ? action.oc : o))
          : [action.oc, ...state.ordenesCliente],
      };
    }

    case "REEMPLAZAR_OE": {
      const existe = state.ordenesEstacion.some((o) => o.id === action.oe.id);
      return {
        ...state,
        ordenesEstacion: existe
          ? state.ordenesEstacion.map((o) => (o.id === action.oe.id ? action.oe : o))
          : [...state.ordenesEstacion, action.oe],
      };
    }

    case "AGREGAR_INCIDENCIAS": {
      const idsExistentes = new Set(state.incidencias.map((i) => i.id));
      const nuevas = action.incidencias.filter((i) => !idsExistentes.has(i.id));
      return nuevas.length > 0 ? { ...state, incidencias: [...nuevas, ...state.incidencias] } : state;
    }

    case "REEMPLAZAR_HISTORIAL_OC": {
      const otros = state.historialComisiones.filter((h) => h.entidad_id !== action.ordenId);
      return { ...state, historialComisiones: [...action.historial, ...otros] };
    }

    default:
      return state;
  }
}

interface OrdenesContextValue {
  state: OrdenesState;
  /** Crea una OrdenCliente nueva. `conVobo` decide si nace en 1.1 o directo en 1.2
   * (checklist ya completo al momento de guardar). */
  crearOC: (input: OrdenClienteInput, conVobo: boolean) => Promise<OrdenCliente>;
  /** Actualiza una OrdenCliente existente. `auditoria.motivo` solo se manda si de verdad
   * cambió algún % de comisión (el formulario decide eso) — el backend valida quién puede
   * tocarlos (canal dedicado de comisiones, Dirección/Admin) y registra el motivo. */
  actualizarOC: (
    id: string,
    patch: Partial<OrdenCliente> & { estatus_orden?: EstadoOC },
    opts?: { auditoria?: { motivo: string } },
  ) => Promise<void>;
  /** Crea una OrdenEstacion nueva colgada de `ocId`. */
  crearOE: (ocId: string, input: OrdenEstacionInput) => Promise<OrdenEstacion>;
  /** 2.1 → 2.2: persiste solo los días modificados respecto a lo asignado. */
  avanzarAProgramados: (oeId: string, horariosProgramados: PeriodoTransmisionRow[], reporteRef?: string | null) => Promise<void>;
  /** 2.2 → 2.3: persiste los días modificados respecto a lo programado efectivo; el backend
   * genera las incidencias correspondientes. Devuelve las incidencias generadas (para que la
   * pantalla las pueda mostrar de inmediato). */
  avanzarAReales: (oeId: string, input: AvanzarARealesInput) => Promise<Incidencia[]>;
  /** Estado 2 → 3. */
  cerrarOC: (ocId: string, input: CerrarOCInput) => Promise<void>;
}

const OrdenesContext = createContext<OrdenesContextValue | null>(null);

export function OrdenesProvider({
  children,
  initialState,
}: {
  children: ReactNode;
  /** Estado ya cargado del backend real — `OrdenesExplorerPage` hace el fetch ANTES de
   * montar este provider (el inicializador de `useReducer` es síncrono). */
  initialState: OrdenesState;
}) {
  const [state, dispatch] = useReducer(reducer, undefined, () => initialState);

  const value = useMemo<OrdenesContextValue>(
    () => ({
      state,
      crearOC: async (input, conVobo) => {
        const dto = await crearOrdenClienteApi(ordenClienteCreateToApi(input, conVobo));
        const oc = await refrescarOrdenCliente(dto.orden_id);
        dispatch({ type: "REEMPLAZAR_OC", oc });
        return oc;
      },
      actualizarOC: async (id, patch, opts) => {
        // 1. Checklist: solo los ítems que de verdad cambiaron (canal propio, un PATCH por
        // ítem — no hay "PUT masivo" de checklist en el backend real).
        if (patch.revision_checklist) {
          const actual = state.ordenesCliente.find((o) => o.id === id);
          const anteriorChecklist = actual?.revision_checklist ?? {};
          for (const [item, completado] of Object.entries(patch.revision_checklist)) {
            if (anteriorChecklist[item] !== completado) {
              await toggleVoboApi(id, item, completado);
            }
          }
        }
        // 2. Campos normales (PUT) — nunca incluye comisión ni checklist (ver toApi.ts).
        const bodyPut = ordenClienteUpdateToApi(patch);
        if (Object.keys(bodyPut).length > 0) {
          await actualizarOrdenClienteApi(id, bodyPut);
        }
        // 3. Dar Vo.Bo., si el patch lo pide (mismo atajo que usa el formulario).
        if (patch.estatus_orden === "orden_cliente_con_vobo") {
          await darVoboApi(id);
        }
        // 4. Comisiones — canal dedicado (Dirección/Admin), solo si el llamador trae
        // auditoría (el formulario solo la manda cuando de verdad cambió un %).
        const cambioComision = Boolean(opts?.auditoria);
        if (cambioComision && opts?.auditoria) {
          await actualizarComisionesApi(id, {
            porcentaje_comision_vendedor_principal_snap: patch.porcentaje_comision_vendedor_principal_snap,
            porcentaje_comision_vendedor_secundario_snap: patch.porcentaje_comision_vendedor_secundario_snap,
            porcentaje_comision_agencia_snap: patch.porcentaje_comision_agencia_snap,
            motivo_cambio: opts.auditoria.motivo,
          });
        }
        const oc = await refrescarOrdenCliente(id);
        dispatch({ type: "REEMPLAZAR_OC", oc });
        if (cambioComision) {
          const historial = await listarHistorialComisionesApi(id);
          dispatch({ type: "REEMPLAZAR_HISTORIAL_OC", ordenId: id, historial: historial as HistorialComision[] });
        }
      },
      crearOE: async (ocId, input) => {
        const dto = await crearOrdenEstacionApi(ordenEstacionCreateToApi(ocId, input));
        const [oe, oc] = await Promise.all([
          refrescarOrdenEstacion(dto.orden_estacion_id),
          refrescarOrdenCliente(ocId),
        ]);
        dispatch({ type: "REEMPLAZAR_OE", oe });
        dispatch({ type: "REEMPLAZAR_OC", oc });
        return oe;
      },
      avanzarAProgramados: async (oeId, horariosProgramados, reporteRef) => {
        await avanzarProgramadosApi(oeId, programadosToApi(horariosProgramados, reporteRef));
        const oe = await refrescarOrdenEstacion(oeId);
        dispatch({ type: "REEMPLAZAR_OE", oe });
      },
      avanzarAReales: async (oeId, input) => {
        await avanzarRealesApi(oeId, realesToApi(input));
        const [oe, incidenciasDto] = await Promise.all([
          refrescarOrdenEstacion(oeId),
          listarIncidenciasDeOEApi(oeId),
        ]);
        dispatch({ type: "REEMPLAZAR_OE", oe });
        const incidenciasNuevas = incidenciasDto.map(incidenciaFromApi);
        dispatch({ type: "AGREGAR_INCIDENCIAS", incidencias: incidenciasNuevas });
        const oc = await refrescarOrdenCliente(oe.orden_id);
        dispatch({ type: "REEMPLAZAR_OC", oc });
        return incidenciasNuevas;
      },
      cerrarOC: async (ocId, input) => {
        await cerrarOrdenClienteApi(ocId, cerrarToApi(input));
        const oc = await refrescarOrdenCliente(ocId);
        dispatch({ type: "REEMPLAZAR_OC", oc });
      },
    }),
    [state],
  );

  return <OrdenesContext.Provider value={value}>{children}</OrdenesContext.Provider>;
}

export function useOrdenes(): OrdenesContextValue {
  const ctx = useContext(OrdenesContext);
  if (!ctx) throw new Error("useOrdenes() debe usarse dentro de <OrdenesProvider>.");
  return ctx;
}
