/** Pantalla "Órdenes internas": lista + panel de detalle, con filtro por sub-estado y
 * buscador. El alta (Tanda 3) abre a pantalla completa, igual que en Órdenes del cliente.
 */

import { useMemo, useState } from "react";

import { CatalogToolbar, DetailEmpty, ListDetailLayout } from "@/shared/ui";

import { EstadoOIBadge } from "../../components/EstadoBadge";
import { fmtMonto } from "../../format";
import { findAfiliado, findEstacion, findPlaza } from "../../state/catalogosCache";
import { useOrdenes } from "../../state/OrdenesContext";
import { oiImporte, oiPeriodoTexto, oiTotalSpots } from "../../state/selectors";
import type { EstadoOI, OrdenEstacionInput, PeriodoTransmisionRow } from "../../types";
import { OrdenEstacionDetailPanel } from "../components/OrdenEstacionDetailPanel";
import { OrdenEstacionForm } from "../components/OrdenEstacionForm";
import { ProgramadosForm } from "../components/ProgramadosForm";
import { RealesForm } from "../components/RealesForm";

export type FiltroOI = "todas" | EstadoOI;

const FILTROS: { key: FiltroOI; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "asignada_afiliado", label: "2.1 Asignadas" },
  { key: "programados_conciliados", label: "2.2 Programados" },
  { key: "reales_conciliados", label: "2.3 Reales" },
];

type Modo = "view" | "new" | "programados" | "reales";

interface OrdenEstacionListPageProps {
  filtroInicial?: FiltroOI;
  oeIdPreseleccionada?: string;
  ocIdParaNueva?: string;
  onVerOC: (ocId: string) => void;
  onVerVerificacion: (oeId: string) => void;
}

