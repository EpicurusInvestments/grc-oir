/** Formato de presentación de F3.
 *
 * No se reutiliza `modules/facturacion/format.ts` a propósito: importar de otro módulo
 * de negocio crea la dependencia directa que el CLAUDE.md prohíbe (lo compartido va a
 * `shared/`) — mismo criterio que F2 respecto a F1.
 */

/** Formatea un monto decimal en string (p.ej. "11600.00") como moneda MXN, siempre a 2
 * decimales SIN redondear (p.ej. "1234.567" → $1,234.56, no $1,234.57) — se corta el
 * STRING antes de convertir a número, así que no depende de ningún redondeo de
 * `toLocaleString` ni de precisión de punto flotante (mismo criterio que F2,
 * `modules/facturacion/format.ts`). */
export function fmtMoneda(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  let v = valor;
  const idxPunto = v.indexOf(".");
  if (idxPunto !== -1) v = v.slice(0, idxPunto + 3);
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtPorcentaje(valor: string | null | undefined): string {
  if (valor == null || valor === "") return "—";
  const n = Number(valor);
  return Number.isNaN(n) ? "—" : `${n.toLocaleString("es-MX", { minimumFractionDigits: 2 })} %`;
}

export function fmtFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Se parte el ISO en vez de usar `new Date(iso)`: una fecha pura se interpreta como
  // UTC y en México se mostraría el día anterior (mismo motivo que en F2).
  const [anio, mes, dia] = iso.slice(0, 10).split("-");
  if (!anio || !mes || !dia) return "—";
  return `${dia}/${mes}/${anio}`;
}

export function oGuion(valor: string | null | undefined): string {
  return valor && valor.trim() ? valor : "—";
}

/** Días entre hoy y una fecha ISO (positivo = futuro, negativo = ya pasó). */
export function diasHasta(iso: string): number {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);
  const [anio, mes, dia] = iso.slice(0, 10).split("-").map(Number);
  const destino = new Date(anio, mes - 1, dia);
  return Math.round((destino.getTime() - hoy.getTime()) / (1000 * 60 * 60 * 24));
}

/** Clase de badge por estatus, reutilizando los colores YA definidos en `theme.css` (sin
 *  inventar clases nuevas — mismo criterio que `badgeEstadoFactura` de F2). */
export function badgeEstatusCobro(estatus: string): string {
  switch (estatus) {
    case "pendiente":
      return "b-amber";
    case "cobro_parcial":
      return "b-purple";
    case "cobrada":
      return "b-dark";
    default:
      return "b-gray";
  }
}

/** El badge "Vencida" no es un valor de `estatus_cobro`: es el badge derivado (ver
 *  `types.ts`). Rojo, como el resto de las alertas del sistema. */
export const BADGE_VENCIDA = "b-red";

export function badgeEstatusRequisicion(estatus: string): string {
  switch (estatus) {
    case "pendiente":
      return "b-amber";
    case "autorizada":
      return "b-blue";
    case "pagada":
      return "b-dark";
    case "cancelada":
      return "b-gray";
    default:
      return "b-gray";
  }
}

export function badgeTipoRequisicion(tipo: string): string {
  switch (tipo) {
    case "pago_afiliado":
      return "b-teal";
    case "pago_agencia":
      return "b-purple";
    case "comision_vendedor":
      return "b-blue";
    case "comision_agencia":
      return "b-amber";
    default:
      return "b-gray";
  }
}

export function badgeTipoMovimiento(tipo: string): string {
  return tipo === "abono" ? "b-green" : "b-amber";
}

export function badgeConciliado(conciliado: boolean): string {
  return conciliado ? "b-green" : "b-amber";
}
