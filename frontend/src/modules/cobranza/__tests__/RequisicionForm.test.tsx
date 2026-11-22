/** ADR-282 (petición del usuario, con captura): el alta de "Pago afiliado"/"Pago
 * agencia"/"Pagos vendedor" se movió a un bloque embebido en la pantalla de su propia
 * factura (F2) — este formulario queda solo para "Comisión agencia" (sin factura de
 * origen, el único tipo que sigue dándose de alta en "Requisiciones de pago").
 *
 * Los `<select>`/buscadores sin `<label>` asociado se ubican por posición o por texto
 * visible, mismo criterio que el resto de este módulo.
 */

import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RequisicionForm } from "../requisicion/components/RequisicionForm";

vi.mock("../api", () => ({
  agenciasInfo: vi.fn().mockResolvedValue([
    { agencia_id: "ag-1", nombre_agencia: "Mindshare México", rfc_agencia: "MIN010101AAA", porcentaje_comision_agencia_default: "10.00" },
    { agencia_id: "ag-2", nombre_agencia: "OMD México", rfc_agencia: "OMD010101AAA", porcentaje_comision_agencia_default: "12.00" },
  ]),
  ordenesInfo: vi.fn().mockResolvedValue([{ orden_id: "oc-1", folio_orden: "OC-2026-0041", total: "4698.00" }]),
}));

async function elegirEnBuscable(input: HTMLElement, texto: string) {
  fireEvent.change(input, { target: { value: texto } });
  fireEvent.mouseDown(await screen.findByText(texto));
}

function buscador(container: HTMLElement, placeholder: string): HTMLInputElement {
  return container.querySelector(`input[placeholder="${placeholder}"]`) as HTMLInputElement;
}

function renderForm(onSubmit = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <RequisicionForm onSubmit={onSubmit} onCancel={vi.fn()} />
    </QueryClientProvider>,
  );
  return { ...utils, onSubmit };
}

describe("RequisicionForm: alta de 'Comisión agencia' (único tipo que queda aquí)", () => {
  it("ya no pide 'Número de requisición' ni un selector de 'Tipo de requisición'", () => {
    const { container } = renderForm();
    expect(screen.queryByText("Número de requisición")).not.toBeInTheDocument();
    expect(screen.queryByText("Tipo de requisición")).not.toBeInTheDocument();
    expect(container.querySelectorAll("select.fsel").length).toBe(0);
  });

  it("elegir la agencia sugiere su % de comisión por defecto (editable)", async () => {
    const { container } = renderForm();
    await elegirEnBuscable(buscador(container, "Selecciona…"), "Mindshare México");
    expect(screen.getByDisplayValue("10.00")).toBeInTheDocument();
  });

  it("exige agencia, orden y monto antes de guardar", () => {
    const { onSubmit } = renderForm();
    fireEvent.click(screen.getByText("Guardar"));
    expect(screen.getByText("Captura el monto de la requisición.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("guarda con tipo_requisicion='comision_agencia' y las FKs correctas", async () => {
    const { container, onSubmit } = renderForm();

    await elegirEnBuscable(buscador(container, "Selecciona…"), "Mindshare México");
    await elegirEnBuscable(buscador(container, "Buscar por folio de orden…"), "OC-2026-0041 · $4,698.00");

    const ocSap = container.querySelector('input[placeholder="OC-SAP-XXXX"]') as HTMLInputElement;
    fireEvent.change(ocSap, { target: { value: "OC-SAP-9001" } });
    // Hay 2 campos `inputmode="decimal"` (% Comisión y Monto, en ese orden) — el monto
    // es el segundo.
    const [, monto] = container.querySelectorAll('input[inputmode="decimal"]');
    fireEvent.change(monto, { target: { value: "469.80" } });

    fireEvent.click(screen.getByText("Guardar"));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        tipo_requisicion: "comision_agencia",
        agencia_id: "ag-1",
        orden_id: "oc-1",
        numero_oc_sap: "OC-SAP-9001",
        monto_requisicion: "469.80",
        porcentaje_comision_agencia_req: "10.00",
        afiliado_id: null,
        factura_afiliado_id: null,
        factura_agencia_id: null,
        vendedor_comision_id: null,
        factura_vendedor_id: null,
      }),
    );
  });
});
