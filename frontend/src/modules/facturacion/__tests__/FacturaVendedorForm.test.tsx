/** "Asignación a órdenes" de FacturaVendedor (alta Y edición) — ADR nuevo (petición del
 * usuario, con captura, 2026-11-06), mismo cambio que para `FacturaAgenciaForm`: el
 * combo "Orden relacionada" de selección simple se vuelve "Buscar y agregar"
 * multi-selección. Cada orden aporta su propia comisión (su % ya pactado, o si no el
 * default del catálogo del vendedor) — Subtotal/IVA/Total son CALCULADOS.
 */

import { StrictMode } from "react";

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FacturaVendedorForm } from "../facturaVendedor/components/FacturaVendedorForm";
import type { OrdenClienteFacturableVendedor } from "../types";

const ordenesFacturablesMock = vi.fn();
const subirMock = vi.fn();
const leerCfdiMock = vi.fn();

vi.mock("../hooks", () => ({
  useVendedores: () => ({
    data: [
      { id: "vd-1", etiqueta: "Carmen Aristegui" },
      { id: "vd-2", etiqueta: "Juan Pérez" },
    ],
  }),
  useOrdenesFacturablesVendedor: (vendedorId: string | null, excluirDeFacturaId?: string) => ({
    data: vendedorId ? ordenesFacturablesMock(vendedorId, excluirDeFacturaId) : [],
    isLoading: false,
  }),
}));

vi.mock("../api", () => ({
  adjuntosFacturacionApi: {
    subir: (...args: unknown[]) => subirMock(...args),
    ver: vi.fn(),
  },
  cfdiApi: {
    leer: (...args: unknown[]) => leerCfdiMock(...args),
  },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
}));

// % propio de la orden NULO: usa el default del vendedor (15%). Comisión = 1,183,200.00 * 15% = 177,480.00
const OC_A: OrdenClienteFacturableVendedor = {
  orden_id: "oc-a",
  folio_orden: "OC-2025-0041",
  numero_orden_cliente: "PO-BIMBO-0419",
  anunciante: "Grupo Bimbo",
  producto: "Pan Bimbo Integral 680g",
  total: "1183200.00",
  porcentaje_comision_vendedor_snap: null,
  porcentaje_comision_vendedor_default: "15.00",
};

// % propio de la orden (10%), DISTINTO del default del vendedor (15%): debe usarse el
// de la orden. Comisión = 500,000.00 * 10% = 50,000.00
const OC_B: OrdenClienteFacturableVendedor = {
  orden_id: "oc-b",
  folio_orden: "OC-2025-0055",
  numero_orden_cliente: "PO-BIMBO-0555",
  anunciante: "Grupo Bimbo",
  producto: "Bimbo Cero Cero",
  total: "500000.00",
  porcentaje_comision_vendedor_snap: "10.00",
  porcentaje_comision_vendedor_default: "15.00",
};

/** Campo que sigue a una etiqueta `.fl` (mismo patrón que `FacturaAgenciaForm.test.tsx`). */
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

// ADR-221b (combos largos → SearchableSelect): se elige por LABEL, no por id — el campo
// es un buscador, no un <select> nativo.
const ETIQUETA_VENDEDOR: Record<string, string> = { "vd-1": "Carmen Aristegui", "vd-2": "Juan Pérez" };
function elegirVendedor(container: HTMLElement, id = "vd-1") {
  const input = campoTrasEtiqueta<HTMLInputElement>(container, "Vendedor");
  const texto = ETIQUETA_VENDEDOR[id];
  fireEvent.change(input, { target: { value: texto } });
  fireEvent.mouseDown(screen.getByText(texto));
}

function agregarOrden(folio: string) {
  const buscador = screen.getByPlaceholderText("Buscar por folio y agregar…");
  fireEvent.change(buscador, { target: { value: folio } });
  fireEvent.mouseDown(screen.getByText((c) => c.startsWith(folio)));
}

