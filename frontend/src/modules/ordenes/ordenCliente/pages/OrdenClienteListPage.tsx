/** Pantalla "Órdenes del cliente": lista + panel de detalle (patrón F0), con filtro por
 * estado, búsqueda y el filtro activo (chip removible) cuando se llega desde una vista
 * operativa del sidebar ("Listas para cerrar" / "Listas para facturar"). El alta/edición
 * (Tanda 2) se abre a pantalla completa, reemplazando la lista+detalle mientras dura.
 */

import { useMemo, useState } from "react";

import { CatalogToolbar, DetailEmpty, ListDetailLayout } from "@/shared/ui";

import { RootBadge } from "../../components/EstadoBadge";
import { CierreOCForm } from "../../cierre/components/CierreOCForm";
import { fmtMonto, fmtRangoFechas } from "../../format";
import { findAgencia, findAnunciante, findVendedor, marcas } from "../../state/catalogosCache";
import type { CerrarOCInput } from "../../state/OrdenesContext";
import { useOrdenes } from "../../state/OrdenesContext";
import { filtrarOrdenesCliente, oesDeOC, totalesOC, type FiltroOrdenCliente } from "../../state/selectors";
import type { OrdenClienteInput } from "../../types";
import { OrdenClienteDetailPanel } from "../components/OrdenClienteDetailPanel";
import { OrdenClienteForm } from "../components/OrdenClienteForm";

const FILTROS: { key: FiltroOrdenCliente; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "activas", label: "Activas" },
  { key: "listas_cerrar", label: "Listas para cerrar" },
  { key: "listas_facturar", label: "Listas para facturar" },
];

const FILTRO_DESCRIPCION: Partial<Record<FiltroOrdenCliente, string>> = {
  listas_cerrar: "Solo órdenes cuyas órdenes internas están todas en 2.3 (reales conciliados).",
  listas_facturar: "Solo órdenes ya cerradas (estado 3).",
};

type Modo = "view" | "new" | "edit" | "cierre";

interface OrdenClienteListPageProps {
  /** Filtro con el que arranca la pantalla (llegando desde una vista operativa del sidebar). */
  filtroInicial?: FiltroOrdenCliente;
  /** OC con la que arranca seleccionada (llegando desde "Ver OC →" del detalle de una OI). */
  ocIdPreseleccionada?: string;
  onQuitarFiltroInicial?: () => void;
  onSeleccionarOE: (oeId: string) => void;
  onAsignarEstaciones: (ocId: string) => void;
}

