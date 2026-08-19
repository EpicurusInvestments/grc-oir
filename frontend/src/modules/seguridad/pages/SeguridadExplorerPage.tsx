/** Explorador de la fase Seguridad (F5) — mismo patrón que el de Catálogos.
 *
 * `rootClassName="phase-f5"` tiñe la pantalla completa con el rojo de marca (botones, foco
 * de campos, tag de fase, item activo del sidebar) sin duplicar una sola regla de CSS ni
 * afectar a las demás fases. Es el mismo mecanismo que usa F1 con `phase-f5`→`phase-f1`.
 */

import { useState } from "react";

import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

import {
  buildSeguridadGroups,
  seguridadRegistry,
  type SeguridadEntry,
} from "../seguridadRegistry";

const FASE_LABEL = "SEGURIDAD";

export function SeguridadExplorerPage() {
  const [activeKey, setActiveKey] = useState<string | null>(
    seguridadRegistry[0]?.key ?? null,
  );

  const entry: SeguridadEntry | undefined = seguridadRegistry.find((e) => e.key === activeKey);

  return (
    <ExplorerLayout
      faseLabel={FASE_LABEL}
      user={currentUser}
      groups={buildSeguridadGroups(seguridadRegistry)}
      activeKey={activeKey}
      onSelect={setActiveKey}
      rootClassName="phase-f5"
    >
      {entry?.render ? (
        entry.render()
      ) : (
        <>
          <div className="cat-header">
            <div>
              <div className="cat-title">{entry?.label ?? "Seguridad"}</div>
              <div className="cat-sub">
                Sección de la Fase 5. F5-00 adelantó la autenticación y la gestión de
                usuarios; el resto llega con la fase completa.
              </div>
            </div>
          </div>
          <div className="state-msg">
            «{entry?.label ?? "—"}» aún no está implementado. Llega con F5 pleno, sobre esta
            misma base.
          </div>
        </>
      )}
    </ExplorerLayout>
  );
}
