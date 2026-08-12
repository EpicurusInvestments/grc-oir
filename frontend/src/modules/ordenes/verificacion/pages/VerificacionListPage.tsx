/** Pantalla "Verificaciones": lista + panel de detalle sobre una vista DERIVADA — no hay
 * alta ni edición porque no es una entidad capturable. Cada fila proyecta una OI que llegó
 * a 2.3 (reales conciliados). Ver `VerificacionDerivada` en types.ts para el porqué.
 */

import { useMemo, useState } from "react";

import { CatalogToolbar, DetailEmpty, ListDetailLayout } from "@/shared/ui";

import { findAfiliado, findEstacion } from "../../state/catalogosCache";
import { useOrdenes } from "../../state/OrdenesContext";
import { verificacionesDerivadas } from "../../state/selectors";
import { VerificacionDetailPanel } from "../components/VerificacionDetailPanel";

type Filtro = "todas" | "con_incidencias" | "sin_incidencias";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "con_incidencias", label: "Con incidencias" },
  { key: "sin_incidencias", label: "Sin incidencias" },
];

interface VerificacionListPageProps {
  oeIdPreseleccionada?: string;
  onVerOE: (oeId: string) => void;
}

export function VerificacionListPage({ oeIdPreseleccionada, onVerOE }: VerificacionListPageProps) {
  const { state } = useOrdenes();
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(oeIdPreseleccionada ?? null);

  const todas = useMemo(() => verificacionesDerivadas(state.ordenesEstacion), [state.ordenesEstacion]);

  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    return todas.filter((v) => {
      const incDeV = state.incidencias.filter((i) => i.orden_interna_id === v.ordenEstacionId);
      if (filtro === "con_incidencias" && incDeV.length === 0) return false;
      if (filtro === "sin_incidencias" && incDeV.length > 0) return false;
      if (q) {
        const oe = state.ordenesEstacion.find((o) => o.id === v.ordenEstacionId);
        const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
        const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
        const haystack = `${v.folioOrdenInterna} ${estacion?.nombre_estacion ?? ""} ${afiliado?.nombre_afiliado ?? ""}`.toLowerCase();
        return haystack.includes(q);
      }
      return true;
    });
  }, [todas, state.incidencias, state.ordenesEstacion, filtro, search]);

  const selected = selectedId ? (todas.find((v) => v.ordenEstacionId === selectedId) ?? null) : null;
  const selectedOE = selected ? state.ordenesEstacion.find((o) => o.id === selected.ordenEstacionId) : undefined;

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Verificaciones</div>
          <div className="cat-sub">
            Vista derivada: no es una entidad capturable — cada fila compara lo programado (efectivo) contra lo realmente transmitido de
            una orden interna que llegó a 2.3. Llegar a 2.3 ya implica que quedó reconciliada.
          </div>
        </div>
      </div>

      <CatalogToolbar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Buscar folio, estación, afiliado…"
        filterLabel="Incidencias"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setSelectedId(null);
        }}
        count={`${items.length} de ${todas.length}`}
      />

      <ListDetailLayout
        list={
          <table className="cat-table">
            <thead>
              <tr>
                <th style={{ width: "14%" }}>Folio OI</th>
                <th style={{ width: "23%" }}>Estación</th>
                <th style={{ width: "21%" }}>Afiliado</th>
                <th className="td-center" style={{ width: "13%" }}>
                  Programado
                </th>
                <th className="td-center" style={{ width: "11%" }}>
                  Real
                </th>
                <th className="td-center" style={{ width: "9%" }}>
                  Inc.
                </th>
                <th className="td-center" style={{ width: "9%" }}>
                  Estado
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((v) => {
                const oe = state.ordenesEstacion.find((o) => o.id === v.ordenEstacionId);
                const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
                const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
                const incDeV = state.incidencias.filter((i) => i.orden_interna_id === v.ordenEstacionId);
                return (
                  <tr key={v.ordenEstacionId} className={selectedId === v.ordenEstacionId ? "sel" : ""} onClick={() => setSelectedId(v.ordenEstacionId)}>
                    <td className="td-mono">{v.folioOrdenInterna}</td>
                    <td className="td-main">{estacion?.nombre_estacion ?? "—"}</td>
                    <td className="td-2">{afiliado?.nombre_afiliado ?? "—"}</td>
                    <td className="td-center td-mono">{v.totalProgramado}</td>
                    <td className="td-center td-mono">{v.totalReal}</td>
                    <td className="td-center">
                      {incDeV.length > 0 ? <span className="badge b-amber">{incDeV.length}</span> : <span className="muted">—</span>}
                    </td>
                    <td className="td-center">
                      <span className="badge b-teal">Reconciliada</span>
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={7} className="state-msg">
                    No hay verificaciones para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        }
        detail={
          selected ? (
            <VerificacionDetailPanel
              verificacion={selected}
              oe={selectedOE}
              incidencias={state.incidencias.filter((i) => i.orden_interna_id === selected.ordenEstacionId)}
              onVerOE={() => onVerOE(selected.ordenEstacionId)}
            />
          ) : (
            <DetailEmpty message="Selecciona una orden interna reconciliada para ver el detalle día a día." />
          )
        }
      />
    </>
  );
}
