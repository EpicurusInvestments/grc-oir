/** Formato de presentación de F2.
 *
 * No se reutiliza `modules/ordenes/format.ts` a propósito: importar de otro módulo de
 * negocio crea la dependencia directa que el CLAUDE.md prohíbe (lo compartido va a
 * `shared/`), y además aquellos helpers reciben `number` mientras que los montos de F2
 * llegan como STRING decimal desde el backend.
 */

/** Formatea un monto decimal en string (p.ej. "11600.00") como moneda MXN, siempre a 2
 * decimales SIN redondear (p.ej. "1234.567" → $1,234.56, no $1,234.57) — se corta el
 * STRING antes de convertir a número, así que no depende de ningún redondeo de
 * `toLocaleString` ni de precisión de punto flotante.
 *
 * Notas de Crédito (petición del usuario): `total_factura`/`subtotal_factura`/
 * `iva_factura` pueden venir NEGATIVOS — mismo fix ya establecido en
 * `cobranza/format.ts` para `ajuste` (`Intl` antepone el signo de "menos" al símbolo de
 * moneda, "-$1,234.56"; aquí se arma el texto sobre el valor absoluto y se inserta el
 * "-" DESPUÉS del "$", "$-1,234.56"). No se importa de `cobranza` a propósito (ver
 * docstring de arriba del archivo) — se duplica la función pequeña, no se comparte. */
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

export function fmtPorcentaje(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const n = Number(valor);
  return Number.isNaN(n) ? "—" : `${n.toLocaleString("es-MX", { minimumFractionDigits: 2 })} %`;
}

const MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

// ADR-272 (petición del usuario, barrido global): en TODA la pantalla de Facturación
// (y solo aquí — módulos como `ordenes`/`cobranza` tienen su propio `fmtFecha`,
// deliberadamente independiente, ver docstring de arriba) las fechas de solo lectura
// se muestran "DD-MMM-AA" (p.ej. "13-feb-26"). Los campos donde SE CAPTURA la fecha
// (`DateInput`, ADR-271c) se quedan en dd/mm/aa numérico — ver su propio docstring.
export function fmtFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Se parte el ISO en vez de usar `new Date(iso)`: una fecha pura ("2026-02-01") se
  // interpreta como UTC y en México se mostraría el día anterior.
  const [anio, mes, dia] = iso.slice(0, 10).split("-");
  if (!anio || !mes || !dia) return "—";
  return `${dia}-${MESES_ABREV[Number(mes) - 1]}-${anio.slice(-2)}`;
}

// ADR-278 (petición del usuario, con captura): mismo criterio que `ordenes/format.ts`
// (ADR-275) — el folio GUARDADO no cambia, esto es solo formato de DESPLIEGUE: quita
// los ceros a la izquierda del último segmento numérico ("OS-2026-11-000061" →
// "OS-2026-11-61"). No se reutiliza el de `ordenes` a propósito (ver docstring de
// arriba del archivo).
export function fmtFolio(folio: string | null | undefined): string {
  if (!folio) return "—";
  const partes = folio.split("-");
  const ultima = partes[partes.length - 1];
  const m = ultima.match(/^(\d+)([A-Za-z]*)$/);
  if (!m) return folio;
  partes[partes.length - 1] = String(Number(m[1])) + m[2];
  return partes.join("-");
}

export function oGuion(valor: string | null | undefined): string {
  return valor && valor.trim() ? valor : "—";
}

/** Clase de badge por estado, alineada a los colores ya definidos en `theme.css`. */
export function badgeEstadoFactura(estado: string): string {
  switch (estado) {
    case "preparada":
      return "b-gray";
    case "enviada_a_timbrado":
      return "b-amber";
    case "timbrada":
    case "entregada":
      return "b-blue";
    case "cobrada":
      // Badge OSCURO, no verde (mockup `Fase_2_-_Facturacion.html`: `.st-cobrada` es
      // `background:#181816; color:#fff`). `.b-dark` ya es exactamente esa combinación
      // —`var(--text)` vale #181816— y F1 ya lo usa para su propio estado `cobrada`
      // (`modules/ordenes/constants.ts`), así que se reutiliza en vez de crear una clase.
      return "b-dark";
    case "cancelada":
      return "b-red";
    default:
      return "b-gray";
  }
}

export function badgeEstatusProveedor(estatus: string): string {
  switch (estatus) {
    case "recibida":
      return "b-gray";
    case "autorizada":
      return "b-blue";
    case "pagada":
      return "b-teal";
    default:
      return "b-gray";
  }
}
