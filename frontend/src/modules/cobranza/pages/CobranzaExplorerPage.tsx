/** Explorador de la fase Cobranza y Pagos (F3) — mismo patrón que Facturación (F2).
 *
 * `rootClassName="phase-f3"` tiñe la pantalla de ámbar (convención de la propuesta: F0
 * morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo).
 */

import { Fragment, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

import { buildCobranzaGroups, cobranzaRegistry, type CobranzaEntry } from "../cobranzaRegistry";
import { useConteosCobranza } from "../hooks";

const FASE_LABEL = "COBRANZA Y PAGOS";
const URGENTES = new Set(["cobranzas_vencidas", "por_autorizar", "por_pagar", "sin_conciliar"]);

export function CobranzaExplorerPage() {
  const [activeKey, setActiveKey] = useState<string | null>(cobranzaRegistry[0]?.key ?? null);

  // Bug corregido (reportado por el usuario, con captura): la liga "Ver en Cobranza de
  // facturas →" desde "Pagos recibidos" solo cambiaba la URL (`?cobranza_id=...`) sin
  // mover la pantalla — las secciones de esta fase NO son rutas reales, son un
  // `activeKey` interno que la barra lateral controla, así que navegar DENTRO de la
  // misma ruta "/cobranza" no remonta este componente ni cambia ese estado. Cuando el
  // deep-link trae `factura_id`/`cobranza_id`, se fuerza la sección "Cobranza de
  // facturas" (la única que sabe leer esos parámetros, ver `CobranzaFacturasPage`).
  const [searchParams] = useSearchParams();
  const facturaIdParam = searchParams.get("factura_id");
  const cobranzaIdParam = searchParams.get("cobranza_id");
  useEffect(() => {
    if ((facturaIdParam || cobranzaIdParam) && activeKey !== "cobranza_factura") {
      setActiveKey("cobranza_factura");
    }
    // Solo reacciona cuando cambia el deep-link en sí, no en cada clic del menú —
    // si no, pisaría cualquier sección que el usuario elija después mientras el
    // parámetro siga en la URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facturaIdParam, cobranzaIdParam]);

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
