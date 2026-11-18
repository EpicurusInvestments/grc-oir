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

const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

// ADR-272 (petición del usuario, barrido global): fechas de solo lectura en
// "DD-MMM-AA" (p.ej. "13-feb-26"), no mes/día/año ni ISO crudo — mismo criterio que
// F2/F3. Los campos de CAPTURA (`DateInput`) se quedan en dd/mm/aa numérico.
export function fmtFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Se parte el ISO en vez de usar `new Date(iso)`: una fecha pura se interpreta como
  // UTC y en México se mostraría el día anterior.
  const [anio, mes, dia] = iso.slice(0, 10).split("-");
  if (!anio || !mes || !dia) return "—";
  return `${dia}-${MESES_ABREV[Number(mes) - 1]}-${anio.slice(-2)}`;
}
