/** "Asignación a órdenes" de FacturaAgencia (alta Y edición) — ADR nuevo (petición del
 * usuario, con captura, 2026-11-06) que SUSTITUYE el criterio de ADR-079: el combo
 * "Orden relacionada" de selección simple se vuelve "Buscar y agregar" multi-selección,
 * mismo patrón que `FacturaAfiliadoForm`. Cada orden aporta su propia comisión (su % ya
 * pactado, o si no el default del catálogo de la agencia) — Subtotal/IVA/Total son
 * ahora CALCULADOS (suma de esas comisiones + IVA), ya no se capturan a mano.
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

// % propio de la orden NULO: usa el default de la agencia (15%). Comisión = 1,183,200.00 * 15% = 177,480.00
const OC_A: OrdenClienteFacturableAgencia = {
  orden_id: "oc-a",
  folio_orden: "OC-2025-0041",
  numero_orden_cliente: "PO-BIMBO-0419",
  anunciante: "Grupo Bimbo",
  producto: "Pan Bimbo Integral 680g",
  total: "1183200.00",
  porcentaje_comision_agencia_snap: null,
  porcentaje_comision_agencia_default: "15.00",
};

// % propio de la orden (10%), DISTINTO del default de la agencia (15%): debe usarse el
// de la orden. Comisión = 500,000.00 * 10% = 50,000.00
const OC_B: OrdenClienteFacturableAgencia = {
  orden_id: "oc-b",
  folio_orden: "OC-2025-0055",
  numero_orden_cliente: "PO-BIMBO-0555",
  anunciante: "Grupo Bimbo",
  producto: "Bimbo Cero Cero",
  total: "500000.00",
  porcentaje_comision_agencia_snap: "10.00",
  porcentaje_comision_agencia_default: "15.00",
};

/** Campo que sigue a una etiqueta `.fl` (mismo patrón que `FacturaAfiliadoForm.test.tsx`). */
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

function agregarOrden(folio: string) {
  const buscador = screen.getByPlaceholderText("Buscar por folio y agregar…");
  fireEvent.change(buscador, { target: { value: folio } });
  fireEvent.mouseDown(screen.getByText((c) => c.startsWith(folio)));
}

