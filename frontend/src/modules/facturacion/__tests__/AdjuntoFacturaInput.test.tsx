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
const leerCfdiMock = vi.fn();

vi.mock("../api", () => ({
  adjuntosFacturacionApi: {
    subir: (...args: unknown[]) => subirMock(...args),
    ver: vi.fn(),
    verEnVisor: vi.fn(),
  },
  cfdiApi: {
    leer: (...args: unknown[]) => leerCfdiMock(...args),
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
    leerCfdiMock.mockReset();
  });

  // Fix (petición del usuario): al elegir un XML, si se pasa `onArchivoXmlLeido`, se
  // lee el CFDI EN PARALELO a la subida normal — para precargar Subtotal/IVA en las
  // facturas de Agencia/Vendedor/Afiliado.
  describe("onArchivoXmlLeido (fix, precarga de Subtotal/IVA desde el XML)", () => {
    it("al elegir un .xml válido, lee el CFDI y entrega el resultado al callback", async () => {
      leerCfdiMock.mockResolvedValue({
        ok: true,
        motivo: null,
        subtotal: "957.00",
        iva: "153.12",
        total: "1110.12",
        rfc_emisor: "PBA260101XX1",
        folio: "0071",
      });
      const onArchivoXmlLeido = vi.fn();
      const { container } = render(
        <AdjuntoFacturaInput
          tipo="factura_agencia_xml"
          placeholder="Cargar XML de la factura"
          value={null}
          onChange={vi.fn()}
          onArchivoXmlLeido={onArchivoXmlLeido}
        />,
      );
      elegirArchivo(container.querySelector('input[type="file"]')!, "cfdi.xml");

      await vi.waitFor(() => expect(leerCfdiMock).toHaveBeenCalledWith(expect.any(File)));
      await vi.waitFor(() =>
        expect(onArchivoXmlLeido).toHaveBeenCalledWith(
          expect.objectContaining({ ok: true, subtotal: "957.00", iva: "153.12" }),
        ),
      );
      // La subida normal del archivo NO se bloquea ni depende de la lectura del CFDI.
      await vi.waitFor(() => expect(subirMock).toHaveBeenCalledWith("factura_agencia_xml", expect.any(File)));
    });

    it("si el XML no se puede leer como CFDI (ok: false), entrega null — no bloquea la subida", async () => {
      leerCfdiMock.mockResolvedValue({ ok: false, motivo: "no es un CFDI", subtotal: null, iva: null, total: null, rfc_emisor: null, folio: null });
      const onArchivoXmlLeido = vi.fn();
      const { container } = render(
        <AdjuntoFacturaInput
          tipo="factura_vendedor_xml"
          placeholder="Cargar XML de la factura"
          value={null}
          onChange={vi.fn()}
          onArchivoXmlLeido={onArchivoXmlLeido}
        />,
      );
      elegirArchivo(container.querySelector('input[type="file"]')!, "cfdi.xml");

      await vi.waitFor(() => expect(onArchivoXmlLeido).toHaveBeenCalledWith(null));
      await vi.waitFor(() => expect(subirMock).toHaveBeenCalled());
    });

    it("si la lectura del CFDI falla (red/servidor), entrega null sin tumbar la subida normal", async () => {
      leerCfdiMock.mockRejectedValue(new Error("red caída"));
      const onArchivoXmlLeido = vi.fn();
      const onChange = vi.fn();
      const { container } = render(
        <AdjuntoFacturaInput
          tipo="factura_afiliado_xml"
          placeholder="Cargar XML de la factura"
          value={null}
          onChange={onChange}
          onArchivoXmlLeido={onArchivoXmlLeido}
        />,
      );
      elegirArchivo(container.querySelector('input[type="file"]')!, "cfdi.xml");

      await vi.waitFor(() => expect(onArchivoXmlLeido).toHaveBeenCalledWith(null));
      await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith("facturacion/clientes/xml/abc_cfdi.xml"));
    });

    it("en el campo de PDF nunca se intenta leer como CFDI, aunque se pase el callback", async () => {
      subirMock.mockResolvedValue({ ref: "facturacion/proveedor/agencia/pdf/abc_factura.pdf" });
      const onArchivoXmlLeido = vi.fn();
      const { container } = render(
        <AdjuntoFacturaInput
          tipo="factura_agencia_pdf"
          placeholder="Cargar PDF de la factura"
          value={null}
          onChange={vi.fn()}
          onArchivoXmlLeido={onArchivoXmlLeido}
        />,
      );
      elegirArchivo(container.querySelector('input[type="file"]')!, "factura.pdf");

      await vi.waitFor(() => expect(subirMock).toHaveBeenCalled());
      expect(leerCfdiMock).not.toHaveBeenCalled();
      expect(onArchivoXmlLeido).not.toHaveBeenCalled();
    });

    it("sin `onArchivoXmlLeido`, elegir un XML no llama a leer el CFDI (comportamiento de siempre)", async () => {
      const { container } = render(
        <AdjuntoFacturaInput tipo="cfdi_xml" placeholder="Cargar XML del CFDI" value={null} onChange={vi.fn()} />,
      );
      elegirArchivo(container.querySelector('input[type="file"]')!, "cfdi.xml");

      await vi.waitFor(() => expect(subirMock).toHaveBeenCalled());
      expect(leerCfdiMock).not.toHaveBeenCalled();
    });
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
