/** Pantalla "Verificaciones": lista + panel de detalle sobre una vista DERIVADA — no hay
 * alta ni edición porque no es una entidad capturable. Cada fila proyecta una OI que llegó
 * a 2.3 (reales conciliados). Ver `VerificacionDerivada` en types.ts para el porqué.
 *
 * ADR-285 (petición del usuario, con captura): la tabla pagina contra el backend
 * (`useVerificacionesPagina`) en vez de derivar sobre el arreglo completo de OE del
 * sistema (`state.ordenesEstacion` vía `cargarEstadoReal`) — misma razón que
 * "Órdenes de Transmisión". La fila seleccionada usa `useOrdenEstacionSeleccionada`
 * (ya trae días + verificaciones completos), igual que esa pantalla.
 */

import { useEffect, useState } from "react";

import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import { fmtFecha, fmtFolio } from "../../format";
import { useIncidenciasDeLaOC, useOrdenEstacionSeleccionada, useVerificacionesPagina } from "../../hooks";
import { findAfiliado, findEstacion } from "../../state/catalogosCache";
import { verificacionDerivada } from "../../state/selectors";
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
  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(oeIdPreseleccionada ?? null);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);

  const filtros = {
    page,
    size,
    q: search || undefined,
    tiene_incidencias: filtro === "todas" ? undefined : filtro === "con_incidencias",
  };
  const lista = useVerificacionesPagina(filtros);
  const ordenesEstacion = lista.data?.items ?? [];
  const items = ordenesEstacion.map(verificacionDerivada);
  const total = lista.data?.total ?? 0;

  const seleccionadaQuery = useOrdenEstacionSeleccionada(selectedId);
  const selectedOE = seleccionadaQuery.data ?? null;
  const selected = selectedOE ? verificacionDerivada(selectedOE) : null;
  const incidenciasQuery = useIncidenciasDeLaOC(ordenesEstacion);
  const incidencias = incidenciasQuery.data ?? [];
  // La OE seleccionada puede no estar en la página actual (p.ej. preselección desde otra
  // pantalla) — sus incidencias se piden aparte, igual que `OrdenEstacionListPage.tsx`.
  const incidenciasSeleccionadaQuery = useIncidenciasDeLaOC(selectedOE ? [selectedOE] : undefined);
  const incidenciasSeleccionada = incidenciasSeleccionadaQuery.data ?? [];

  useEffect(() => {
    if (oeIdPreseleccionada && selectedOE?.id === oeIdPreseleccionada && search === "") {
      setSearch(selectedOE.folio_orden_interna);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedOE]);

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Verificaciones</div>
          <div className="cat-sub">
            Vista derivada: no es una entidad capturable — cada fila compara lo programado (efectivo) contra lo realmente transmitido de
            una Orden de Transmisión que llegó a 2.3. Llegar a 2.3 ya implica que quedó reconciliada.
          </div>
        </div>
      </div>

      <CatalogToolbar
        search={search}
        onSearch={(v) => {
          setSearch(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar folio, estación, afiliado…"
        filterLabel="Incidencias"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setSelectedId(null);
          setPage(1);
        }}
        count={`${items.length} de ${total}`}
      />

      <ListDetailLayout
        list={
          <>
          <table className="cat-table">
            <thead>
              <tr>
                <th className="td-center" style={{ width: "12%" }}>Folio OI</th>
                <th className="td-center" style={{ width: "10%" }}>Fecha</th>
                <th style={{ width: "20%" }}>Estación</th>
                <th style={{ width: "19%" }}>Afiliado</th>
                <th className="td-center" style={{ width: "12%" }}>
                  Programado
                </th>
                <th className="td-center" style={{ width: "10%" }}>
                  Real
                </th>
                <th className="td-center" style={{ width: "8%" }}>
                  Inc.
                </th>
                <th className="td-center" style={{ width: "9%" }}>
                  Estado
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((v) => {
                const oe = ordenesEstacion.find((o) => o.id === v.ordenEstacionId);
                const estacion = oe ? findEstacion(oe.estacion_id) : undefined;
                const afiliado = estacion ? findAfiliado(estacion.afiliado_id) : undefined;
                const incDeV = incidencias.filter((i) => i.orden_interna_id === v.ordenEstacionId);
                return (
                  <tr key={v.ordenEstacionId} className={selectedId === v.ordenEstacionId ? "sel" : ""} onClick={() => setSelectedId(v.ordenEstacionId)}>
                    <td className="td-mono td-center">{fmtFolio(v.folioOrdenInterna)}</td>
                    <td className="td-mono td-center">{fmtFecha(v.fechaInicio)}</td>
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
              {lista.isLoading && (
                <tr>
                  <td colSpan={8} className="state-msg">
                    Cargando verificaciones…
                  </td>
                </tr>
              )}
              {lista.isError && (
                <tr>
                  <td colSpan={8} className="state-msg error">
                    No se pudieron cargar las verificaciones.
                  </td>
                </tr>
              )}
              {!lista.isLoading && !lista.isError && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="state-msg">
                    No hay verificaciones para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {total > 0 && (
            <Paginator
              page={page}
              size={size}
              total={total}
              onChange={(np, ns) => {
                setPage(np);
                setSize(ns);
              }}
            />
          )}
          </>
        }
        detail={
          selected ? (
            <VerificacionDetailPanel
              key={selected.ordenEstacionId}
              verificacion={selected}
              oe={selectedOE ?? undefined}
              incidencias={incidenciasSeleccionada}
              onVerOE={() => onVerOE(selected.ordenEstacionId)}
            />
          ) : (
            <DetailEmpty message="Selecciona una Orden de Transmisión reconciliada para ver el detalle día a día." />
          )
        }
      />
    </>
  );
}
