/** Pantalla "Órdenes del cliente": lista + panel de detalle (patrón F0), con filtro por
 * estado y búsqueda. Al llegar desde una vista operativa del sidebar ("Listas para
 * cerrar" / "Listas para facturar") arranca con esa pill ya activa en el toolbar — sin
 * letrero aparte (fix, petición del usuario: el aviso "Filtro activo: ..." describía el
 * filtro en términos técnicos que no le hacían sentido al usuario de negocio; la pill
 * resaltada en el toolbar ya comunica lo mismo). El alta/edición (Tanda 2) se abre a
 * pantalla completa, reemplazando la lista+detalle mientras dura.
 *
 * ADR-285 (petición del usuario, con captura): la tabla y su paginación pegan al
 * backend de verdad (`useOrdenesClientePagina`) — antes traían el 100% de las órdenes
 * (vía `OrdenesContext`/`cargarEstadoReal`) y paginaban/filtraban un arreglo completo en
 * el cliente. El panel de detalle de la fila seleccionada pide sus propios datos
 * (`useOrdenClienteSeleccionada`/`useOesDeLaOC`/`useIncidenciasDeLaOC`/
 * `useHistorialComisionesOC`), independiente de en qué página esté. Las escrituras
 * (alta/edición/cierre) siguen viviendo en `OrdenesContext` — fuera de alcance de esta
 * ronda, solo cambia de dónde se LEE.
 */

import { useEffect, useState } from "react";

import { CatalogToolbar, DetailEmpty, ListDetailLayout, Paginator } from "@/shared/ui";

import { RootBadge } from "../../components/EstadoBadge";
import { CierreOCForm } from "../../cierre/components/CierreOCForm";
import { fmtFecha, fmtFolio, fmtMonto, fmtRangoFechas } from "../../format";
import {
  useHistorialComisionesOC,
  useIncidenciasDeLaOC,
  useOesDeLaOC,
  useOrdenClienteSeleccionada,
  useOrdenesClientePagina,
} from "../../hooks";
import { findAgencia, findAnunciante, findVendedor, marcas } from "../../state/catalogosCache";
import type { CerrarOCInput } from "../../state/OrdenesContext";
import { useOrdenes } from "../../state/OrdenesContext";
import { totalesOC, type FiltroOrdenCliente } from "../../state/selectors";
import type { OrdenClienteInput } from "../../types";
import { OrdenClienteDetailPanel } from "../components/OrdenClienteDetailPanel";
import { OrdenClienteForm } from "../components/OrdenClienteForm";

const FILTROS: { key: FiltroOrdenCliente; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "activas", label: "Activas" },
  { key: "listas_cerrar", label: "Listas para cerrar" },
  { key: "listas_facturar", label: "Listas para facturar" },
];

type Modo = "view" | "new" | "edit" | "cierre";

interface OrdenClienteListPageProps {
  /** Filtro con el que arranca la pantalla (llegando desde una vista operativa del sidebar). */
  filtroInicial?: FiltroOrdenCliente;
  /** OC con la que arranca seleccionada (llegando desde "Ver OC →" del detalle de una OI). */
  ocIdPreseleccionada?: string;
  onSeleccionarOE: (oeId: string) => void;
  onAsignarEstaciones: (ocId: string) => void;
}

