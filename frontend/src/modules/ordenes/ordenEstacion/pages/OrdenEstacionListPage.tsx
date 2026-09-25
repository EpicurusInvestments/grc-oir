/** Pantalla "Órdenes de Transmisión": lista + panel de detalle, con filtro por sub-estado y
 * buscador. El alta (Tanda 3) abre a pantalla completa, igual que en Órdenes de Servicio.
 */

import { useMemo, useState } from "react";

import { CatalogToolbar, ConfirmDialog, DetailEmpty, ListDetailLayout } from "@/shared/ui";

import { EstadoOIBadge } from "../../components/EstadoBadge";
import { fmtMonto } from "../../format";
import { findAfiliado, findEstacion, findPlaza } from "../../state/catalogosCache";
import { useOrdenes } from "../../state/OrdenesContext";
import { oiImporte, oiPeriodoTexto, oiTotalSpots } from "../../state/selectors";
import type { EstadoOI, OrdenEstacion, OrdenEstacionInput, PeriodoTransmisionRow } from "../../types";
import { OrdenEstacionDetailPanel } from "../components/OrdenEstacionDetailPanel";
import { OrdenEstacionForm } from "../components/OrdenEstacionForm";
import { RealesForm } from "../components/RealesForm";

export type FiltroOI = "todas" | EstadoOI;

const FILTROS: { key: FiltroOI; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "asignada_afiliado", label: "2.1 Asignadas" },
  { key: "programados_conciliados", label: "2.2 Programados" },
  { key: "reales_conciliados", label: "2.3 Reales" },
];

