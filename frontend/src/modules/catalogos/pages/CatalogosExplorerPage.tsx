/** Pantalla contenedora del explorador de catálogos (F0-00).
 *
 * Arma el sidebar desde el `catalogRegistry` y muestra el catálogo activo. En F0-00
 * ningún catálogo tiene pantalla concreta todavía: se muestra un placeholder claro.
 * Desde F0-01, cuando una entrada del registry trae `render`, aquí se renderiza su
 * pantalla lista+detalle sin tocar este archivo.
 */

import { useMemo, useState } from "react";

import { useAfiliados } from "@/modules/catalogos/afiliado/hooks";
import { useAgencias } from "@/modules/catalogos/agencia/hooks";
import { useAnunciantes } from "@/modules/catalogos/anunciante/hooks";
import {
  buildSidebarGroups,
  catalogRegistry,
  type CatalogEntry,
} from "@/modules/catalogos/catalogRegistry";
import { usePlazas } from "@/modules/catalogos/plaza/hooks";
import { useTarifas } from "@/modules/catalogos/tarifa/hooks";
import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

const FASE_LABEL = "FASE 0 · CATÁLOGOS";

export function CatalogosExplorerPage() {
  // Conteos reales solo de los catálogos ya implementados (F0-01/F0-02): una consulta
  // ligera (size:1) por catálogo, reutilizando el `total` del listado paginado. Sus
  // mutaciones invalidan la key del catálogo y refrescan el contador. Los catálogos aún no
  // implementados (F0-03/04/05) no consultan nada y el Sidebar los muestra en 0.
  const plazaTotal = usePlazas().useList({ page: 1, size: 1 }).data?.total;
  const afiliadoTotal = useAfiliados().useList({ page: 1, size: 1 }).data?.total;
  const tarifaTotal = useTarifas().useList({ page: 1, size: 1 }).data?.total;
  const agenciaTotal = useAgencias().useList({ page: 1, size: 1 }).data?.total;
  const anuncianteTotal = useAnunciantes().useList({ page: 1, size: 1 }).data?.total;

  const groups = useMemo(() => {
    const counts: Record<string, number | undefined> = {
      plaza: plazaTotal,
      afiliado: afiliadoTotal,
      tarifa: tarifaTotal,
      agencia: agenciaTotal,
      anunciante: anuncianteTotal,
    };
    return buildSidebarGroups(
      catalogRegistry.map((e) =>
        counts[e.key] !== undefined ? { ...e, count: counts[e.key] } : e,
      ),
    );
  }, [plazaTotal, afiliadoTotal, tarifaTotal, agenciaTotal, anuncianteTotal]);

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
