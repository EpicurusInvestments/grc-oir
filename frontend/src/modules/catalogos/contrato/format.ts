/** Formateadores del módulo Contrato. Los montos/porcentajes llegan como string (Decimal). */

/** Monto en MXN (o "—" si es nulo). */
export function fmtMonto(v: string | null | undefined, opts?: { full?: boolean }): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: opts?.full ? 2 : 0,
  });
}

/** Porcentaje (o "—" si es nulo). */
export function fmtPct(v: string | null | undefined): string {
  return v == null || v === "" ? "—" : `${v}%`;
}