export function OrdenClienteListPage({
  filtroInicial,
  ocIdPreseleccionada,
  onSeleccionarOE,
  onAsignarEstaciones,
}: OrdenClienteListPageProps) {
  const { crearOC, actualizarOC, cerrarOC } = useOrdenes();
  const [filtro, setFiltro] = useState<FiltroOrdenCliente>(filtroInicial ?? "todas");
  // Al llegar con una OC preseleccionada (p.ej. "Ver OC →" desde el detalle de una orden
  // interna), el buscador arranca filtrado por su folio: así la tabla muestra SOLO esa
  // fila en vez de todas — antes solo se resaltaba en el detalle, sin filtrar la lista
  // (mismo fix que OrdenEstacionListPage.tsx para "Ver orden interna →"). Como la OC ya
  // no está disponible sincrónicamente (ADR-285: se pide al backend), se completa en
  // cuanto `useOrdenClienteSeleccionada` resuelve, una sola vez.
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(ocIdPreseleccionada ?? null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Paginación real contra el backend (ADR-285): ya no se trae el 100% de las órdenes.
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);

  const filtros = {
    page,
    size,
    q: search || undefined,
    listas_para_cerrar: filtro === "listas_cerrar" ? true : undefined,
    estatus_orden: filtro === "listas_facturar" ? ("orden_cerrada" as const) : undefined,
    activas: filtro === "activas" ? true : undefined,
  };
  const lista = useOrdenesClientePagina(filtros);
  const items = lista.data?.items ?? [];
  const total = lista.data?.total ?? 0;

  const seleccionadaQuery = useOrdenClienteSeleccionada(selectedId);
  const selected = seleccionadaQuery.data ?? null;
  const oesQuery = useOesDeLaOC(selected?.id);
  const oesDeLaOC = oesQuery.data ?? [];
  const incidenciasQuery = useIncidenciasDeLaOC(oesDeLaOC);
  const historialQuery = useHistorialComisionesOC(selected?.id);

  useEffect(() => {
    if (ocIdPreseleccionada && selected?.id === ocIdPreseleccionada && search === "") {
      setSearch(selected.folio_orden);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const onGuardar = async (input: OrdenClienteInput, opts: { motivoComision?: string }) => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (modo === "new") {
        // ADR-249 (petición del usuario): en alta también se exige motivo si algún % de
        // comisión diverge del sugerido del catálogo (el formulario ya decidió eso).
        const nueva = await crearOC(input, { motivoComision: opts.motivoComision });
        setSelectedId(nueva.id);
        setModo("view");
        // ADR-100: alta unificada — al guardar la Orden de Servicio se encadena directo
        // hacia la captura de su primera Orden de Transmisión, sin pasar por la lista.
        onAsignarEstaciones(nueva.id);
        return;
      } else if (modo === "edit" && selected) {
        const auditoria = opts.motivoComision ? { motivo: opts.motivoComision } : undefined;
        await actualizarOC(selected.id, input, { auditoria });
      }
      setModo("view");
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "No se pudo guardar la orden.");
    } finally {
      setSubmitting(false);
    }
  };

  if (modo === "new" || modo === "edit") {
    return (
      <OrdenClienteForm
        title={modo === "new" ? "Nueva Orden de Servicio" : `Editar: ${fmtFolio(selected?.folio_orden)}`}
        isEdit={modo === "edit"}
        estatusActual={selected?.estatus_orden}
        defaultValues={modo === "edit" ? selected ?? undefined : undefined}
        oeCount={modo === "edit" && selected ? selected.oe_count : 0}
        historialComisiones={modo === "edit" ? (historialQuery.data ?? []) : []}
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

  if (modo === "cierre" && selected) {
    const onConfirmarCierre = async (input: CerrarOCInput) => {
      setSubmitError(null);
      setSubmitting(true);
      try {
        await cerrarOC(selected.id, input);
        setModo("view");
      } catch (e) {
        setSubmitError(e instanceof Error ? e.message : "No se pudo cerrar la orden.");
      } finally {
        setSubmitting(false);
      }
    };
    return (
      <CierreOCForm
        oc={selected}
        oesDeLaOC={oesDeLaOC}
        incidencias={incidenciasQuery.data ?? []}
        submitError={submitError}
        submitting={submitting}
        onConfirmar={onConfirmarCierre}
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
          <div className="cat-title">Órdenes de Servicio</div>
          <div className="cat-sub">
            Órdenes recibidas del anunciante o agencia. De aquí se derivan las órdenes de transmisión (OT). El listado muestra el estado
            raíz (1–5); el detalle de la orden muestra el sub-estado de cada OT hija.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-phase"
          onClick={() => {
            setSelectedId(null);
            setSubmitError(null);
            setModo("new");
          }}
        >
          + Nueva orden
        </button>
      </div>

      <CatalogToolbar
        search={search}
        onSearch={(v) => {
          setSearch(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar folio, anunciante, no. de orden…"
        filterLabel="Estado"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as FiltroOrdenCliente);
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
                <th className="td-center" style={{ width: "10%" }}>Folio</th>
                <th className="td-center" style={{ width: "9%" }}>Fecha</th>
                <th style={{ width: "15%" }}>Anunciante</th>
                <th style={{ width: "13%" }}>Agencia / Vendedor</th>
                {/* Fix (petición del usuario): decían "Producto / Marca" y "Campaña" pero
                    desplegaban otra cosa — `oc.producto` es texto libre de "Campaña" (así lo
                    llama el propio formulario, `OrdenClienteForm.tsx`: "Descripción de la
                    campaña anunciada"), y esta columna de fechas es el PERIODO de esa
                    campaña, no un nombre. Mismos datos de siempre, solo se corrige el rótulo. */}
                <th style={{ width: "13%" }}>Marca / Campaña</th>
                <th className="td-center" style={{ width: "11%" }}>Periodo</th>
                <th className="td-center" style={{ width: "9%" }}>
                  Total
                </th>
                <th className="td-center" style={{ width: "6%" }}>
                  OT
                </th>
                <th className="td-center" style={{ width: "14%" }}>
                  Estado
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((oc) => {
                const anunciante = findAnunciante(oc.anunciante_id);
                const agencia = findAgencia(oc.agencia_id);
                const vendedor = findVendedor(oc.vendedor_principal_id);
                const marca = oc.marca_id ? marcas.find((m) => m.id === oc.marca_id) : null;
                const { total: totalOC } = totalesOC(oc);
                return (
                  <tr key={oc.id} className={selectedId === oc.id ? "sel" : ""} onClick={() => setSelectedId(oc.id)}>
                    <td className="td-center">
                      <div className="td-mono">{fmtFolio(oc.folio_orden)}</div>
                      <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 1 }}>{oc.numero_orden_cliente}</div>
                    </td>
                    <td className="td-mono td-center" style={{ fontSize: 11 }}>{fmtFecha(oc.created_at)}</td>
                    <td className="td-main">{anunciante ? anunciante.nombre_comercial : "—"}</td>
                    <td className="td-2">
                      <div style={{ fontSize: 12 }}>{agencia ? agencia.nombre_agencia : <span style={{ color: "var(--text3)" }}>Sin agencia</span>}</div>
                      <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 1 }}>{vendedor ? vendedor.nombre_vendedor : "—"}</div>
                    </td>
                    <td className="td-2">
                      <div style={{ fontSize: 12 }}>{marca ? marca.nombre_marca : "—"}</div>
                      <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 1 }}>{oc.producto}</div>
                    </td>
                    <td className="td-mono td-center" style={{ fontSize: 11 }}>
                      {fmtRangoFechas(oc.fecha_inicio_campania, oc.fecha_fin_campania)}
                    </td>
                    <td className="td-center td-mono" style={{ fontWeight: 500 }}>
                      {fmtMonto(totalOC)}
                    </td>
                    <td className="td-center td-2">{oc.oe_count}</td>
                    <td className="td-center">
                      <RootBadge estatus={oc.estatus_orden} />
                    </td>
                  </tr>
                );
              })}
              {lista.isLoading && (
                <tr>
                  <td colSpan={9} className="state-msg">
                    Cargando órdenes…
                  </td>
                </tr>
              )}
              {lista.isError && (
                <tr>
                  <td colSpan={9} className="state-msg error">
                    No se pudieron cargar las órdenes.
                  </td>
                </tr>
              )}
              {!lista.isLoading && !lista.isError && items.length === 0 && (
                <tr>
                  <td colSpan={9} className="state-msg">
                    No hay órdenes para los filtros seleccionados.
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
            <OrdenClienteDetailPanel
              oc={selected}
              ordenesEstacion={oesDeLaOC}
              incidencias={incidenciasQuery.data ?? []}
              historialComisiones={historialQuery.data ?? []}
              onSeleccionarOE={onSeleccionarOE}
              onEditar={() => {
                setSubmitError(null);
                setModo("edit");
              }}
              onAsignarEstaciones={() => onAsignarEstaciones(selected.id)}
              onCerrar={() => {
                setSubmitError(null);
                setModo("cierre");
              }}
            />
          ) : (
            <DetailEmpty message="Selecciona una orden para ver sus datos y órdenes de transmisión." />
          )
        }
      />
    </>
  );
}
