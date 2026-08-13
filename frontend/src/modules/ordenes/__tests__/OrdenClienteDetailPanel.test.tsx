/** Corrección del hallazgo #12: el historial de cambios de comisión se auditaba en memoria
 * pero ninguna pantalla lo mostraba. Cubre el nuevo bloque "Historial de cambios de
 * comisión" en `OrdenClienteDetailPanel.tsx` (mismo patrón que `ContratoDetailPanel` en F0).
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenClienteDetailPanel } from "../ordenCliente/components/OrdenClienteDetailPanel";
import type { HistorialComision } from "../state/OrdenesContext";
import { makeOC } from "./fixtures";

function renderPanel(oc: ReturnType<typeof makeOC>, historialComisiones: HistorialComision[] = []) {
  return render(
    <OrdenClienteDetailPanel
      oc={oc}
      ordenesEstacion={[]}
      incidencias={[]}
      historialComisiones={historialComisiones}
      onSeleccionarOE={vi.fn()}
      onEditar={vi.fn()}
      onAsignarEstaciones={vi.fn()}
      onCerrar={vi.fn()}
    />,
  );
}

describe("Historial de cambios de comisión (fix del hallazgo #12)", () => {
  it("sin cambios registrados, muestra el estado vacío explícito", () => {
    renderPanel(makeOC());
    expect(screen.getByText("Sin cambios registrados.")).toBeInTheDocument();
  });

  it("muestra solo los cambios de ESTA OC (filtra por entidad_id), con campo, valores, usuario y motivo", () => {
    const oc = makeOC();
    const historial: HistorialComision[] = [
      {
        log_cambio_parametro_id: "h1",
        entidad: "OrdenCliente",
        entidad_id: oc.id,
        campo: "porcentaje_comision_agencia_snap",
        valor_anterior: "15",
        valor_nuevo: "13.5",
        usuario: "dev.admin",
        ip: null,
        motivo_cambio: "Renegociación posterior al cierre.",
        fecha_cambio: "2025-01-10T09:45:00",
      },
      {
        log_cambio_parametro_id: "h2",
        entidad: "OrdenCliente",
        entidad_id: "otra-oc-distinta",
        campo: "porcentaje_comision_vendedor_principal_snap",
        valor_anterior: "4",
        valor_nuevo: "5",
        usuario: "alguien.mas",
        ip: null,
        motivo_cambio: null,
        fecha_cambio: "2025-01-01T00:00:00",
      },
    ];
    renderPanel(oc, historial);

    expect(screen.getByText(/% comisión agencia/)).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("13.5")).toBeInTheDocument();
    expect(screen.getByText(/dev\.admin/)).toBeInTheDocument();
    expect(screen.getByText(/Renegociación posterior al cierre\./)).toBeInTheDocument();

    // El de la otra OC no debe aparecer.
    expect(screen.queryByText(/alguien\.mas/)).toBeNull();
  });
});
