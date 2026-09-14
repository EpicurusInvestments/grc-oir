/** Combo "Folio de la Orden Interna" del alta de FacturaAfiliado: solo lista las OI
 * `cerrada` del afiliado elegido, permite buscar por folio, precarga Subtotal/IVA al
 * elegir una (quedan editables), y solo aplica al alta (no en edición). También cubre
 * la subida de PDF/XML de la factura.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FacturaAfiliadoForm } from "../facturaAfiliado/components/FacturaAfiliadoForm";
import type { OrdenEstacionFacturableAfiliado } from "../types";

const subirMock = vi.fn();
const ordenesFacturablesMock = vi.fn();

vi.mock("../hooks", () => ({
  useAfiliados: () => ({ data: [{ id: "af-1", etiqueta: "Radiorama Jalisco SA de CV" }] }),
  useOrdenesFacturablesAfiliado: (afiliadoId: string | null) => ({
    data: afiliadoId ? ordenesFacturablesMock(afiliadoId) : [],
  }),
}));

vi.mock("../api", () => ({
  adjuntosFacturacionApi: {
    subir: (...args: unknown[]) => subirMock(...args),
    ver: vi.fn(),
  },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
}));

const OE_CERRADA: OrdenEstacionFacturableAfiliado = {
  orden_estacion_id: "oe-1",
  folio_orden_estacion: "OE-2026-0041A",
  nombre_estacion: "XHMT-FM",
  importe_emisora: "7000.00",
  iva_emisora: "1120.00",
  total_emisora: "8120.00",
};

/** Campo que sigue a una etiqueta `.fl` (mismo patrón que `domHelpers.ts` de `ordenes/`,
 *  duplicado aquí porque `facturacion/__tests__` no tiene ese helper compartido todavía). */
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

function elegirAfiliado(container: HTMLElement) {
  fireEvent.change(campoTrasEtiqueta<HTMLSelectElement>(container, "Afiliado"), { target: { value: "af-1" } });
}

describe("FacturaAfiliadoForm — combo Folio de la Orden Interna", () => {
  it("el combo aparece deshabilitado hasta elegir un afiliado", () => {
    render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByPlaceholderText("Buscar por folio…")).toBeDisabled();
  });

  it("al elegir un afiliado, el combo se habilita y solo lista sus OI cerradas", () => {
    ordenesFacturablesMock.mockReturnValue([OE_CERRADA]);
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container);

    const buscador = screen.getByPlaceholderText("Buscar por folio…");
    expect(buscador).toBeEnabled();
    fireEvent.change(buscador, { target: { value: "0041" } });
    expect(screen.getByText("OE-2026-0041A — XHMT-FM")).toBeInTheDocument();
  });

  it("al elegir un folio, precarga Subtotal/IVA — y siguen siendo editables", () => {
    ordenesFacturablesMock.mockReturnValue([OE_CERRADA]);
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container);

    const buscador = screen.getByPlaceholderText("Buscar por folio…");
    fireEvent.change(buscador, { target: { value: "0041" } });
    fireEvent.mouseDown(screen.getByText("OE-2026-0041A — XHMT-FM"));

    const subtotal = campoTrasEtiqueta(container, "Subtotal");
    const iva = campoTrasEtiqueta(container, "IVA");
    expect(subtotal.value).toBe("7000.00");
    expect(iva.value).toBe("1120.00");

    // No quedan de solo lectura: se pueden seguir editando tras la precarga.
    expect(subtotal).toBeEnabled();
    fireEvent.change(subtotal, { target: { value: "6500.00" } });
    expect(subtotal.value).toBe("6500.00");
  });

  it("al guardar con un folio elegido, onSubmit recibe orden_estacion_id", async () => {
    ordenesFacturablesMock.mockReturnValue([OE_CERRADA]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAfiliadoForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio…"), { target: { value: "0041" } });
    fireEvent.mouseDown(screen.getByText("OE-2026-0041A — XHMT-FM"));

    fireEvent.change(campoTrasEtiqueta(container, "Folio de la emisora"), { target: { value: "EMI-9000" } });
    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    // `handleSubmit` de react-hook-form + zodResolver valida de forma asíncrona.
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].orden_estacion_id).toBe("oe-1");
  });

  it("sin elegir ningún folio, onSubmit recibe orden_estacion_id null (la asignación sigue siendo opcional)", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAfiliadoForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    fireEvent.change(campoTrasEtiqueta(container, "Folio de la emisora"), { target: { value: "EMI-9001" } });
    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.change(campoTrasEtiqueta(container, "Subtotal"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].orden_estacion_id).toBeNull();
  });

  it("en edición, el combo de Folio de la Orden Interna no se muestra", () => {
    render(
      <FacturaAfiliadoForm
        isEdit
        defaultValues={{
          afiliado_id: "af-1",
          factura_emisora: "EMI-2025-118",
          fecha_factura_afiliado: "2025-04-10",
          monto_factura_afiliado: "334904.00",
          iva_factura_afiliado: "53584.64",
        }}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByText("Folio de la Orden Interna")).toBeNull();
  });

  it("subir el PDF llama a adjuntosFacturacionApi.subir con el tipo correcto y refleja el archivo", async () => {
    subirMock.mockResolvedValue({ ref: "facturacion/proveedor/afiliado/pdf/abc_factura.pdf", nombre_archivo: "factura.pdf" });
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    const archivo = new File(["contenido"], "factura.pdf", { type: "application/pdf" });
    const inputArchivo = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(inputArchivo, { target: { files: [archivo] } });

    await waitFor(() => expect(subirMock).toHaveBeenCalledWith("factura_afiliado_pdf", archivo));
    expect(await screen.findByText("facturacion/proveedor/afiliado/pdf/abc_factura.pdf")).toBeInTheDocument();
  });
});
