/** Patrón lista + panel de detalle (~420px). La tabla a la izquierda; al seleccionar un
 * renglón, el detalle/edición a la derecha sin perder el contexto de la lista.
 */

import type { ReactNode } from "react";

interface ListDetailLayoutProps {
  list: ReactNode;
  detail: ReactNode;
}

export function ListDetailLayout({ list, detail }: ListDetailLayoutProps) {
  return (
    <div className="split">
      <div className="list-pane">{list}</div>
      <div className="detail-pane">{detail}</div>
    </div>
  );
}

/** Estado vacío del panel de detalle (cuando no hay selección). */
export function DetailEmpty({ message }: { message: string }) {
  return <div className="d-empty">{message}</div>;
}
