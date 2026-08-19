/** Shell de la fase F1 — Órdenes: sidebar fija (flujo principal + vistas operativas, con
 * contadores en vivo) + área principal que conmuta entre las 4 pantallas de la fase
 * (Órdenes del cliente, Órdenes internas, Verificaciones, Incidencias).
 *
 * A diferencia de `CatalogosExplorerPage` (F0), aquí NO hay un registry dinámico de
 * catálogos: F1 tiene un conjunto fijo de 4 pantallas de flujo + 4 vistas operativas
 * (filtros hacia Órdenes internas/del cliente), así que se listan directamente.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { currentUser } from "@/shared/lib/currentUser";
import type { SidebarGroup } from "@/shared/ui";
import { ExplorerLayout } from "@/shared/ui";

import { cargarEstadoReal } from "../adapters/cargarEstadoReal";
import { IncidenciaListPage } from "../incidencia/pages/IncidenciaListPage";
import { OrdenClienteListPage } from "../ordenCliente/pages/OrdenClienteListPage";
import { OrdenEstacionListPage, type FiltroOI } from "../ordenEstacion/pages/OrdenEstacionListPage";
import { OrdenesProvider, useOrdenes, type OrdenesState } from "../state/OrdenesContext";
import { calcularContadores, type FiltroOrdenCliente } from "../state/selectors";
import { VerificacionListPage } from "../verificacion/pages/VerificacionListPage";

const FASE_LABEL = "ÓRDENES";

type ViewKey = "orden_cliente" | "orden_estacion" | "verificacion" | "incidencia";

interface Nav {
  view: ViewKey;
  filtroOC?: FiltroOrdenCliente;
  ocSeleccionada?: string;
  filtroOI?: FiltroOI;
  oeSeleccionada?: string;
  ocParaNuevaOE?: string;
  /** OI preseleccionada al entrar a Verificaciones (llegando desde "Ver verificación →"). */
  verSeleccionada?: string;
  /** Incidencia preseleccionada al entrar a Incidencias (llegando desde un badge "N inc."). */
  incSeleccionada?: string;
}