describe("FacturaVendedorForm — Asignación a órdenes", () => {
  it("el combo aparece deshabilitado hasta elegir un vendedor", () => {
    render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByPlaceholderText("Buscar por folio y agregar…")).toBeDisabled();
  });

  it("al elegir un vendedor, el combo se habilita y solo lista sus OC cerradas", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirVendedor(container);

    const buscador = screen.getByPlaceholderText("Buscar por folio y agregar…");
    expect(buscador).toBeEnabled();
    fireEvent.change(buscador, { target: { value: "0041" } });
    expect(screen.getByText("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();
  });

  it("al agregar una orden sin % propio, usa el default del vendedor y calcula su comisión", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const { container } = render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirVendedor(container);
    agregarOrden("OC-2025-0041");

    expect(screen.getByText(/15.00 %/)).toBeInTheDocument();
    expect(screen.getByText("$177,480.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("177480.00")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio y agregar…"), { target: { value: "0041" } });
    expect(screen.queryByText("OC-2025-0041 — Grupo Bimbo")).toBeNull();
  });

  it("al agregar una orden CON % propio, usa el de la orden, no el default del vendedor", () => {
    ordenesFacturablesMock.mockReturnValue([OC_B]);
    const { container } = render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirVendedor(container);
    agregarOrden("OC-2025-0055");

    expect(screen.getByText(/10.00 %/)).toBeInTheDocument();
    expect(screen.getByText("$50,000.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("50000.00")).toBeInTheDocument();
  });

  it("Subtotal/IVA/Total acumulan la comisión de cada orden elegida, con su propio %", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A, OC_B]);
    const { container } = render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirVendedor(container);
    agregarOrden("OC-2025-0041");
    agregarOrden("OC-2025-0055");

    // Subtotal = 177,480.00 + 50,000.00 = 227,480.00 — precargado en el input editable (fix).
    expect(screen.getByDisplayValue("227480.00")).toBeInTheDocument();
    // IVA = 227,480.00 * 16% = 36,396.80
    expect(screen.getByDisplayValue("36396.80")).toBeInTheDocument();
    // Total = 227,480.00 + 36,396.80 = 263,876.80 (sigue calculado, de solo lectura)
    expect(screen.getByText("$263,876.80")).toBeInTheDocument();
  });

  it("quitar una orden de la lista la regresa al buscador y baja el Subtotal", () => {
    ordenesFacturablesMock.mockReturnValue([OC_A, OC_B]);
    const { container } = render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirVendedor(container);
    agregarOrden("OC-2025-0041");
    agregarOrden("OC-2025-0055");
    expect(screen.getByDisplayValue("227480.00")).toBeInTheDocument();

    fireEvent.click(screen.getAllByTitle("Quitar de esta factura")[0]);

    expect(screen.queryByDisplayValue("227480.00")).toBeNull();
    expect(screen.getByText("$50,000.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("50000.00")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio y agregar…"), { target: { value: "0041" } });
    expect(screen.getByText("OC-2025-0041 — Grupo Bimbo")).toBeInTheDocument();
  });

  it("cambiar de vendedor limpia las órdenes ya elegidas", () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "vd-1" ? [OC_A] : [OC_B]));
    const { container } = render(<FacturaVendedorForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirVendedor(container, "vd-1");
    agregarOrden("OC-2025-0041");
    expect(screen.getByText("$177,480.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("177480.00")).toBeInTheDocument();

    elegirVendedor(container, "vd-2");
    expect(screen.queryByText("$177,480.00")).toBeNull();
    expect(screen.queryByDisplayValue("177480.00")).toBeNull();
    expect(screen.getByText("Sin órdenes agregadas todavía.")).toBeInTheDocument();
  });

  it("al guardar con órdenes elegidas, onSubmit recibe ordenes_ids con ambas", async () => {
    ordenesFacturablesMock.mockReturnValue([OC_A, OC_B]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaVendedorForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirVendedor(container);
    agregarOrden("OC-2025-0041");
    agregarOrden("OC-2025-0055");

    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const payload = onSubmit.mock.calls[0][0];
    expect(payload.vendedor_id).toBe("vd-1");
    expect(payload.ordenes_ids).toEqual(["oc-a", "oc-b"]);
  });

  it("fix: en edición, el vendedor se puede reasignar y la sección de asignación precarga lo ya asignado", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    render(
      <FacturaVendedorForm
        isEdit
        defaultValues={{
          vendedor_id: "vd-1",
          folio_factura_vendedor: "VE-2025-0287",
          fecha_factura_vendedor: "2025-06-08",
          // Fix: en edición, Subtotal/IVA ya NO se recalculan solos — arrancan en lo
          // ya guardado (aquí, coincide con la comisión de la única OI asignada).
          monto_factura_vendedor: "177480.00",
          iva_factura_vendedor: "28396.80",
        }}
        ordenesIniciales={[
          {
            id: "fvo-1",
            factura_vendedor_id: "fv-1",
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
    expect(await screen.findByDisplayValue("Carmen Aristegui")).toBeEnabled();
    expect(screen.getByText("OC-2025-0041")).toBeInTheDocument();
    expect(screen.getByText("$177,480.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("177480.00")).toBeInTheDocument();
  });

  it("ADR-264: en edición, manda el id de la propia factura para que el combo no excluya sus propias órdenes", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    render(
      <FacturaVendedorForm
        isEdit
        defaultValues={{
          vendedor_id: "vd-1",
          folio_factura_vendedor: "VE-2025-0287",
          fecha_factura_vendedor: "2025-06-08",
        }}
        facturaVendedorIdActual="fv-1"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await screen.findByDisplayValue("Carmen Aristegui");
    expect(ordenesFacturablesMock).toHaveBeenCalledWith("vd-1", "fv-1");
  });

  it("en edición, cambiar de vendedor limpia las órdenes ya asignadas (eran del vendedor anterior)", async () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "vd-1" ? [OC_A] : [OC_B]));
    const { container } = render(
      <FacturaVendedorForm
        isEdit
        defaultValues={{
          vendedor_id: "vd-1",
          folio_factura_vendedor: "VE-2025-0287",
          fecha_factura_vendedor: "2025-06-08",
        }}
        ordenesIniciales={[
          {
            id: "fvo-1",
            factura_vendedor_id: "fv-1",
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
    await screen.findByDisplayValue("Carmen Aristegui");
    expect(screen.getByText("OC-2025-0041")).toBeInTheDocument();

    elegirVendedor(container, "vd-2");
    expect(screen.queryByText("OC-2025-0041")).toBeNull();
    expect(screen.getByText("Sin órdenes agregadas todavía.")).toBeInTheDocument();
  });

  it("fix: en edición, precarga las órdenes ya asignadas y sobreviven al doble-render de StrictMode", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    const onSubmit = vi.fn();
    render(
      <StrictMode>
        <FacturaVendedorForm
          isEdit
          defaultValues={{
            vendedor_id: "vd-1",
            folio_factura_vendedor: "VE-2025-0287",
            fecha_factura_vendedor: "2025-06-08",
            monto_factura_vendedor: "177480.00",
            iva_factura_vendedor: "28396.80",
          }}
          ordenesIniciales={[
            {
              id: "fvo-1",
              factura_vendedor_id: "fv-1",
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
    await screen.findByDisplayValue("Carmen Aristegui");
    expect(screen.getByText("$177,480.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("177480.00")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].vendedor_id).toBe("vd-1");
    expect(onSubmit.mock.calls[0][0].ordenes_ids).toEqual(["oc-a"]);
  });

  it("fix: cargar el XML precarga Subtotal/IVA y siguen siendo editables después", async () => {
    leerCfdiMock.mockResolvedValue({
      ok: true,
      motivo: null,
      subtotal: "957.00",
      iva: "150.00",
      total: "1107.00",
      rfc_emisor: "PBA260101XX1",
      folio: "0071",
    });
    const onSubmit = vi.fn();
    const { container } = render(<FacturaVendedorForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirVendedor(container);

    const xml = new File(["<cfdi/>"], "factura.xml", { type: "application/xml" });
    const inputs = container.querySelectorAll('input[type="file"]');
    const inputXml = Array.from(inputs).find((i) => i.getAttribute("accept") === ".xml")!;
    fireEvent.change(inputXml, { target: { files: [xml] } });

    expect(await screen.findByDisplayValue("957.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("150.00")).toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue("150.00"), { target: { value: "153.12" } });
    expect(screen.getByDisplayValue("153.12")).toBeInTheDocument();

    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].monto_factura_vendedor).toBe("957.00");
    expect(onSubmit.mock.calls[0][0].iva_factura_vendedor).toBe("153.12");
  });

  it("subir el PDF llama a adjuntosFacturacionApi.subir con el tipo correcto y lo incluye al guardar", async () => {
    subirMock.mockResolvedValue({
      ref: "facturacion/proveedor/vendedor/pdf/abc_factura.pdf",
      nombre_archivo: "factura.pdf",
    });
    ordenesFacturablesMock.mockReturnValue([OC_A]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaVendedorForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirVendedor(container);
    agregarOrden("OC-2025-0041");

    const archivo = new File(["contenido"], "factura.pdf", { type: "application/pdf" });
    const inputArchivo = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(inputArchivo, { target: { files: [archivo] } });

    await waitFor(() => expect(subirMock).toHaveBeenCalledWith("factura_vendedor_pdf", archivo));
    const texto = await screen.findByText("factu...pdf");
    expect(texto).toHaveAttribute("title", "facturacion/proveedor/vendedor/pdf/abc_factura.pdf");

    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].archivo_pdf_path).toBe(
      "facturacion/proveedor/vendedor/pdf/abc_factura.pdf",
    );
  });
});
