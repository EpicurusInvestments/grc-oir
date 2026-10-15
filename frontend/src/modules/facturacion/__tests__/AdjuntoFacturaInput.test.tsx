/** ADR-205 (petición del usuario, corrige un bug real): cada campo de
 * `AdjuntoFacturaInput` es XML o PDF del CFDI, nunca ambos — antes el selector nativo de
 * archivos (y la validación del front) aceptaba las 9 extensiones de TODO el módulo de
 * Facturación por igual, así que "Cargar XML del CFDI" dejaba elegir un PDF (o
 * cualquier otro formato) desde el explorador de Windows.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdjuntoFacturaInput } from "../facturaCliente/components/AdjuntoFacturaInput";

const subirMock = vi.fn();

vi.mock("../api", () => ({
  adjuntosFacturacionApi: {
    subir: (...args: unknown[]) => subirMock(...args),
    ver: vi.fn(),
    verEnVisor: vi.fn(),
  },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
}));

function elegirArchivo(input: HTMLElement, nombre: string) {
  const archivo = new File(["contenido"], nombre, { type: "application/octet-stream" });
  fireEvent.change(input, { target: { files: [archivo] } });
}

describe("AdjuntoFacturaInput", () => {
  beforeEach(() => {
    subirMock.mockReset();
    subirMock.mockResolvedValue({ ref: "facturacion/clientes/xml/abc_cfdi.xml" });
  });

  it('tipo "_xml" solo acepta .xml en el selector nativo (accept)', () => {
    const { container } = render(
      <AdjuntoFacturaInput tipo="cfdi_xml" placeholder="Cargar XML del CFDI" value={null} onChange={vi.fn()} />,
    );
    expect(container.querySelector('input[type="file"]')).toHaveAttribute("accept", ".xml");
  });

  it('tipo "_pdf" solo acepta .pdf en el selector nativo (accept)', () => {
    const { container } = render(
      <AdjuntoFacturaInput tipo="cfdi_pdf" placeholder="Cargar PDF de la factura" value={null} onChange={vi.fn()} />,
    );
    expect(container.querySelector('input[type="file"]')).toHaveAttribute("accept", ".pdf");
  });

  it("elegir un .pdf en el campo de XML lo rechaza sin llegar a subirlo", () => {
    const { container } = render(
      <AdjuntoFacturaInput tipo="cfdi_xml" placeholder="Cargar XML del CFDI" value={null} onChange={vi.fn()} />,
    );
    elegirArchivo(container.querySelector('input[type="file"]')!, "factura.pdf");

    expect(screen.getByText("Extensión no permitida. Usa: .xml.")).toBeInTheDocument();
    expect(subirMock).not.toHaveBeenCalled();
  });

  it("elegir un .xml válido en el campo de XML sí lo sube", async () => {
    const onChange = vi.fn();
    const { container } = render(
      <AdjuntoFacturaInput tipo="cfdi_xml" placeholder="Cargar XML del CFDI" value={null} onChange={onChange} />,
    );
    elegirArchivo(container.querySelector('input[type="file"]')!, "cfdi.xml");

    await vi.waitFor(() => expect(subirMock).toHaveBeenCalledWith("cfdi_xml", expect.any(File)));
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith("facturacion/clientes/xml/abc_cfdi.xml"));
  });

  it("elegir un .docx en el campo de PDF lo rechaza con el mensaje correcto", () => {
    const { container } = render(
      <AdjuntoFacturaInput tipo="cfdi_pdf" placeholder="Cargar PDF de la factura" value={null} onChange={vi.fn()} />,
    );
    elegirArchivo(container.querySelector('input[type="file"]')!, "factura.docx");

    expect(screen.getByText("Extensión no permitida. Usa: .pdf.")).toBeInTheDocument();
    expect(subirMock).not.toHaveBeenCalled();
  });

  // ADR-207 (petición del usuario, corrige un bug real): un nombre largo desbordaba el
  // `.dropzone` (scroll horizontal en todo el panel) — se trunca a un largo FIJO (5
  // letras + "…" + extensión), con el nombre completo en un tooltip nativo (`title`).
  it("un nombre de archivo largo se trunca a 5 letras + extensión, con el nombre completo en el title", () => {
    render(
      <AdjuntoFacturaInput
        tipo="cfdi_xml"
        placeholder="Cargar XML del CFDI"
        value="facturacion/clientes/xml/abc_factura_prueba_corregida.xml"
        onChange={vi.fn()}
      />,
    );
    const texto = screen.getByText("factu...xml");
    expect(texto).toHaveAttribute(
      "title",
      "facturacion/clientes/xml/abc_factura_prueba_corregida.xml",
    );
  });

  it("un nombre corto (5 letras o menos de raíz) no se trunca", () => {
    render(
      <AdjuntoFacturaInput tipo="cfdi_pdf" placeholder="Cargar PDF de la factura" value="abc.pdf" onChange={vi.fn()} />,
    );
    expect(screen.getByText("abc.pdf")).toBeInTheDocument();
  });
});
