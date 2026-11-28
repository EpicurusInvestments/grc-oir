/** Explorador de la fase Reportes (F4) — mismo patrón que Facturación/Cobranza.
 *
 * `rootClassName="phase-f4"` tiñe la pantalla de gris (convención de la propuesta: F0
 * morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo).
 *
 * A diferencia de F2/F3, las entradas del menú se filtran por `area` (ver
 * `reportesRegistry.entradasPermitidas`): un área sin ninguna vista permitida ve un
 * estado vacío explícito, no una pantalla rota ni un menú fantasma.
 */

import { Fragment, useState } from "react";

import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

import { buildReportesGroups, entradasPermitidas, type ReportesEntry } from "../reportesRegistry";

const FASE_LABEL = "REPORTES";

export function ReportesExplorerPage() {
  const entradas = entradasPermitidas(currentUser.area);
  const [activeKey, setActiveKey] = useState<string | null>(entradas[0]?.key ?? null);
  const entry: ReportesEntry | undefined = entradas.find((e) => e.key === activeKey);

  return (
    <ExplorerLayout
      faseLabel={FASE_LABEL}
      user={currentUser}
      groups={buildReportesGroups(entradas)}
      activeKey={activeKey}
      onSelect={setActiveKey}
      rootClassName="phase-f4"
    >
      {entradas.length === 0 ? (
        <>
          <div className="cat-header">
            <div>
              <div className="cat-title">Reportes</div>
              <div className="cat-sub">Sección de la Fase 4.</div>
            </div>
          </div>
          <div className="state-msg">
            Tu área ({currentUser.area || "—"}) no tiene acceso a ningún reporte todavía.
          </div>
        </>
      ) : entry ? (
        <Fragment key={entry.key}>{entry.render()}</Fragment>
      ) : (
        <>
          <div className="cat-header">
            <div>
              <div className="cat-title">Reportes</div>
              <div className="cat-sub">Sección de la Fase 4.</div>
            </div>
          </div>
          <div className="state-msg">Selecciona una sección del menú.</div>
        </>
      )}
    </ExplorerLayout>
  );
}