export function OrdenEstacionListPage({
  filtroInicial,
  oeIdPreseleccionada,
  ocIdParaNueva,
  onVerOC,
  onVerVerificacion,
}: OrdenEstacionListPageProps) {
  const { state, crearOE, avanzarAProgramados, avanzarAReales } = useOrdenes();
  const [filtro, setFiltro] = useState<FiltroOI>(filtroInicial ?? "todas");
  // Al llegar con una OI preseleccionada (p.ej. "Ver orden interna →" desde Verificaciones
  // o Incidencias), el buscador arranca filtrado por su folio: así la tabla muestra SOLO
  // esa fila en vez de las 12 (o las que haya) — antes solo se resaltaba en el detalle,
  // sin filtrar la lista.
  const [search, setSearch] = useState(() => {
    if (!oeIdPreseleccionada) return "";
    const oe = state.ordenesEstacion.find((o) => o.id === oeIdPreseleccionada);
    return oe?.folio_orden_interna ?? "";
  });
  const [selectedId, setSelectedId] = useState<string | null>(oeIdPreseleccionada ?? null);
  const [modo, setModo] = useState<Modo>(ocIdParaNueva ? "new" : "view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    return state.ordenesEstacion.filter((oe) => {
      if (filtro !== "todas" && oe.estatus !== filtro) return false;
      if (q) {
        const estacion = findEstacion(oe.estacion_id);
        const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
        const oc = state.ordenesCliente.find((o) => o.id === oe.orden_id);
        const haystack = `${oe.folio_orden_interna} ${estacion?.nombre_estacion ?? ""} ${afiliado?.nombre_afiliado ?? ""} ${oc?.folio_orden ?? ""}`.toLowerCase();
        return haystack.includes(q);
      }
      return true;
    });
  }, [state.ordenesEstacion, state.ordenesCliente, filtro, search]);

  const selected = selectedId ? (state.ordenesEstacion.find((o) => o.id === selectedId) ?? null) : null;

  const onGuardar = async (ocId: string, input: OrdenEstacionInput) => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const nueva = await crearOE(ocId, input);
      setSelectedId(nueva.id);
      setModo("view");
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "No se pudo guardar la orden interna.");
    } finally {
      setSubmitting(false);
    }
  };

  if (modo === "new") {
    return (
      <OrdenEstacionForm
        ocIdFijo={ocIdParaNueva}
        submitError={submitError}
        submitting={submitting}
        onGuardar={onGuardar}
        onCancelar={() => {
          setModo("view");
          setSubmitError(null);
        }}
      />
    );
  }

  if (modo === "programados" && selected) {
    return (
      <ProgramadosForm
        oe={selected}
        submitError={submitError}
        submitting={submitting}
        onAvanzar={async (horariosProgramados, reporteRef) => {
          setSubmitError(null);
          setSubmitting(true);
          try {
            await avanzarAProgramados(selected.id, horariosProgramados, reporteRef);
            setModo("view");
          } catch (e) {
            setSubmitError(e instanceof Error ? e.message : "No se pudo avanzar la orden interna.");
          } finally {
            setSubmitting(false);
          }
        }}
        onCancelar={() => {
          setModo("view");
          setSubmitError(null);
        }}
      />
    );
  }

  if (modo === "reales" && selected) {
    return (
      <RealesForm
        oe={selected}
        submitError={submitError}
        submitting={submitting}
        onAvanzar={async (horariosReales: PeriodoTransmisionRow[], extra) => {
          setSubmitError(null);
          setSubmitting(true);
          try {
            await avanzarAReales(selected.id, { horariosReales, ...extra });
            setModo("view");
          } catch (e) {
            setSubmitError(e instanceof Error ? e.message : "No se pudo avanzar la orden interna.");
          } finally {
            setSubmitting(false);
          }
        }}
        onCancelar={() => {
          setModo("view");
          setSubmitError(null);
        }}
      />
    );
  }

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Órdenes internas</div>
          <div className="cat-sub">
            Derivación por estación de una orden del cliente. El sub-estado (2.1/2.2/2.3) vive aquí; el estado raíz de la OC solo refleja
            que existe al menos una.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-phase"
          onClick={() => {
            setSubmitError(null);
            setModo("new");
          }}
        >
          + Nueva orden interna
        </button>
      </div>

      <CatalogToolbar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Buscar folio, estación, afiliado, OC de origen…"
        filterLabel="Sub-estado"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as FiltroOI);
          setSelectedId(null);
        }}
        count={`${items.length} de ${state.ordenesEstacion.length}`}
      />

      <ListDetailLayout
        list={
          <table className="cat-table">
            <thead>
              <tr>
                <th style={{ width: "12%" }}>Folio</th>
                <th style={{ width: "11%" }}>OC de origen</th>
                <th style={{ width: "16%" }}>Estación</th>
                <th style={{ width: "10%" }}>Plaza</th>
                <th style={{ width: "15%" }}>Afiliado</th>
                <th style={{ width: "14%" }}>Periodo</th>
                <th className="td-center" style={{ width: "7%" }}>
                  Spots
                </th>
                <th className="td-right" style={{ width: "10%" }}>
                  Importe
                </th>
                <th className="td-center" style={{ width: "15%" }}>
                  Sub-estado
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((oe) => {
                const estacion = findEstacion(oe.estacion_id);
                const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
                const plaza = findPlaza(oe.plaza_id);
                const oc = state.ordenesCliente.find((o) => o.id === oe.orden_id);
                return (
                  <tr key={oe.id} className={selectedId === oe.id ? "sel" : ""} onClick={() => setSelectedId(oe.id)}>
                    <td className="td-mono">{oe.folio_orden_interna}</td>
                    <td className="td-mono" style={{ fontSize: 11 }}>
                      {oc?.folio_orden ?? "—"}
                    </td>
                    <td className="td-main">{estacion?.nombre_estacion ?? "—"}</td>
                    <td className="td-2">{plaza?.nombre_plaza ?? "—"}</td>
                    <td className="td-2">{afiliado?.nombre_afiliado ?? "—"}</td>
                    <td className="td-mono" style={{ fontSize: 11 }}>
                      {oiPeriodoTexto(oe)}
                    </td>
                    <td className="td-center td-mono">{oiTotalSpots(oe)}</td>
                    <td className="td-right td-mono" style={{ fontWeight: 500 }}>
                      {fmtMonto(oiImporte(oe), { sinDecimales: true })}
                    </td>
                    <td className="td-center">
                      <EstadoOIBadge estatus={oe.estatus} />
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={9} className="state-msg">
                    No hay órdenes internas para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        }
        detail={
          selected ? (
            <OrdenEstacionDetailPanel
              oe={selected}
              oc={state.ordenesCliente.find((o) => o.id === selected.orden_id)}
              incidencias={state.incidencias}
              onVerOC={() => onVerOC(selected.orden_id)}
              onCapturarProgramados={() => {
                setSubmitError(null);
                setModo("programados");
              }}
              onCapturarReales={() => {
                setSubmitError(null);
                setModo("reales");
              }}
              onVerVerificacion={() => onVerVerificacion(selected.id)}
            />
          ) : (
            <DetailEmpty message="Selecciona una orden interna para ver su detalle." />
          )
        }
      />
    </>
  );
}
