/** Explorador de la fase Cobranza y Pagos (F3) — mismo patrón que Facturación (F2).
 *
 * `rootClassName="phase-f3"` tiñe la pantalla de ámbar (convención de la propuesta: F0
 * morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo).
 */

import { Fragment, useState } from "react";

import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

import { buildCobranzaGroups, cobranzaRegistry, type CobranzaEntry } from "../cobranzaRegistry";
import { useConteosCobranza } from "../hooks";

const FASE_LABEL = "COBRANZA Y PAGOS";
const URGENTES = new Set(["cobranzas_vencidas", "por_autorizar", "por_pagar", "sin_conciliar"]);

export function CobranzaExplorerPage() {
  const [activeKey, setActiveKey] = useState<string | null>(cobranzaRegistry[0]?.key ?? null);

  const entry: CobranzaEntry | undefined = cobranzaRegistry.find((e) => e.key === activeKey);

  // Las 4 "vistas operativas" van en rojo (`urgent`): son trabajo PENDIENTE, no
  // inventario — mismo criterio que "Listas para facturar" en F2.
  const totales = useConteosCobranza();
  const contadores = Object.fromEntries(
    Object.entries(totales).map(([clave, count]) => [clave, { count, urgent: URGENTES.has(clave) }]),
  );

  return (
    <ExplorerLayout
      faseLabel={FASE_LABEL}
      user={currentUser}
      groups={buildCobranzaGroups(cobranzaRegistry, contadores)}
      activeKey={activeKey}
      onSelect={setActiveKey}
      rootClassName="phase-f3"
    >
      {entry ? (
        // Fix (reportado por el usuario): "Requisiciones" y sus "vistas operativas" ("Por
        // autorizar"/"Por pagar") renderizan el MISMO componente (`RequisicionesPage`),
        // solo con `filtroInicial` distinto — mismo caso "Cobranza de facturas"/
        // "Cobranzas vencidas" con `CobranzaFacturasPage`. Sin una `key` que distinga la
        // sección activa, React no remonta al cambiar entre ellas (mismo tipo, misma
        // posición), así que el `useState(filtroInicial ?? "all")` interno — que solo
        // corre al MONTAR — se quedaba con el valor de la primera vez que se montó esa
        // instancia, ignorando el nuevo `filtroInicial`. `key={entry.key}` fuerza un
        // remonte limpio en cada cambio de sección.
        <Fragment key={entry.key}>{entry.render()}</Fragment>
      ) : (
        <>
          <div className="cat-header">
            <div>
              <div className="cat-title">Cobranza y Pagos</div>
              <div className="cat-sub">Sección de la Fase 3.</div>
            </div>
          </div>
          <div className="state-msg">Selecciona una sección del menú.</div>
        </>
      )}
    </ExplorerLayout>
  );
}
