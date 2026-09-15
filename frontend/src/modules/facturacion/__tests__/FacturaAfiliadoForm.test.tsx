/** "Asignación a órdenes estación" de FacturaAfiliado (alta Y edición): el combo "Folio
 * de la Orden Interna" solo lista las OI `cerrada` del afiliado elegido, permite agregar
 * VARIAS (una por una, ya no se auto-llenan Subtotal/IVA al elegir), muestra en vivo
 * Asignado (suma de `importe_emisora` de las elegidas) y Sin Asignar (Subtotal capturado
 * − Asignado), y se limpia si se cambia de afiliado. Al editar, además, se puede
 * reasignar el afiliado y la lista llega precargada con lo ya asignado. También cubre la
 * subida de PDF/XML de la factura.
 */

import { StrictMode } from "react";

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FacturaAfiliadoForm } from "../facturaAfiliado/components/FacturaAfiliadoForm";
import type { OrdenEstacionFacturableAfiliado } from "../types";

const subirMock = vi.fn();
const ordenesFacturablesMock = vi.fn();

vi.mock("../hooks", () => ({
  useAfiliados: () => ({
    data: [
      { id: "af-1", etiqueta: "Radiorama Jalisco SA de CV" },
      { id: "af-2", etiqueta: "Grupo ACIR SA de CV" },
    ],
  }),
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

const OE_A: OrdenEstacionFacturableAfiliado = {
  orden_estacion_id: "oe-a",
  folio_orden_estacion: "OE-2026-0041A",
  nombre_estacion: "XHMT-FM",
  importe_emisora: "285600.00",
  iva_emisora: "45696.00",
  total_emisora: "331296.00",
};

const OE_B: OrdenEstacionFacturableAfiliado = {
  orden_estacion_id: "oe-b",
  folio_orden_estacion: "OE-2026-0041B",
  nombre_estacion: "XHRC-FM",
  importe_emisora: "168000.00",
  iva_emisora: "26880.00",
  total_emisora: "194880.00",
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

function elegirAfiliado(container: HTMLElement, id = "af-1") {
  fireEvent.change(campoTrasEtiqueta<HTMLSelectElement>(container, "Afiliado"), { target: { value: id } });
}

function agregarOrdenEstacion(folio: string) {
  const buscador = screen.getByPlaceholderText("Buscar por folio y agregar…");
  fireEvent.change(buscador, { target: { value: folio } });
  fireEvent.mouseDown(screen.getByText((c) => c.startsWith(folio)));
}

describe("FacturaAfiliadoForm — Asignación a órdenes estación", () => {
  it("el combo aparece deshabilitado hasta elegir un afiliado", () => {
    render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByPlaceholderText("Buscar por folio y agregar…")).toBeDisabled();
  });

  it("al elegir un afiliado, el combo se habilita y solo lista sus OI cerradas", () => {
    ordenesFacturablesMock.mockReturnValue([OE_A]);
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container);

    const buscador = screen.getByPlaceholderText("Buscar por folio y agregar…");
    expect(buscador).toBeEnabled();
    fireEvent.change(buscador, { target: { value: "0041" } });
    expect(screen.getByText("OE-2026-0041A — XHMT-FM")).toBeInTheDocument();
  });

  it("al elegir un folio se agrega a la lista (no autollena Subtotal/IVA) y desaparece del buscador", () => {
    ordenesFacturablesMock.mockReturnValue([OE_A, OE_B]);
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    agregarOrdenEstacion("OE-2026-0041A");

    // La OE elegida aparece en la lista de asignadas (y también en la tarjeta
    // "Asignado", que por ahora coincide con esta única OE — de ahí las dos veces).
    // `fmtMoneda` da formato de moneda MXN ("$285,600.00"), no el string crudo.
    expect(screen.getAllByText("$285,600.00").length).toBe(2);
    // ...y ya no se ofrece de nuevo en el buscador.
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio y agregar…"), { target: { value: "0041" } });
    expect(screen.queryByText("OE-2026-0041A — XHMT-FM")).toBeNull();
    expect(screen.getByText("OE-2026-0041B — XHRC-FM")).toBeInTheDocument();

    // Subtotal/IVA no se tocan solos: siguen en su default.
    const subtotal = campoTrasEtiqueta(container, "Subtotal");
    const iva = campoTrasEtiqueta(container, "IVA");
    expect(subtotal.value).toBe("");
    expect(iva.value).toBe("0");
  });

  it("Asignado suma el importe_emisora de las OE elegidas; Sin Asignar resta contra el Subtotal capturado", () => {
    ordenesFacturablesMock.mockReturnValue([OE_A, OE_B]);
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    agregarOrdenEstacion("OE-2026-0041A");
    agregarOrdenEstacion("OE-2026-0041B");

    // Asignado = 285600.00 + 168000.00
    expect(screen.getByText("$453,600.00")).toBeInTheDocument();

    fireEvent.change(campoTrasEtiqueta(container, "Subtotal"), { target: { value: "453600.00" } });
    // Sin Asignar = 453600.00 - 453600.00 = 0.00
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("quitar una OE de la lista la regresa al buscador y baja el Asignado", () => {
    ordenesFacturablesMock.mockReturnValue([OE_A, OE_B]);
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    agregarOrdenEstacion("OE-2026-0041A");
    agregarOrdenEstacion("OE-2026-0041B");
    expect(screen.getByText("$453,600.00")).toBeInTheDocument();

    fireEvent.click(screen.getAllByTitle("Quitar de esta factura")[0]);

    // Solo queda OE-B asignada: Asignado baja a su propio importe_emisora (aparece dos
    // veces: en la tarjeta "Asignado" y en el renglón de la OE).
    expect(screen.queryByText("$453,600.00")).toBeNull();
    expect(screen.getAllByText("$168,000.00").length).toBe(2);
    // OE-A vuelve a estar disponible en el buscador.
    fireEvent.change(screen.getByPlaceholderText("Buscar por folio y agregar…"), { target: { value: "0041" } });
    expect(screen.getByText("OE-2026-0041A — XHMT-FM")).toBeInTheDocument();
  });

  it("cambiar de afiliado limpia las OI ya elegidas", () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "af-1" ? [OE_A] : [OE_B]));
    const { container } = render(<FacturaAfiliadoForm onSubmit={vi.fn()} onCancel={vi.fn()} />);
    elegirAfiliado(container, "af-1");
    agregarOrdenEstacion("OE-2026-0041A");
    expect(screen.getAllByText("$285,600.00").length).toBe(2);

    elegirAfiliado(container, "af-2");
    expect(screen.queryByText("$285,600.00")).toBeNull();
    expect(screen.getByText("Sin órdenes internas agregadas todavía.")).toBeInTheDocument();
  });

  it("al guardar con folios elegidos, onSubmit recibe ordenes_estacion_ids con ambos", async () => {
    ordenesFacturablesMock.mockReturnValue([OE_A, OE_B]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAfiliadoForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    agregarOrdenEstacion("OE-2026-0041A");
    agregarOrdenEstacion("OE-2026-0041B");

    fireEvent.change(campoTrasEtiqueta(container, "Folio de la emisora"), { target: { value: "EMI-9000" } });
    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.change(campoTrasEtiqueta(container, "Subtotal"), { target: { value: "453600.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    // `handleSubmit` de react-hook-form + zodResolver valida de forma asíncrona.
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].ordenes_estacion_ids).toEqual(["oe-a", "oe-b"]);
  });

  it("sin elegir ningún folio, onSubmit recibe ordenes_estacion_ids vacío (la asignación sigue siendo opcional)", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
    const onSubmit = vi.fn();
    const { container } = render(<FacturaAfiliadoForm onSubmit={onSubmit} onCancel={vi.fn()} />);
    elegirAfiliado(container);
    fireEvent.change(campoTrasEtiqueta(container, "Folio de la emisora"), { target: { value: "EMI-9001" } });
    fireEvent.change(campoTrasEtiqueta(container, "Fecha de la factura"), { target: { value: "2026-04-10" } });
    fireEvent.change(campoTrasEtiqueta(container, "Subtotal"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].ordenes_estacion_ids).toEqual([]);
  });

  it("fix: en edición, el afiliado se puede reasignar y la sección de asignación también aparece", async () => {
    ordenesFacturablesMock.mockReturnValue([]);
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
    expect(await screen.findByDisplayValue("Radiorama Jalisco SA de CV")).toBeEnabled();
    expect(screen.getByText("Asignación a órdenes estación")).toBeInTheDocument();
    expect(screen.getByText("Folio de la Orden Interna")).toBeInTheDocument();
  });

  it("fix: en edición, precarga las OI ya asignadas y sobreviven al doble-render de StrictMode", async () => {
    // Regresión real: un `useRef` de "¿ya corrió el efecto?" (en vez de comparar
    // contra el afiliado con el que se montó) se ve engañado por el doble
    // montaje/efecto que React StrictMode hace a propósito en desarrollo — el
    // formulario SÍ usa `<StrictMode>` en `main.tsx`, así que hay que probarlo así
    // para que esta regresión no vuelva a colarse sin que la prueba la note.
    ordenesFacturablesMock.mockReturnValue([OE_A, OE_B]);
    const onSubmit = vi.fn();
    render(
      <StrictMode>
        <FacturaAfiliadoForm
          isEdit
          defaultValues={{
            afiliado_id: "af-1",
            factura_emisora: "EMI-2025-118",
            fecha_factura_afiliado: "2025-04-10",
            monto_factura_afiliado: "453600.00",
            iva_factura_afiliado: "72576.00",
          }}
          asignacionesIniciales={[
            {
              id: "asig-1",
              factura_afiliado_id: "fa-1",
              orden_estacion_id: "oe-a",
              monto_asignado: "285600.00",
              notas_asignacion: null,
              folio_orden_estacion: "OE-2026-0041A",
              nombre_estacion: "XHMT-FM",
            },
          ]}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
        />
      </StrictMode>,
    );
    await screen.findByDisplayValue("Radiorama Jalisco SA de CV");
    expect(screen.getByText("OE-2026-0041A")).toBeInTheDocument();
    // Aparece dos veces: en el renglón de la OE y en la tarjeta "Asignado" (coincide
    // porque es la única seleccionada).
    expect(screen.getAllByText("$285,600.00").length).toBe(2);

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].afiliado_id).toBe("af-1");
    expect(onSubmit.mock.calls[0][0].ordenes_estacion_ids).toEqual(["oe-a"]);
  });

  it("en edición, cambiar de afiliado limpia las OI ya asignadas (eran del afiliado anterior)", async () => {
    ordenesFacturablesMock.mockImplementation((id: string) => (id === "af-1" ? [OE_A] : [OE_B]));
    const { container } = render(
      <FacturaAfiliadoForm
        isEdit
        defaultValues={{
          afiliado_id: "af-1",
          factura_emisora: "EMI-2025-118",
          fecha_factura_afiliado: "2025-04-10",
          monto_factura_afiliado: "334904.00",
          iva_factura_afiliado: "53584.64",
        }}
        asignacionesIniciales={[
          {
            id: "asig-1",
            factura_afiliado_id: "fa-1",
            orden_estacion_id: "oe-a",
            monto_asignado: "285600.00",
            notas_asignacion: null,
            folio_orden_estacion: "OE-2026-0041A",
            nombre_estacion: "XHMT-FM",
          },
        ]}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    await screen.findByDisplayValue("Radiorama Jalisco SA de CV");
    expect(screen.getByText("OE-2026-0041A")).toBeInTheDocument();

    elegirAfiliado(container, "af-2");
    expect(screen.queryByText("OE-2026-0041A")).toBeNull();
    expect(screen.getByText("Sin órdenes internas agregadas todavía.")).toBeInTheDocument();
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
