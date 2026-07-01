/** Tag de campo: indica el ORIGEN del dato (de la propuesta).
 * El usuario siempre sabe de dónde viene un valor: catálogo, heredado, calculado, etc.
 */

export type FieldOrigin = "catalogo" | "heredado" | "calculado" | "derivado" | "audit" | "timbrado";

const META: Record<FieldOrigin, { cls: string; label: string }> = {
  catalogo: { cls: "cat", label: "Catálogo" },
  heredado: { cls: "her", label: "Heredado" },
  calculado: { cls: "calc", label: "Calculado" },
  derivado: { cls: "der", label: "Derivado" },
  audit: { cls: "audit", label: "Audit log" },
  timbrado: { cls: "timbrado", label: "Timbrado" },
};

export function FieldTag({ origin, text }: { origin: FieldOrigin; text?: string }) {
  const meta = META[origin];
  return <span className={`fl-tag ${meta.cls}`}>{text ?? meta.label}</span>;
}
