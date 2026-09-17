/** Alta/edición de FacturaAgencia: el combo "Orden relacionada" es de selección
 * simple (a diferencia del de OI en FacturaAfiliado, la relación aquí es 1:1 por
 * factura) y solo lista las OC `orden_cerrada` de la agencia ya elegida. Al elegir una,
 * se sugiere el % de comisión de esa agencia (si el usuario no capturó uno a mano) y se
 * muestra en vivo la comisión calculada. La edición hace todo lo que hace el alta
 * (agencia/orden reasignables) — mismo criterio que ADR-077 en FacturaAfiliado.
 */

import { StrictMode } from "react";

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FacturaAgenciaForm } from "../facturaAgencia/components/FacturaAgenciaForm";
import type { OrdenClienteFacturableAgencia } from "../types";

const ordenesFacturablesMock = vi.fn();
const subirMock = vi.fn();

vi.mock("../hooks", () => ({
  useAgencias: () => ({
    data: [
      { id: "ag-1", etiqueta: "OMD México" },
      { id: "ag-2", etiqueta: "Mindshare" },
    ],
  }),
  useOrdenesFacturablesAgencia: (agenciaId: string | null) => ({
    data: agenciaId ? ordenesFacturablesMock(agenciaId) : [],
    isLoading: false,
  }),
}));

vi.mock("../api", () => ({
  adjuntosFacturacionApi: {
    subir: (...args: unknown[]) => subirMock(...args),
    ver: vi.fn(),
  },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
}));

const OC_A: OrdenClienteFacturableAgencia = {
  orden_id: "oc-a",
  folio_orden: "OC-2025-0041",
  numero_orden_cliente: "PO-BIMBO-0419",
  anunciante: "Grupo Bimbo",
  producto: "Pan Bimbo Integral 680g",
  total: "1183200.00",
  porcentaje_comision_agencia_default: "15.00",
};

const OC_B: OrdenClienteFacturableAgencia = {
  orden_id: "oc-b",
  folio_orden: "OC-2025-0055",
  numero_orden_cliente: "PO-BIMBO-0555",
  anunciante: "Grupo Bimbo",
  producto: "Bimbo Cero Cero",
  total: "500000.00",
  porcentaje_comision_agencia_default: "15.00",
};

/** Campo que sigue a una etiqueta `.fl` (mismo helper que en `FacturaAfiliadoForm.test.tsx`). */
function campoTrasEtiqueta<T extends Element = HTMLInputElement>(container: HTMLElement, texto: string): T {
  const etiquetas = Array.from(container.querySelectorAll(".fl"));
  const etiqueta = etiquetas.find((el) => el.textContent?.trim().startsWith(texto));
  if (!etiqueta) throw new Error(`No se encontró la etiqueta "${texto}"`);
  const campo = etiqueta.nextElementSibling;
  if (campo?.matches("input, select, textarea")) return campo as T;
  const interno = campo?.querySelector("input, select, textarea");
  if (!interno) throw new Error(`"${texto}" no tiene un campo después`);
  return interno as T;
}

function elegirAgencia(container: HTMLElement, id = "ag-1") {
  fireEvent.change(campoTrasEtiqueta<HTMLSelectElement>(container, "Agencia"), { target: { value: id } });
}

function elegirOrden(folio: string) {
  const buscador = screen.getByPlaceholderText("Busca por folio o número…");
  fireEvent.change(buscador, { target: { value: folio } });
  fireEvent.mouseDown(screen.getByText((c) => c.startsWith(folio)));
}

