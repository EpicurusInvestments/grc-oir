/** Badges de estado de la demo F1 — reutilizan `.badge .b-*` de theme.css (no clases
 * dedicadas por estado, a diferencia del prototipo aprobado; mismo patrón que
 * `ESTADO_BADGE` en `catalogos/contrato/types.ts`).
 */

import { ESTADO_OC_BADGE_CLASS, ESTADO_OI_BADGE_CLASS, ROOT_LABEL, rootBadgeClass, rootState, STATUS_LABELS } from "../constants";
import type { EstadoOC, EstadoOI } from "../types";

/** Badge del estado RAÍZ (1–5) de una OC, para la columna de la lista. */
export function RootBadge({ estatus }: { estatus: EstadoOC }) {
  const root = rootState(estatus);
  const label = root ? `${root} · ${ROOT_LABEL[root]}` : "Cancelada";
  return (
    <span className={`badge ${rootBadgeClass(root)}`} title={STATUS_LABELS[estatus]}>
      {label}
    </span>
  );
}

/** Badge del sub-estado completo de una OC (p.ej. "1.1 ODC sin Vo.Bo."). */
export function EstadoOCBadge({ estatus }: { estatus: EstadoOC }) {
  return <span className={`badge ${ESTADO_OC_BADGE_CLASS[estatus]}`}>{STATUS_LABELS[estatus]}</span>;
}

/** Badge del sub-estado de una OrdenEstacion (2.1 / 2.2 / 2.3). */
export function EstadoOIBadge({ estatus }: { estatus: EstadoOI }) {
  return <span className={`badge ${ESTADO_OI_BADGE_CLASS[estatus]}`}>{STATUS_LABELS[estatus]}</span>;
}
