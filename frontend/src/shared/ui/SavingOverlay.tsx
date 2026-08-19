/** Modal de "guardando" — se muestra mientras un formulario envía su alta/edición al
 * backend, para que el usuario sepa que la pantalla está trabajando. Sin botón de cerrar
 * ni cierre por clic afuera: desaparece solo cuando `visible` pasa a `false` (la request
 * termina). Mismo patrón visual que `ConfirmDialog` (envuelve `Dialog` de PrimeReact).
 */

import { Dialog } from "primereact/dialog";

interface SavingOverlayProps {
  visible: boolean | undefined;
  message?: string;
}

export function SavingOverlay({ visible, message = "Guardando, por favor espera…" }: SavingOverlayProps) {
  return (
    <Dialog
      visible={!!visible}
      onHide={() => {}}
      closable={false}
      showHeader={false}
      dismissableMask={false}
      closeOnEscape={false}
      style={{ width: 320 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 4px" }}>
        <i className="pi pi-spin pi-spinner" style={{ fontSize: 22, color: "var(--phase)" }} />
        <span style={{ fontSize: 13.5 }}>{message}</span>
      </div>
    </Dialog>
  );
}
