/** Ayudas de consulta para RTL, compartidas entre las pruebas de formularios de F1.
 *
 * Hallazgo de accesibilidad (reportado en la Tanda 3): varias pantallas usan
 * `<div className="fl">Etiqueta</div>` o `<div className="sec">Etiqueta</div>` seguido del
 * campo, SIN `<label htmlFor>` ni `aria-label` — por eso `getByLabelText` de Testing Library
 * no los encuentra (viola la regla de `frontend/CLAUDE.md`: "labels en inputs"). Este helper
 * reproduce cómo lo ubica un usuario vidente: el campo que sigue inmediatamente a la etiqueta
 * visible. Los checkboxes SÍ están bien asociados (envueltos en `<label>`) y usan
 * `getByRole("checkbox", { name })` normalmente.
 *
 * `.form-card-title` se suma a `.fl`/`.sec`: mismo patrón "etiqueta + campo inmediato",
 * usado por las tarjetas de sección (look and feel del prototipo `Fase_1_-_Ordenes.html`).
 */
export function fieldByLabelText<T extends Element = HTMLElement>(container: ParentNode, labelText: string): T {
  const candidatos = Array.from(container.querySelectorAll(".fl, .sec, .form-card-title"));
  const labelDiv = candidatos.find((d) => d.textContent?.trim().startsWith(labelText));
  if (!labelDiv) throw new Error(`No se encontró la etiqueta "${labelText}"`);
  const campo = labelDiv.nextElementSibling;
  if (!campo) throw new Error(`"${labelText}" no tiene un campo inmediatamente después`);
  // Algunos campos (p.ej. MoneyInput) envuelven el <input> real en un <div> de
  // presentación (prefijo "$"); si el elemento inmediato no es el propio control,
  // se busca el control real dentro de él.
  if (campo.matches("input, select, textarea")) return campo as T;
  const controlInterno = campo.querySelector("input, select, textarea");
  if (!controlInterno) throw new Error(`"${labelText}" no contiene un campo de formulario`);
  return controlInterno as T;
}
