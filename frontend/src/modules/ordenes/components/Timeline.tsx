/** Stepper de 5 estados raíz del ciclo de vida de una OrdenCliente, con el sub-estado
 * vigente (si lo hay) debajo del paso activo. Es el elemento visual más importante de la
 * demo: cuando `estatus_orden` es `cancelada` no hay raíz activa, así que se muestra un
 * aviso en su lugar en vez de un stepper con nada resaltado.
 */

import { ROOT_LABEL, rootState, STATUS_LABELS } from "../constants";
import type { EstadoOC } from "../types";

const ROOTS = [1, 2, 3, 4, 5] as const;

export function Timeline({ estatus }: { estatus: EstadoOC }) {
  if (estatus === "cancelada") {
    return (
      <div
        style={{
          background: "var(--gray-bg)",
          color: "var(--gray-text)",
          borderRadius: "var(--r)",
          padding: "10px 13px",
          fontSize: 12,
          marginBottom: 14,
          fontWeight: 500,
        }}
      >
        ✕ Orden cancelada — el ciclo se interrumpió antes de completarse.
      </div>
    );
  }

  const root = rootState(estatus) ?? 0;
  const sub = STATUS_LABELS[estatus];
  // Solo las raíces 1 y 4 tienen sub-estado propio (1.1/1.2, 4.1/4.2); la 2 (Orden interna)
  // guarda sus sub-estados en la OrdenEstacion, no aquí.
  const subLabel = root === 1 || root === 4 ? sub : "";

  return (
    <div className="timeline">
      {ROOTS.map((r) => {
        const cls = r < root ? "done" : r === root ? "current" : "";
        return (
          <div className={`tl-step ${cls}`} key={r}>
            <div className="tl-dot">{r < root ? "✓" : r}</div>
            <div className="tl-lbl">
              {ROOT_LABEL[r]}
              {r === root && subLabel && (
                <div style={{ fontSize: 9, color: "var(--text3)", fontWeight: 500, marginTop: 1 }}>{subLabel}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
