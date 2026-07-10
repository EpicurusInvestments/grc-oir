/** Utilidades de formato/derivación de la UI de tarifas (moneda MXN, fecha, vigencia). */

const MXN = new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" });

/** Formatea un monto (string Decimal o número) como moneda MXN; "—" si no es número. */
export function fmtMoneda(valor: string | number): string {
  const n = typeof valor === "string" ? Number(valor) : valor;
  return Number.isFinite(n) ? MXN.format(n) : "—";
}

/** Fecha ISO `YYYY-MM-DD` → `dd/mm/yyyy` sin construir Date (evita corrimientos de zona). */
export function fmtFecha(iso: string): string {
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

/** Preview de la tarifa neta = bruta * (1 - descuento/100). NaN si algún dato no es número.
 *  El valor OFICIAL lo calcula y persiste el backend; esto es solo para mostrar en el form. */
export function calcularNetaPreview(
  bruta: string | number,
  descuentoPct: string | number,
): number {
  const b = Number(bruta);
  const d = Number(descuentoPct);
  if (!Number.isFinite(b) || !Number.isFinite(d)) return NaN;
  return b * (1 - d / 100);
}

/** Derivado: una tarifa está "vigente" si `vigencia_hasta` no es anterior a hoy.
 *  Comparación lexicográfica de ISO `YYYY-MM-DD` (equivale a comparar fechas). */
export function esVigente(vigenciaHasta: string): boolean {
  const hoy = new Date().toISOString().slice(0, 10);
  return vigenciaHasta >= hoy;
}
