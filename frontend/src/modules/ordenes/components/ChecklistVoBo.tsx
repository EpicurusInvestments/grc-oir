/** Checklist de revisión PO §2 (transición 1.1 → 1.2): los 10 ítems + barra de progreso.
 * Puramente controlado — el padre decide qué hacer con `checklist` (habilitar el botón
 * "Dar Vo.Bo." solo cuando `isChecklistComplete(checklist)` es `true`).
 */

import { checklistProgress, ODC_REVIEW_CHECKLIST } from "../constants";

interface ChecklistVoBoProps {
  checklist: Record<string, boolean>;
  onChange: (checklist: Record<string, boolean>) => void;
  disabled?: boolean;
}

export function ChecklistVoBo({ checklist, onChange, disabled }: ChecklistVoBoProps) {
  const done = checklistProgress(checklist);
  const total = ODC_REVIEW_CHECKLIST.length;
  const completo = done === total;

  return (
    <div className="info-panel">
      <div className="info-panel-title">Checklist de revisión (PO §2)</div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 10 }}>
        {ODC_REVIEW_CHECKLIST.map((item) => (
          <label key={item.key} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12.5, cursor: disabled ? "default" : "pointer" }}>
            <input
              type="checkbox"
              checked={checklist[item.key] === true}
              disabled={disabled}
              onChange={(e) => onChange({ ...checklist, [item.key]: e.target.checked })}
              style={{ marginTop: 2 }}
            />
            <span style={{ color: checklist[item.key] ? "var(--text)" : "var(--text2)" }}>{item.label}</span>
          </label>
        ))}
      </div>

      <div style={{ height: 6, background: "var(--surface3)", borderRadius: 3, overflow: "hidden", marginBottom: 6 }}>
        <div
          style={{
            height: "100%",
            background: completo ? "var(--teal)" : "var(--amber-text)",
            width: `${(done / total) * 100}%`,
            transition: "width .2s",
          }}
        />
      </div>
      <div
        style={{
          fontSize: 11,
          fontWeight: completo ? 600 : 400,
          color: completo ? "var(--teal-text)" : "var(--text3)",
        }}
      >
        {completo ? `✓ ODC lista para Vo.Bo. (${done}/${total})` : `Faltan ${total - done} ítem(s) por palomear (${done}/${total})`}
      </div>
    </div>
  );
}
