/** Formateadores del módulo Contrato. Los montos/porcentajes llegan como string (Decimal). */

/** Monto en MXN, siempre a 2 decimales SIN redondear (o "—" si es nulo) — mismo
 * criterio que el resto del sistema, `modules/facturacion/format.ts`: se corta el
 * STRING antes de convertir a número, así que no depende del redondeo de
 * `toLocaleString`. */
export function fmtMonto(v: string | null | undefined): string {
  if (v == null || v === "") return "—";
  const idxPunto = v.indexOf(".");
  const truncado = idxPunto === -1 ? v : v.slice(0, idxPunto + 3);
  const n = Number(truncado);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Porcentaje (o "—" si es nulo). */
export function fmtPct(v: string | null | undefined): string {
  return v == null || v === "" ? "—" : `${v}%`;
}
