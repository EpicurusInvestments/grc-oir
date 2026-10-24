/** Bug reportado por el usuario (con captura): al elegir una "Factura de la
 * emisora"/"Factura de la agencia"/"Factura del vendedor" en el alta de una
 * Requisicion, el monto que se ve en el selector no se pintaba en "Monto de la
 * requisición" — había que teclearlo a mano aunque ya estuviera a la vista. Se
 * agrega el autollenado (siempre editable después: `monto_requisicion` nunca deja
 * de ser un `<input>` normal).
 *
 * Los `<select>` del formulario no tienen `<label>` asociado (mismo criterio que
 * `RegistrarPagoForm.test.tsx`), así que se ubican por posición con
 * `container.querySelectorAll("select.fsel")` en vez de por accesible name.
 */

import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RequisicionForm } from "../requisicion/components/RequisicionForm";

vi.mock("../api", () => ({
  afiliadosInfo: vi.fn().mockResolvedValue([
    { afiliado_id: "af-1", nombre_afiliado: "Radio Fórmula MX", razon_social_afiliado: "Radio Fórmula MX SA de CV" },
  ]),
  agenciasInfo: vi.fn().mockResolvedValue([
    { agencia_id: "ag-1", nombre_agencia: "Mindshare México", rfc_agencia: "MIN010101AAA", porcentaje_comision_agencia_default: "10.00" },
  ]),
  vendedoresInfo: vi.fn().mockResolvedValue([
    { vendedor_id: "vd-1", nombre_vendedor: "Juan Arturo Rodríguez Morales", porcentaje_comision_default: "5.00" },
  ]),
  facturasAfiliadoPagables: vi.fn().mockResolvedValue([
    { factura_afiliado_id: "fa-1", afiliado_id: "af-1", factura_emisora: "AFI-004", total_factura_afiliado: "290.25" },
  ]),
  facturasAgenciaPagables: vi.fn().mockResolvedValue([
    { factura_agencia_id: "fg-1", agencia_id: "ag-1", orden_id: "oc-1", folio_factura_agencia: "AGE-009", total_factura_agencia: "704.70", porcentaje_comision_agencia: null },
  ]),
  facturasVendedorPagables: vi.fn().mockResolvedValue([
    { factura_vendedor_id: "fv-1", vendedor_id: "vd-1", orden_id: "oc-1", folio_factura_vendedor: "VND-009", total_factura_vendedor: "4698.00" },
  ]),
  ordenesInfo: vi.fn().mockResolvedValue([{ orden_id: "oc-1", folio_orden: "OC-2026-0041", total: "4698.00" }]),
}));

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RequisicionForm onSubmit={vi.fn()} onCancel={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("RequisicionForm: autollenado del monto al elegir una factura", () => {
  it("pago_afiliado: elegir la factura de la emisora pinta su total en 'Monto de la requisición', y sigue editable", async () => {
    const { container } = renderForm();
    await screen.findByText("Radio Fórmula MX");

    const [, selectAfiliado, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectAfiliado, { target: { value: "af-1" } });
    fireEvent.change(selectFactura, { target: { value: "fa-1" } });

    const monto = screen.getByDisplayValue("290.25") as HTMLInputElement;
    expect(monto).toBeInTheDocument();

    fireEvent.change(monto, { target: { value: "250.00" } });
    expect(monto.value).toBe("250.00");
  });

  it("pago_agencia: elegir la factura de la agencia pinta su total", async () => {
    const { container } = renderForm();
    await screen.findByText("Radio Fórmula MX");

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "pago_agencia" } });
    await screen.findByText("Mindshare México");

    const [, selectAgencia, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectAgencia, { target: { value: "ag-1" } });
    fireEvent.change(selectFactura, { target: { value: "fg-1" } });

    expect(screen.getByDisplayValue("704.70")).toBeInTheDocument();
  });

  it("comision_vendedor: elegir la factura del vendedor pinta su total", async () => {
    const { container } = renderForm();
    await screen.findByText("Radio Fórmula MX");

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "comision_vendedor" } });
    await screen.findByText("Juan Arturo Rodríguez Morales");

    const [, selectVendedor, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectVendedor, { target: { value: "vd-1" } });
    fireEvent.change(selectFactura, { target: { value: "fv-1" } });

    expect(screen.getByDisplayValue("4698.00")).toBeInTheDocument();
  });
});
