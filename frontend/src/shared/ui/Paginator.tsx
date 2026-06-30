/** Paginación POR PÁGINA (no scroll infinito). Envuelve el Paginator de PrimeReact
 * exponiendo una API por página (1-based), alineada con la respuesta `Page` del backend.
 */

import { Paginator as PrimePaginator, type PaginatorPageChangeEvent } from "primereact/paginator";

interface PaginatorProps {
  /** Página actual, 1-based. */
  page: number;
  size: number;
  total: number;
  onChange: (page: number, size: number) => void;
  rowsPerPageOptions?: number[];
}

export function Paginator({
  page,
  size,
  total,
  onChange,
  rowsPerPageOptions = [10, 20, 50, 100],
}: PaginatorProps) {
  const first = (page - 1) * size;

  const handle = (e: PaginatorPageChangeEvent) => {
    const nuevaPagina = Math.floor(e.first / e.rows) + 1;
    onChange(nuevaPagina, e.rows);
  };

  return (
    <PrimePaginator
      first={first}
      rows={size}
      totalRecords={total}
      rowsPerPageOptions={rowsPerPageOptions}
      onPageChange={handle}
    />
  );
}
