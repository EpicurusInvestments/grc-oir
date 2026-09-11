/** Formateadores de la demo F1. A diferencia de `catalogos/contrato/format.ts` (donde los
 * montos llegan como string por venir de un Decimal del backend), aquí los mocks son
 * `number` puro en memoria: no hay backend que serialice.
 */

/** Monto en MXN, formato `$1,234,567.89` (o "—" si es nulo).
 *
 * `truncar`: corta a 2 decimales SIN redondear (p.ej. $1,234.567 → $1,234.56, no
 * $1,234.57) — para columnas donde el valor puede traer ruido de punto flotante
 * (`oiImporte`/`totalesOC` no redondean internamente, ver `state/selectors.ts`) y no se
 * quiere que el redondeo de `toLocaleString` invente un centavo que no está ahí. */
export function fmtMonto(v: number | null | undefined, opts?: { sinDecimales?: boolean; truncar?: boolean }): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const valor = opts?.truncar ? Math.trunc(v * 100) / 100 : v;
  return valor.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: opts?.sinDecimales ? 0 : 2,
    minimumFractionDigits: opts?.sinDecimales ? 0 : 2,
  });
}

/** Porcentaje (o "—" si es nulo). Sin decimales de sobra: 4 → "4%", 4.5 → "4.5%". */
export function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${Number.isInteger(v) ? v : v.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}%`;
}

const DIA_SEMANA = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"];

/** Día de la semana de una fecha ISO `YYYY-MM-DD`, calculado en UTC para evitar shift de huso. */
export function diaDeSemana(fechaIso: string): string {
  if (!fechaIso) return "—";
  const [y, m, d] = fechaIso.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return DIA_SEMANA[dt.getUTCDay()];
}

/** "2025-05-01 → 2025-05-31 (31 días)" o "—" si falta alguna fecha. */
export function fmtRangoFechas(inicio: string, fin: string): string {
  if (!inicio || !fin) return "—";
  const dias = Math.floor((new Date(fin).getTime() - new Date(inicio).getTime()) / 86_400_000) + 1;
  return `${inicio} → ${fin} (${dias} días)`;
}

export function oGuion(v: string | null | undefined): string {
  return v && v.trim() ? v : "—";
}
