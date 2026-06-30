/** Pantalla contenedora del explorador de catálogos (F0-00).
 *
 * Arma el sidebar desde el `catalogRegistry` y muestra el catálogo activo. En F0-00
 * ningún catálogo tiene pantalla concreta todavía: se muestra un placeholder claro.
 * Desde F0-01, cuando una entrada del registry trae `render`, aquí se renderiza su
 * pantalla lista+detalle sin tocar este archivo.
 */

import { useMemo, useState } from "react";

import {
  buildSidebarGroups,
  catalogRegistry,
  type CatalogEntry,
} from "@/modules/catalogos/catalogRegistry";
import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

const FASE_LABEL = "FASE 0 · CATÁLOGOS";

export function CatalogosExplorerPage() {
  const groups = useMemo(() => buildSidebarGroups(catalogRegistry), []);
  const [activeKey, setActiveKey] = useState<string | null>(catalogRegistry[0]?.key ?? null);

  const entry: CatalogEntry | undefined = catalogRegistry.find((e) => e.key === activeKey);

  return (
    <ExplorerLayout
      faseLabel={FASE_LABEL}
      user={currentUser}
      groups={groups}
      activeKey={activeKey}
      onSelect={setActiveKey}
    >
      {entry?.render ? (
        entry.render()
      ) : (
        <>
          <div className="cat-header">
            <div>
              <div className="cat-title">{entry?.label ?? "Catálogos"}</div>
              <div className="cat-sub">
                Explorador de catálogos de la Fase 0. Cada catálogo se habilitará en su
                módulo (F0-01 a F0-05) sobre esta misma base.
              </div>
            </div>
          </div>
          <div className="state-msg">
            Catálogo «{entry?.label ?? "—"}» aún no implementado. Llega en un módulo
            posterior de F0 (F0-01+) reutilizando el patrón lista + detalle.
          </div>
        </>
      )}
    </ExplorerLayout>
  );
}
