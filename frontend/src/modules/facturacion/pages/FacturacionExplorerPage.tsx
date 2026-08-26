/** Explorador de la fase Facturación (F2) — mismo patrón que Catálogos y Seguridad.
 *
 * `rootClassName="phase-f2"` tiñe la pantalla con el azul de la fase (convención de la
 * propuesta: F0 morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo) sin duplicar
 * reglas de CSS ni afectar a las demás fases.
 */

import { useState } from "react";

import { currentUser } from "@/shared/lib/currentUser";
import { ExplorerLayout } from "@/shared/ui";

import {
  buildFacturacionGroups,
  facturacionRegistry,
  type FacturacionEntry,
} from "../facturacionRegistry";
import { useOrdenesPorFacturar } from "../hooks";

const FASE_LABEL = "FACTURACIÓN";

export function FacturacionExplorerPage() {
  const [activeKey, setActiveKey] = useState<string | null>(facturacionRegistry[0]?.key ?? null);

  const entry: FacturacionEntry | undefined = facturacionRegistry.find((e) => e.key === activeKey);

  // Solo se pide el TOTAL: `size: 1` evita traer filas de una lista que aquí no se pinta.
  // Su clave comparte PREFIJO con la de la bandeja, así que al crear una factura (que
  // invalida ese prefijo) el contador baja solo.
  const porFacturar = useOrdenesPorFacturar({ page: 1, size: 1 });
  const contadores = {
    listas_para_facturar: { count: porFacturar.data?.total ?? 0, urgent: true },
  };

  return (
    <ExplorerLayout
      faseLabel={FASE_LABEL}
      user={currentUser}
      groups={buildFacturacionGroups(facturacionRegistry, contadores)}
      activeKey={activeKey}
      onSelect={setActiveKey}
      rootClassName="phase-f2"
    >
      {entry?.render ? (
        entry.render()
      ) : (
        <>
          <div className="cat-header">
            <div>
              <div className="cat-title">{entry?.label ?? "Facturación"}</div>
              <div className="cat-sub">Sección de la Fase 2.</div>
            </div>
          </div>
          <div className="state-msg">«{entry?.label ?? "—"}» aún no está implementado.</div>
        </>
      )}
    </ExplorerLayout>
  );
}
