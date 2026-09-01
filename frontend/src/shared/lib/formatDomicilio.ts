/** Domicilio estructurado (ADR-059) resumido en una sola línea legible, para los paneles
 * de detalle de Anunciante/EmpresaFacturadora — evita repetir 10 pares etiqueta/valor
 * cuando casi siempre alcanza con una línea tipo "Calle 123, Colonia, Municipio, Estado,
 * CP 00000". `null` si NINGÚN campo estructurado está capturado (el detalle cae al
 * campo legacy en ese caso). */
export interface DomicilioParcial {
  calle: string | null;
  numero_exterior: string | null;
  numero_interior: string | null;
  colonia: string | null;
  localidad: string | null;
  municipio: string | null;
  estado: string | null;
  pais: string | null;
  codigo_postal: string | null;
}

export function formatDomicilio(d: DomicilioParcial): string | null {
  const calleYNumero = [d.calle, d.numero_exterior && `No. ${d.numero_exterior}`]
    .filter(Boolean)
    .join(" ");
  const numeroInterior = d.numero_interior ? `Int. ${d.numero_interior}` : null;
  const partes = [
    calleYNumero || null,
    numeroInterior,
    d.colonia,
    d.localidad,
    d.municipio,
    d.estado,
    d.codigo_postal && `C.P. ${d.codigo_postal}`,
    d.pais && d.pais !== "MEX" ? d.pais : null,
  ].filter((p): p is string => Boolean(p && p.trim()));

  return partes.length > 0 ? partes.join(", ") : null;
}