function OrdenesExplorerContent() {
  const { state } = useOrdenes();
  const [nav, setNav] = useState<Nav>({ view: "orden_cliente" });

  const counts = useMemo(
    () => calcularContadores(state.ordenesCliente, state.ordenesEstacion, state.incidencias.length),
    [state.ordenesCliente, state.ordenesEstacion, state.incidencias.length],
  );

  const groups: SidebarGroup[] = [
    {
      title: "Flujo principal",
      items: [
        { key: "orden_cliente", label: "Órdenes del cliente", count: counts.ordenesCliente },
        { key: "orden_estacion", label: "Órdenes internas", count: counts.ordenesEstacion },
        { key: "verificacion", label: "Verificaciones", count: counts.verificaciones },
        { key: "incidencia", label: "Incidencias", count: counts.incidencias },
      ],
    },
    {
      title: "Vistas operativas",
      items: [
        { key: "op_pendientes_asignar", label: "Pendientes de asignar", count: counts.pendientesAsignar, urgent: true },
        { key: "op_pendientes_verificar", label: "Pendientes de verificar", count: counts.pendientesVerificar },
        { key: "op_listas_cerrar", label: "Listas para cerrar", count: counts.listasCerrar },
        { key: "op_listas_facturar", label: "Listas para facturar", count: counts.listasFacturar },
      ],
    },
  ];

  const onSelectSidebar = (key: string) => {
    switch (key) {
      case "orden_cliente":
      case "orden_estacion":
      case "verificacion":
      case "incidencia":
        setNav({ view: key });
        return;
      case "op_pendientes_asignar":
        setNav({ view: "orden_estacion", filtroOI: "asignada_afiliado" });
        return;
      case "op_pendientes_verificar":
        setNav({ view: "orden_estacion", filtroOI: "programados_conciliados" });
        return;
      case "op_listas_cerrar":
        setNav({ view: "orden_cliente", filtroOC: "listas_cerrar" });
        return;
      case "op_listas_facturar":
        setNav({ view: "orden_cliente", filtroOC: "listas_facturar" });
        return;
    }
  };

  let content: ReactNode;
  if (nav.view === "orden_cliente") {
    content = (
      <OrdenClienteListPage
        key={`${nav.filtroOC ?? "sin_filtro"}-${nav.ocSeleccionada ?? ""}`}
        filtroInicial={nav.filtroOC}
        ocIdPreseleccionada={nav.ocSeleccionada}
        onQuitarFiltroInicial={() => setNav({ view: "orden_cliente" })}
        onSeleccionarOE={(oeId) => setNav({ view: "orden_estacion", oeSeleccionada: oeId })}
        onAsignarEstaciones={(ocId) => setNav({ view: "orden_estacion", ocParaNuevaOE: ocId })}
      />
    );
  } else if (nav.view === "orden_estacion") {
    content = (
      <OrdenEstacionListPage
        key={`${nav.filtroOI ?? "sin_filtro"}-${nav.oeSeleccionada ?? ""}-${nav.ocParaNuevaOE ?? ""}`}
        filtroInicial={nav.filtroOI}
        oeIdPreseleccionada={nav.oeSeleccionada}
        ocIdParaNueva={nav.ocParaNuevaOE}
        onVerOC={(ocId) => setNav({ view: "orden_cliente", ocSeleccionada: ocId })}
        onVerVerificacion={(oeId) => setNav({ view: "verificacion", verSeleccionada: oeId })}
      />
    );
  } else if (nav.view === "verificacion") {
    content = (
      <VerificacionListPage
        key={nav.verSeleccionada ?? ""}
        oeIdPreseleccionada={nav.verSeleccionada}
        onVerOE={(oeId) => setNav({ view: "orden_estacion", oeSeleccionada: oeId })}
      />
    );
  } else {
    content = (
      <IncidenciaListPage
        key={nav.incSeleccionada ?? ""}
        incIdPreseleccionada={nav.incSeleccionada}
        onVerOE={(oeId) => setNav({ view: "orden_estacion", oeSeleccionada: oeId })}
        onVerVerificacion={(oeId) => setNav({ view: "verificacion", verSeleccionada: oeId })}
      />
    );
  }

  return (
    <ExplorerLayout
      faseLabel={FASE_LABEL}
      user={currentUser}
      groups={groups}
      activeKey={nav.view}
      onSelect={onSelectSidebar}
      rootClassName="phase-f1"
    >
      {content}
    </ExplorerLayout>
  );
}

/** El estado inicial viene del backend real — hay que resolverlo ANTES de montar
 * `OrdenesProvider` (su `useReducer` es síncrono, no puede esperar una promesa).
 * Mientras carga o si falla, se muestra un estado explícito (frontend/CLAUDE.md:
 * "manejo explícito de carga/error/vacío en cada pantalla"). */
function OrdenesExplorerApiGate() {
  const [estado, setEstado] = useState<
    { tipo: "cargando" } | { tipo: "error"; mensaje: string } | { tipo: "listo"; datos: OrdenesState }
  >({ tipo: "cargando" });

  useEffect(() => {
    let cancelado = false;
    cargarEstadoReal()
      .then((datos) => {
        if (!cancelado) setEstado({ tipo: "listo", datos });
      })
      .catch((err: unknown) => {
        if (!cancelado) {
          setEstado({
            tipo: "error",
            mensaje: err instanceof Error ? err.message : "Error desconocido al cargar Órdenes.",
          });
        }
      });
    return () => {
      cancelado = true;
    };
  }, []);

  if (estado.tipo === "cargando") {
    return (
      <div className="app-shell phase-f1">
        <div className="state-msg">Cargando Órdenes desde el backend…</div>
      </div>
    );
  }
  if (estado.tipo === "error") {
    return (
      <div className="app-shell phase-f1">
        <div className="state-msg">No se pudo cargar Órdenes: {estado.mensaje}</div>
      </div>
    );
  }
  return (
    <OrdenesProvider initialState={estado.datos}>
      <OrdenesExplorerContent />
    </OrdenesProvider>
  );
}

export function OrdenesExplorerPage() {
  return <OrdenesExplorerApiGate />;
}
