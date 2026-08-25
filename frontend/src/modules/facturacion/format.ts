/** Formato de presentación de F2.
 *
 * No se reutiliza `modules/ordenes/format.ts` a propósito: importar de otro módulo de
 * negocio crea la dependencia directa que el CLAUDE.md prohíbe (lo compartido va a
 * `shared/`), y además aquellos helpers reciben `number` mientras que los montos de F2
 * llegan como STRING decimal desde el backend.
 */

/** Formatea un monto decimal en string (p.ej. "11600.00") como moneda MXN. */
export function fmtMoneda(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const n = Number(valor);
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 2,
  });
}

export function fmtPorcentaje(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const n = Number(valor);
  return Number.isNaN(n) ? "—" : `${n.toLocaleString("es-MX", { minimumFractionDigits: 2 })} %`;
}

export function fmtFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Se parte el ISO en vez de usar `new Date(iso)`: una fecha pura ("2026-02-01") se
  // interpreta como UTC y en México se mostraría el día anterior.
  const [anio, mes, dia] = iso.slice(0, 10).split("-");
  if (!anio || !mes || !dia) return "—";
  return `${dia}/${mes}/${anio}`;
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
      return "b-teal";
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
    case "en_revision":
      return "b-amber";
    case "autorizada":
      return "b-blue";
    case "pagada":
      return "b-teal";
    default:
      return "b-gray";
  }
}