export function OrdenClienteListPage({
  filtroInicial,
  ocIdPreseleccionada,
  onQuitarFiltroInicial,
  onSeleccionarOE,
  onAsignarEstaciones,
}: OrdenClienteListPageProps) {
  const { state, crearOC, actualizarOC, cerrarOC } = useOrdenes();
  const [filtro, setFiltro] = useState<FiltroOrdenCliente>(filtroInicial ?? "todas");
  // Al llegar con una OC preseleccionada (p.ej. "Ver OC →" desde el detalle de una orden
  // interna), el buscador arranca filtrado por su folio: así la tabla muestra SOLO esa
  // fila en vez de todas — antes solo se resaltaba en el detalle, sin filtrar la lista
  // (mismo fix que OrdenEstacionListPage.tsx para "Ver orden interna →").
  const [search, setSearch] = useState(() => {
    if (!ocIdPreseleccionada) return "";
    const oc = state.ordenesCliente.find((o) => o.id === ocIdPreseleccionada);
    return oc?.folio_orden ?? "";
  });
  const [selectedId, setSelectedId] = useState<string | null>(ocIdPreseleccionada ?? null);
  const [modo, setModo] = useState<Modo>("view");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const items = useMemo(() => {
    const filtrados = filtrarOrdenesCliente(state.ordenesCliente, state.ordenesEstacion, { filtro, search });
    // Más reciente primero: para que una OC recién dada de alta aparezca al principio.
    return [...filtrados].sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [state.ordenesCliente, state.ordenesEstacion, filtro, search]);
  const selected = selectedId ? (state.ordenesCliente.find((o) => o.id === selectedId) ?? null) : null;

  const filtroDescripcion = filtro !== (filtroInicial ?? "todas") ? undefined : FILTRO_DESCRIPCION[filtro];

  const onGuardar = async (input: OrdenClienteInput, opts: { darVobo: boolean; motivoComision?: string }) => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (modo === "new") {
        const nueva = await crearOC(input, opts.darVobo);
        setSelectedId(nueva.id);
      } else if (modo === "edit" && selected) {
        const auditoria = opts.motivoComision ? { motivo: opts.motivoComision } : undefined;
        await actualizarOC(
          selected.id,
          { ...input, ...(opts.darVobo ? { estatus_orden: "orden_cliente_con_vobo" as const } : {}) },
          { auditoria },
        );
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
        title={modo === "new" ? "Nueva orden del cliente" : `Editar: ${selected?.folio_orden}`}
        isEdit={modo === "edit"}
        estatusActual={selected?.estatus_orden}
        defaultValues={modo === "edit" ? selected ?? undefined : undefined}
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
        oesDeLaOC={oesDeOC(state.ordenesEstacion, selected.id)}
        incidencias={state.incidencias}
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
          <div className="cat-title">Órdenes del cliente</div>
          <div className="cat-sub">
            Órdenes recibidas del anunciante o agencia. De aquí se derivan las órdenes internas (OI). El listado muestra el estado raíz
            (1–5); el detalle de la OC muestra el sub-estado de cada OI hija.
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

      {filtroDescripcion && (
        <div
          style={{
            background: "var(--amber-bg)",
            color: "var(--amber-text)",
            padding: "6px 22px",
            fontSize: 12,
            borderBottom: "1px solid var(--amber-border, #FAC775)",
          }}
        >
          🔎 Filtro activo: {filtroDescripcion}{" "}
          <span
            style={{ cursor: "pointer", textDecoration: "underline" }}
            onClick={() => {
              setFiltro("todas");
              onQuitarFiltroInicial?.();
            }}
          >
            Quitar filtro
          </span>
        </div>
      )}

      <CatalogToolbar
        search={search}
        onSearch={setSearch}
        searchPlaceholder="Buscar folio, anunciante, no. de orden…"
        filterLabel="Estado"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as FiltroOrdenCliente);
          setSelectedId(null);
        }}
        count={`${items.length} de ${state.ordenesCliente.length}`}
      />

      <ListDetailLayout
        list={
          <table className="cat-table">
            <thead>
              <tr>
                <th style={{ width: "10%" }}>Folio</th>
                <th style={{ width: "9%" }}>Fecha</th>
                <th style={{ width: "15%" }}>Anunciante</th>
                <th style={{ width: "13%" }}>Agencia / Vendedor</th>
                <th style={{ width: "13%" }}>Producto / Marca</th>
                <th style={{ width: "11%" }}>Campaña</th>
                <th className="td-right" style={{ width: "9%" }}>
                  Total
                </th>
                <th className="td-center" style={{ width: "6%" }}>
                  OI
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
                const oeCount = oesDeOC(state.ordenesEstacion, oc.id).length;
                const { total } = totalesOC(oc);
                return (
                  <tr key={oc.id} className={selectedId === oc.id ? "sel" : ""} onClick={() => setSelectedId(oc.id)}>
                    <td>
                      <div className="td-mono">{oc.folio_orden}</div>
                      <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 1 }}>{oc.numero_orden_cliente}</div>
                    </td>
                    <td className="td-mono" style={{ fontSize: 11 }}>{oc.created_at}</td>
                    <td className="td-main">{anunciante ? anunciante.nombre_comercial : "—"}</td>
                    <td className="td-2">
                      <div style={{ fontSize: 12 }}>{agencia ? agencia.nombre_agencia : <span style={{ color: "var(--text3)" }}>Sin agencia</span>}</div>
                      <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 1 }}>{vendedor ? vendedor.nombre_vendedor : "—"}</div>
                    </td>
                    <td className="td-2">
                      <div style={{ fontSize: 12 }}>{marca ? marca.nombre_marca : "—"}</div>
                      <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 1 }}>{oc.producto}</div>
                    </td>
                    <td className="td-mono" style={{ fontSize: 11 }}>
                      {fmtRangoFechas(oc.fecha_inicio_campania, oc.fecha_fin_campania)}
                    </td>
                    <td className="td-right td-mono" style={{ fontWeight: 500 }}>
                      {fmtMonto(total, { sinDecimales: true })}
                    </td>
                    <td className="td-center td-2">{oeCount}</td>
                    <td className="td-center">
                      <RootBadge estatus={oc.estatus_orden} />
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={9} className="state-msg">
                    No hay órdenes para los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        }
        detail={
          selected ? (
            <OrdenClienteDetailPanel
              oc={selected}
              ordenesEstacion={state.ordenesEstacion}
              incidencias={state.incidencias}
              historialComisiones={state.historialComisiones}
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
            <DetailEmpty message="Selecciona una orden para ver sus datos y órdenes internas." />
          )
        }
      />
    </>
  );
}