describe("FacturaAgenciaForm", () => {
  it("el combo de orden aparece deshabilitado hasta elegir una agencia", () => {
    render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByPlaceholderText("Busca por folio o número…")).toBeDisabled();
  });

  it("al elegir una agencia, el combo se habilita y solo lista sus OC cerradas", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);

    const buscador = screen.getByPlaceholderText("Busca por folio o número…");
    expect(buscador).toBeEnabled();
    fireEvent.change(buscador, { target: { value: "0041" } });
    expect(screen.getByText("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();
  });

  it("al elegir una orden, sugiere el % de comisión de la agencia y calcula la comisión en vivo", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);
    elegirOrden("OC-2025-0041");

    const porcentaje = campoTrasEtiqueta(container, "% de comisión");
    expect(porcentaje.value).toBe("15.00");
    // Comisión = 1,183,200.00 * 15% = 177,480.00
    expect(screen.getByText("$177,480.00")).toBeInTheDocument();
    expect(screen.getByText(/Sobre el total c\/IVA de la orden/)).toBeInTheDocument();
  });

  it("si el usuario ya capturó un % a mano, elegir la orden no lo pisa", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);

    const porcentaje = campoTrasEtiqueta(container, "% de comisión");
    fireEvent.change(porcentaje, { target: { value: "8.00" } });
    elegirOrden("OC-2025-0041");

    expect(porcentaje.value).toBe("8.00");
    // Comisión recalculada con el % capturado a mano: 1,183,200.00 * 8% = 94,656.00
    expect(screen.getByText("$94,656.00")).toBeInTheDocument();
  });

  it("cambiar de agencia limpia la orden ya elegida, incluso bajo StrictMode", async () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "ag-1" ? [OC_A] : [OC_B]));
    const { container } = render(
      <StrictMode>
        <FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />
      </StrictMode>,
    );
    elegirAgencia(container, "ag-1");
    elegirOrden("OC-2025-0041");
    expect(screen.getByDisplayValue("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();

    elegirAgencia(container, "ag-2");
    expect(screen.queryByDisplayValue("OC-2025-0041 — Grupo Bimbo")).toBeNull();
  });

  it("al guardar, onSubmit recibe agencia_id, orden_id y el % capturado", async () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAgenciaForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAgencia(container);
    elegirOrden("OC-2025-0041");
    fireEvent.change(campoTrasEtiqueta(container, "Subtotal"), { target: { value: "1020000.00" } });
    fireEvent.change(campoTrasEtiqueta(container, "IVA"), { target: { value: "163200.00" } });

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.agencia_id).toBe("ag-1");
    expect(payload.orden_id).toBe("oc-a");
    expect(payload.porcentaje_comision_agencia).toBe("15.00");
  });

  it("en edición, precarga agencia/orden ya asignadas y el combo de agencia sigue editable", async () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const onSubmit = vi.fn();
    render(
      <FacturaAgenciaForm
        isEdit
        defaultValues={{
          agencia_id: "ag-1",
          orden_id: "oc-a",
          folio_factura_agencia: "OMD-2025-0287",
          fecha_factura_agencia: "2025-06-08",
          monto_factura_agencia: "1020000.00",
          iva_factura_agencia: "163200.00",
          porcentaje_comision_agencia: "15.00",
        }}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue("OMD México")).toBeEnabled();
    expect(screen.getByDisplayValue("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].agencia_id).toBe("ag-1");
    expect(onSubmit.mock.calls[0][0].orden_id).toBe("oc-a");
  });

  it("subir el PDF llama a adjuntosFacturacionApi.subir con el tipo correcto y lo incluye al guardar", async () => {
    subirMock.mockResolvedValue({
      ref: "facturacion/proveedor/agencia/pdf/abc_factura.pdf",
      nombre_archivo: "factura.pdf",
    });
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAgenciaForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAgencia(container);
    elegirOrden("OC-2025-0041");
    fireEvent.change(campoTrasEtiqueta(container, "Subtotal"), { target: { value: "1020000.00" } });
    fireEvent.change(campoTrasEtiqueta(container, "IVA"), { target: { value: "163200.00" } });

    const archivo = new File(["contenido"], "factura.pdf", { type: "application/pdf" });
    const inputArchivo = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(inputArchivo, { target: { files: [archivo] } });

    await waitFor(() => expect(subirMock).toHaveBeenCalledWith("factura_agencia_pdf", archivo));
    expect(await screen.findByText("facturacion/proveedor/agencia/pdf/abc_factura.pdf")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].archivo_pdf_path).toBe(
      "facturacion/proveedor/agencia/pdf/abc_factura.pdf",
    );
  });
});
