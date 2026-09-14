/** Patrón lista + panel de detalle (~420px). La tabla a la izquierda; al seleccionar un
 * renglón, el detalle/edición a la derecha sin perder el contexto de la lista.
 */

import type { CSSProperties, ReactNode } from "react";

interface ListDetailLayoutProps {
  list: ReactNode;
  detail: ReactNode;
  /** Ancho del panel de detalle, para el caso puntual donde el contenido (p.ej. un
   *  formulario con varios campos por renglón) no cabe cómodo en los ~420px por default.
   *  Opcional: sin esto, todas las pantallas se comportan exactamente igual que antes. */
  detailWidth?: string;
}

export function ListDetailLayout({ list, detail, detailWidth }: ListDetailLayoutProps) {
  return (
    <div className="split">
      <div className="list-pane">{list}</div>
      <div className="detail-pane" style={detailWidth ? ({ "--detail-width": detailWidth } as CSSProperties) : undefined}>
        {detail}
      </div>
    </div>
  );
}

/** Estado vacío del panel de detalle (cuando no hay selección). */
export function DetailEmpty({ message }: { message: string }) {
  return <div className="d-empty">{message}</div>;
}
