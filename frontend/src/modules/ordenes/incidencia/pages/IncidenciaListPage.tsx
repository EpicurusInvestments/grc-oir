/** Pantalla "Incidencias": lista + panel de detalle de las incidencias generadas
 * automáticamente al avanzar cada OI de 2.2 → 2.3 (ver `avanzarAReales` en
 * `OrdenesContext`). No hay alta manual: toda incidencia nace de una diferencia entre lo
 * programado y lo realmente transmitido.
 */

import { useMemo, useState } from "react";

import { CatalogToolbar, DetailEmpty, ListDetailLayout } from "@/shared/ui";

import { fmtMonto } from "../../format";
import { findEstacion } from "../../state/catalogosCache";
import { useOrdenes } from "../../state/OrdenesContext";
import { IncidenciaDetailPanel } from "../components/IncidenciaDetailPanel";

type Filtro = "todas" | "bonificacion" | "descuento";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "bonificacion", label: "Bonificaciones" },
  { key: "descuento", label: "Descuentos" },
];

interface IncidenciaListPageProps {
  incIdPreseleccionada?: string;
  onVerOE: (oeId: string) => void;
  onVerVerificacion: (oeId: string) => void;
}

export function IncidenciaListPage({ incIdPreseleccionada, onVerOE, onVerVerificacion }: IncidenciaListPageProps) {
  const { state } = useOrdenes();
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(incIdPreseleccionada ?? null);

  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    return state.incidencias.filter((i) => {
      if (filtro !== "todas" && i.tipo !== filtro) return false;
      if (q) {
        const oe = state.ordenesEstacion.find((o) => o.id === i.orden_interna_id);
        const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
        const haystack = `${oe?.folio_orden_interna ?? ""} ${estacion?.nombre_estacion ?? ""} ${i.nota_excepcion}`.toLowerCase();
        return haystack.includes(q);
      }
      return true;
    });
  }, [state.incidencias, state.ordenesEstacion, filtro, search]);

  const selected = selectedId ? (state.incidencias.find((i) => i.id === selectedId) ?? null) : null;
  const selectedOE = selected ? state.ordenesEstacion.find((o) => o.id === selected.orden_interna_id) : undefined;

  const montoNeto = items.reduce((s, i) => s + i.monto_ajuste, 0);

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Incidencias</div>
          <div className="cat-sub">
            Diferencias entre lo programado y lo realmente transmitido, generadas automáticamente al avanzar una orden interna a 2.3. No
            se capturan a mano.
          </div>
        </div>
      </div>

      <CatalogToolbar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Buscar folio, estación, nota…"
        filterLabel="Tipo"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setSelectedId(null);
        }}
        count={`${items.length} de ${state.incidencias.length} · neto ${fmtMonto(montoNeto)}`}
      />

      <ListDetailLayout
        list={
          <table className="cat-table">
            <thead>
              <tr>
                <th style={{ width: "12%" }}>Fecha</th>
                <th style={{ width: "13%" }}>Folio OI</th>
                <th style={{ width: "24%" }}>Estación</th>
                <th className="td-center" style={{ width: "11%" }}>
                  Tipo
                </th>
                <th className="td-center" style={{ width: "16%" }}>
                  Spots (asig. → real)
                </th>
                <th className="td-right" style={{ width: "12%" }}>
                  Ajuste
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => {
                const oe = state.ordenesEstacion.find((o) => o.id === i.orden_interna_id);
                const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
                return (
                  <tr key={i.id} className={selectedId === i.id ? "sel" : ""} onClick={() => setSelectedId(i.id)}>
                    <td className="td-mono">{i.fecha_transmision}</td>
                    <td className="td-mono" style={{ fontSize: 11 }}>
                      {oe?.folio_orden_interna ?? "—"}
                    </td>
                    <td className="td-main">{estacion?.nombre_estacion ?? "—"}</td>
                    <td className="td-center">
                      <span className={`badge ${i.tipo === "bonificacion" ? "b-teal" : "b-red"}`}>
                        {i.tipo === "bonificacion" ? "Bonif." : "Desc."}
                      </span>
                    </td>
                    <td className="td-center td-mono">
                      {i.spots_asignados} → {i.spots_reales}
                    </td>
                    <td
                      className="td-right td-mono"
                      style={{ fontWeight: 500, color: i.monto_ajuste >= 0 ? "var(--green-text)" : "var(--red-text)" }}
                    >
                      {i.monto_ajuste >= 0 ? "+" : ""}
                      {fmtMonto(i.monto_ajuste)}
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={6} className="state-msg">
                    No hay incidencias para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        }
        detail={
          selected ? (
            <IncidenciaDetailPanel
              incidencia={selected}
              oe={selectedOE}
              onVerOE={() => onVerOE(selected.orden_interna_id)}
              onVerVerificacion={() => onVerVerificacion(selected.orden_interna_id)}
            />
          ) : (
            <DetailEmpty message="Selecciona una incidencia para ver su detalle." />
          )
        }
      />
    </>
  );
}