describe("FacturaAgenciaForm — Asignación a órdenes", () => {
  it("el combo aparece deshabilitado hasta elegir una agencia", () => {
    render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByPlaceholderText("Buscar por folio y agregar…")).toBeDisabled();
  });

  it("al elegir una agencia, el combo se habilita y solo lista sus OC cerradas", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);

    const buscador = screen.getByPlaceholderText("Buscar por folio y agregar…");
    expect(buscador).toBeEnabled();
    fireEvent.change(buscador, { target: { value: "0041" } });
    expect(screen.getByText("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();
  });

  it("al agregar una orden sin % propio, usa el default de la agencia y calcula su comisión", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);
    agregarOrden("OC-2025-0041");

    expect(screen.getByText(/15.00 %/)).toBeInTheDocument();
    // Aparece en el renglón y en el Subtotal calculado (coincide: es la única elegida).
    expect(screen.getAllByText("$177,480.00").length).toBe(2);
    // ...y ya no se ofrece de nuevo en el buscador.
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio y agregar…"), { target: { value: "0041" } });
    expect(screen.queryByText("OC-2025-0041 — Grupo Bimbo")).toBeNull();
  });

  it("al agregar una orden CON % propio, usa el de la orden, no el default de la agencia", () => {
    ordenesFacturablesMock.mockReturnValue([OC_B]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);
    agregarOrden("OC-2025-0055");

    expect(screen.getByText(/10.00 %/)).toBeInTheDocument();
    expect(screen.getAllByText("$50,000.00").length).toBe(2);
  });

  it("Subtotal/IVA/Total acumulan la comisión de cada orden elegida, con su propio %", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A, OC_B]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);
    agregarOrden("OC-2025-0041");
    agregarOrden("OC-2025-0055");

    // Subtotal = 177,480.00 + 50,000.00 = 227,480.00
    expect(screen.getByText("$227,480.00")).toBeInTheDocument();
    // IVA = 227,480.00 * 16% = 36,396.80
    expect(screen.getByText("$36,396.80")).toBeInTheDocument();
    // Total = 227,480.00 + 36,396.80 = 263,876.80
    expect(screen.getByText("$263,876.80")).toBeInTheDocument();
  });

  it("quitar una orden de la lista la regresa al buscador y baja el Subtotal", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A, OC_B]);
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container);
    agregarOrden("OC-2025-0041");
    agregarOrden("OC-2025-0055");
    expect(screen.getByText("$227,480.00")).toBeInTheDocument();

    fireEvent.click(screen.getAllByTitle("Quitar de esta factura")[0]);

    expect(screen.queryByText("$227,480.00")).toBeNull();
    expect(screen.getAllByText("$50,000.00").length).toBe(2);
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio y agregar…"), { target: { value: "0041" } });
    expect(screen.getByText("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();
  });

  it("cambiar de agencia limpia las órdenes ya elegidas", () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "ag-1" ? [OC_A] : [OC_B]));
    const { container } = render(<FacturaAgenciaForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAgencia(container, "ag-1");
    agregarOrden("OC-2025-0041");
    expect(screen.getAllByText("$177,480.00").length).toBe(2);

    elegirAgencia(container, "ag-2");
    expect(screen.queryByText("$177,480.00")).toBeNull();
    expect(screen.getByText("Sin órdenes agregadas todavía.")).toBeInTheDocument();
  });

  it("al guardar con órdenes elegidas, onSubmit recibe ordenes_ids con ambas", async () => {
    ordenesFacturablesMock.mockReturnValue([OC_A, OC_B]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAgenciaForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAgencia(container);
    agregarOrden("OC-2025-0041");
    agregarOrden("OC-2025-0055");

    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.agencia_id).toBe("ag-1");
    expect(payload.ordenes_ids).toEqual(["oc-a", "oc-b"]);
  });

  it("fix: en edición, la agencia se puede reasignar y la sección de asignación precarga lo ya asignado", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    render(
      <FacturaAgenciaForm
        isEdit
        defaultValues={{
          agencia_id: "ag-1",
          folio_factura_agencia: "OMD-2025-0287",
          fecha_factura_agencia: "2025-06-08",
        }}
        ordenesIniciales={[
          {
            id: "fao-1",
            factura_agencia_id: "fa-1",
            orden_id: "oc-a",
            porcentaje_comision_snap: "15.00",
            comision_calculada: "177480.00",
            folio_orden: "OC-2025-0041",
            numero_orden_cliente: "PO-BIMBO-0419",
            anunciante: "Grupo Bimbo",
            producto: null,
            orden_total: "1183200.00",
          },
        ]}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(await screen.findByDisplayValue("OMD México")).toBeEnabled();
    expect(screen.getByText("OC-2025-0041")).toBeInTheDocument();
    expect(screen.getAllByText("$177,480.00").length).toBe(2);
  });

  it("en edición, cambiar de agencia limpia las órdenes ya asignadas (eran de la agencia anterior)", async () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "ag-1" ? [OC_A] : [OC_B]));
    const { container } = render(
      <FacturaAgenciaForm
        isEdit
        defaultValues={{
          agencia_id: "ag-1",
          folio_factura_agencia: "OMD-2025-0287",
          fecha_factura_agencia: "2025-06-08",
        }}
        ordenesIniciales={[
          {
            id: "fao-1",
            factura_agencia_id: "fa-1",
            orden_id: "oc-a",
            porcentaje_comision_snap: "15.00",
            comision_calculada: "177480.00",
            folio_orden: "OC-2025-0041",
            numero_orden_cliente: "PO-BIMBO-0419",
            anunciante: "Grupo Bimbo",
            producto: null,
            orden_total: "1183200.00",
          },
        ]}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await screen.findByDisplayValue("OMD México");
    expect(screen.getByText("OC-2025-0041")).toBeInTheDocument();

    elegirAgencia(container, "ag-2");
    expect(screen.queryByText("OC-2025-0041")).toBeNull();
    expect(screen.getByText("Sin órdenes agregadas todavía.")).toBeInTheDocument();
  });

  it("fix: en edición, precarga las órdenes ya asignadas y sobreviven al doble-render de StrictMode", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    const onSubmit = vi.fn();
    render(
      <StrictMode>
        <FacturaAgenciaForm
          isEdit
          defaultValues={{
            agencia_id: "ag-1",
            folio_factura_agencia: "OMD-2025-0287",
            fecha_factura_agencia: "2025-06-08",
          }}
          ordenesIniciales={[
            {
              id: "fao-1",
              factura_agencia_id: "fa-1",
              orden_id: "oc-a",
              porcentaje_comision_snap: "15.00",
              comision_calculada: "177480.00",
              folio_orden: "OC-2025-0041",
              numero_orden_cliente: "PO-BIMBO-0419",
              anunciante: "Grupo Bimbo",
              producto: null,
              orden_total: "1183200.00",
            },
          ]}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
        />
      </StrictMode>,
    );
    await screen.findByDisplayValue("OMD México");
    expect(screen.getAllByText("$177,480.00").length).toBe(2);

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].agencia_id).toBe("ag-1");
    expect(onSubmit.mock.calls[0][0].ordenes_ids).toEqual(["oc-a"]);
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
    agregarOrden("OC-2025-0041");

    const archivo = new File(["contenido"], "factura.pdf", { type: "application/pdf" });
    const inputArchivo = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(inputArchivo, { target: { files: [archivo] } });

    await waitFor(() => expect(subirMock).toHaveBeenCalledWith("factura_agencia_pdf", archivo));
    const texto = await screen.findByText("factu...pdf");
    expect(texto).toHaveAttribute("title", "facturacion/proveedor/agencia/pdf/abc_factura.pdf");

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].archivo_pdf_path).toBe(
      "facturacion/proveedor/agencia/pdf/abc_factura.pdf",
    );
  });
});
