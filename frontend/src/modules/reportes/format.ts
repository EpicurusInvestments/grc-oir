/** Formato de presentación de F4.
 *
 * No se reutiliza `modules/cobranza/format.ts`/`modules/facturacion/format.ts` a
 * propósito: importar de otro módulo de negocio crea la dependencia directa que el
 * CLAUDE.md prohíbe (lo compartido va a `shared/`) — mismo criterio ya usado entre
 * F2 y F3.
 */

/** Formatea un monto decimal en string como moneda MXN, a 2 decimales sin redondear
 * (se corta el STRING antes de convertir a número, igual que F2/F3). */
export function fmtMoneda(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  let v = valor;
  const idxPunto = v.indexOf(".");
  if (idxPunto !== -1) v = v.slice(0, idxPunto + 3);
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  const texto = Math.abs(n).toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return n < 0 ? texto.replace("$", "$-") : texto;
}

/** Versión ABREVIADA de `fmtMoneda` ($5.65M, $310K) — para KPI, barras y la tabla de
 * histórico (mismo criterio que el mockup aprobado, `fmtK`): esas vistas necesitan un
 * vistazo rápido, no el centavo exacto (que sí importa en la tabla del P&L principal,
 * ahí se usa `fmtMoneda`). */
export function fmtMonedaCorta(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const n = Number(valor);
  if (Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  let texto: string;
  if (abs >= 1_000_000) texto = `$${(abs / 1_000_000).toFixed(2)}M`;
  else if (abs >= 1_000) texto = `$${(abs / 1_000).toFixed(0)}K`;
  else texto = `$${abs.toFixed(2)}`;
  return n < 0 ? `-${texto}` : texto;
}

export function fmtPorcentaje(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const n = Number(valor);
  return Number.isNaN(n) ? "—" : `${n.toLocaleString("es-MX", { minimumFractionDigits: 2 })} %`;
}

const MESES = [
  "enero", "febrero", "marzo", "abril", "mayo", "junio",
  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
];

const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** "2026-11" → "Noviembre 2026" (selector de mes, encabezado de la vista). */
export function fmtPeriodo(periodo: string): string {
  const [anio, mes] = periodo.split("-");
  const nombre = MESES[Number(mes) - 1];
  if (!nombre) return periodo;
  return `${nombre[0]!.toUpperCase()}${nombre.slice(1)} ${anio}`;
}

/** "2026-11" → "Nov 2026" (eje de la tabla de histórico, más compacto). */
export function fmtPeriodoCorto(periodo: string): string {
  const [anio, mes] = periodo.split("-");
  const nombre = MESES_ABREV[Number(mes) - 1];
  return nombre ? `${nombre[0]!.toUpperCase()}${nombre.slice(1)} ${anio}` : periodo;
}

/** Mes en curso en formato "YYYY-MM" — SOLO para comparar en la UI (el default real lo
 * decide el backend, en hora de México, ADR-261); aquí es simplemente la hora local del
 * navegador, suficiente para una comparación visual ("(en curso)"). */
export function mesEnCursoLocal(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}`;
}
