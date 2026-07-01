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
    <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
      <button type="button" className="btn btn-sm" onClick={onCancel} disabled={loading}>
        {cancelLabel}
      </button>
      <Button
        label={confirmLabel}
        severity={danger ? "danger" : undefined}
        loading={loading}
        onClick={onConfirm}
      />
    </div>
  );

  return (
    <Dialog header={title} visible={visible} onHide={onCancel} footer={footer} style={{ width: 420 }}>
      <p style={{ fontSize: 13, color: "var(--text2)" }}>{message}</p>
    </Dialog>
  );
}
