/** Modal de confirmación (p.ej. activar/desactivar un catálogo). Envuelve Dialog. */

import { Button } from "primereact/button";
import { Dialog } from "primereact/dialog";

interface ConfirmDialogProps {
  visible: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** true cuando la acción es destructiva/baja (estiliza el botón). */
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  visible,
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  danger = false,
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const footer = (
    <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", padding: "4px 24px 20px" }}>
      <button type="button" className="btn btn-sm" onClick={onCancel} disabled={loading}>
        {cancelLabel}
      </button>
      <Button
        label={confirmLabel}
        severity={danger ? "danger" : undefined}
        loading={loading}
        onClick={onConfirm}
        style={{ fontSize: 12, padding: "0 14px" }}
      />
    </div>
  );

  return (
    // El reset global (`* { padding: 0 }` en theme.css) se come el padding que el tema
    // de PrimeReact traía por default en header/content/footer — se repone a mano con
    // `headerStyle`/`contentStyle` y el padding propio del footer (arriba), para que el
    // texto y los botones no queden pegados al borde del diálogo.
    <Dialog
      header={title}
      visible={visible}
      onHide={onCancel}
      footer={footer}
      style={{ width: 480 }}
      headerStyle={{ padding: "20px 24px 12px" }}
      contentStyle={{ padding: "0 24px 20px" }}
    >
      <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--text2)", margin: 0 }}>{message}</p>
    </Dialog>
  );
}