type Modo = "view" | "new" | "edit" | "reales";

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
  const { state, crearOE, actualizarOE, avanzarAReales } = useOrdenes();
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
  // La OC a la que se le está asignando estación en el alta — arranca en la que llegó
  // fija por prop; si el usuario la elige suelta (sin `ocIdParaNueva`), se recuerda aquí
  // después del primer "Guardar" para que "generar otra" (abajo) siga sobre la misma OC.
  const [ocParaNuevaActual, setOcParaNuevaActual] = useState<string | undefined>(ocIdParaNueva);
  // ADR-116: tras crear una OE, en vez de pasar directo a modo edición (ADR-103, que ya
  // no hace falta desde que ADR-109 permite subir material DURANTE el alta), se pregunta
  // si se quiere capturar otra — la OE recién creada se guarda aquí mientras se decide.
  const [oeReciente, setOeReciente] = useState<OrdenEstacion | null>(null);
  // Cambia en cada "Sí, generar otra" para forzar que `<OrdenEstacionForm>` se remonte en
  // blanco (si se reusara la misma key, se quedaría con los datos de la OE anterior).
  const [intentoNuevo, setIntentoNuevo] = useState(0);

  const items = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtrados = state.ordenesEstacion.filter((oe) => {
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
    // Más reciente primero: para que una OI recién dada de alta aparezca al principio.
    return [...filtrados].sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [state.ordenesEstacion, state.ordenesCliente, filtro, search]);

  const selected = selectedId ? (state.ordenesEstacion.find((o) => o.id === selectedId) ?? null) : null;

  const onGuardar = async (ocId: string, input: OrdenEstacionInput) => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      if (modo === "edit" && selected) {
        const actualizada = await actualizarOE(selected.id, input);
        setSelectedId(actualizada.id);
        setModo("view");
        return actualizada;
      } else {
        const nueva = await crearOE(ocId, input);
        // ADR-116: ya no se pasa directo a modo edición (ADR-103) — desde ADR-109 el
        // material se sube DURANTE el alta, así que ese paso extra ya no hace falta.
        // En su lugar se pregunta si se quiere capturar otra OE para la misma OC.
        setOcParaNuevaActual(ocId);
        setOeReciente(nueva);
        return nueva;
      }
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "No se pudo guardar la Orden de Transmisión.");
      return undefined;
    } finally {
      setSubmitting(false);
    }
  };

  if (modo === "new" || (modo === "edit" && selected)) {
    return (
      <>
        <OrdenEstacionForm
          // El estado local del formulario (periodo, estación, audios, etc.) se inicializa
          // desde `oe` solo UNA vez, al montar (`useState(oe?.x ?? ...)`). Sin esta `key`,
          // React no lo remonta al cambiar de identidad lógica — se quedaría mostrando
          // datos viejos. En "edit" cambia con el id de la OE (ADR-113); en "new" cambia
          // con `intentoNuevo`, que sube en cada "Sí, generar otra" (ADR-116) para que el
          // siguiente formulario nazca en blanco, no con los datos de la OE anterior.
          key={modo === "edit" ? (selected?.id ?? "edit") : `new-${intentoNuevo}`}
          ocIdFijo={modo === "edit" ? undefined : ocParaNuevaActual}
          oe={modo === "edit" ? (selected ?? undefined) : undefined}
          submitError={submitError}
          submitting={submitting}
          onGuardar={onGuardar}
          onCancelar={(ocId) => {
            setSubmitError(null);
            if (modo === "new") {
              // ADR-116 (petición del usuario): cancelar el alta regresa a "Órdenes de
              // Servicio" — a la OC elegida si ya se había seleccionado una, o a la lista
              // suelta si el usuario canceló antes de elegir ninguna.
              if (ocId) onVerOC(ocId);
              else setModo("view");
              return;
            }
            setModo("view");
          }}
        />
        {/* ADR-116: se pregunta DESPUÉS de guardar (no antes) — "Sí" limpia el formulario
            para la siguiente OE de la misma OC; "No" va a la lista con la recién creada
            arriba (orden ya la antepone, ver REEMPLAZAR_OE en OrdenesContext.tsx). Nunca
            aparece en edición: ahí "Guardar" solo guarda, sin preguntar nada más. */}
        <ConfirmDialog
          visible={oeReciente !== null}
          title="Orden de Transmisión guardada"
          message="¿Deseas generar otra Orden de Transmisión para esta misma Orden de Servicio?"
          confirmLabel="Sí, generar otra"
          cancelLabel="No, ir a la lista"
          onConfirm={() => {
            setOeReciente(null);
            setIntentoNuevo((n) => n + 1);
          }}
          onCancel={() => {
            if (oeReciente) setSelectedId(oeReciente.id);
            setOeReciente(null);
            setModo("view");
          }}
        />
      </>
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
            setSubmitError(e instanceof Error ? e.message : "No se pudo avanzar la Orden de Transmisión.");
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
          <div className="cat-title">Órdenes de Transmisión</div>
          <div className="cat-sub">
            Derivación por estación de una Orden de Servicio. El sub-estado (2.1/2.2/2.3) vive aquí; el estado raíz de la orden solo refleja
            que existe al menos una.
          </div>
        </div>
        <button
          type="button"
          className="btn btn-phase"
          onClick={() => {
            setSubmitError(null);
            // Sesión nueva y suelta: no debe arrastrar la OC de una sesión anterior de
            // "generar otra" (ADR-116) si el usuario ya había dicho que no quería más.
            setOcParaNuevaActual(ocIdParaNueva);
            setModo("new");
          }}
        >
          + Nueva Orden de Transmisión
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
                <th style={{ width: "11%" }}>Folio</th>
                <th style={{ width: "8%" }}>Fecha</th>
                <th style={{ width: "10%" }}>OC de origen</th>
                <th style={{ width: "14%" }}>Estación</th>
                <th style={{ width: "8%" }}>Plaza</th>
                <th style={{ width: "13%" }}>Afiliado</th>
                <th style={{ width: "12%" }}>Periodo</th>
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
                      {oe.created_at}
                    </td>
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
                      {fmtMonto(oiImporte(oe))}
                    </td>
                    <td className="td-center">
                      <EstadoOIBadge estatus={oe.estatus} />
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={10} className="state-msg">
                    No hay Órdenes de Transmisión para los filtros seleccionados.
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
              onEditar={() => {
                setSubmitError(null);
                setModo("edit");
              }}
              onCapturarReales={() => {
                setSubmitError(null);
                setModo("reales");
              }}
              onVerVerificacion={() => onVerVerificacion(selected.id)}
            />
          ) : (
            <DetailEmpty message="Selecciona una Orden de Transmisión para ver su detalle." />
          )
        }
      />
    </>
  );
}
