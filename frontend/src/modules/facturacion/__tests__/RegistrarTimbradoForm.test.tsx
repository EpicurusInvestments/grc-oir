/** ADR-296 (petición del usuario): "Registrar respuesta del timbrado" (Factura, Nota de
 * Crédito — mismo componente para ambas) despliega la SERIE de la factura y, al cargar
 * el XML ya timbrado, precarga folio fiscal/fecha de timbrado/certificado desde su
 * Timbre Fiscal Digital — siempre sobreescribe esos 3 campos (el XML manda).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegistrarTimbradoForm } from "../facturaCliente/components/RegistrarTimbradoForm";

const subirMock = vi.fn();
const leerCfdiTimbradoMock = vi.fn();

vi.mock("../api", () => ({
  adjuntosFacturacionApi: {
    subir: (...args: unknown[]) => subirMock(...args),
    ver: vi.fn(),
    verEnVisor: vi.fn(),
  },
  cfdiApi: { leer: vi.fn() },
  cfdiTimbradoApi: {
    leer: (...args: unknown[]) => leerCfdiTimbradoMock(...args),
  },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
}));

function elegirArchivo(input: HTMLElement, nombre: string) {
  const archivo = new File(["contenido"], nombre, { type: "application/octet-stream" });
  fireEvent.change(input, { target: { files: [archivo] } });
}

describe("RegistrarTimbradoForm", () => {
  beforeEach(() => {
    subirMock.mockReset();
    subirMock.mockResolvedValue({ ref: "facturacion/clientes/xml/abc_cfdi.xml" });
    leerCfdiTimbradoMock.mockReset();
  });

  it("despliega la serie de la factura (prefijo antes del guion)", () => {
    render(
      <RegistrarTimbradoForm
        numeroFactura="NC-2026-11-04"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText("NC-2026-11-04")).toBeInTheDocument();
    expect(screen.getByText("NC")).toBeInTheDocument();
  });

  it("al cargar el XML ya timbrado, precarga folio fiscal, fecha de timbrado y certificado", async () => {
    leerCfdiTimbradoMock.mockResolvedValue({
      ok: true,
      motivo: null,
      folio_fiscal_sat: "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
      fecha_timbrado: "2026-11-24",
      serie_timbrado: "00000000000000000000",
    });
    const { container } = render(
      <RegistrarTimbradoForm
        numeroFactura="FMEX-1246"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const inputs = container.querySelectorAll('input[type="file"]');
    elegirArchivo(inputs[0], "cfdi_timbrado.xml"); // primer AdjuntoFacturaInput = XML

    await vi.waitFor(() =>
      expect(screen.getByDisplayValue("A1B2C3D4-E5F6-7890-ABCD-EF1234567890")).toBeInTheDocument(),
    );
    expect(screen.getByDisplayValue("00000000000000000000")).toBeInTheDocument();
  });

  it("si el XML no trae Timbre Fiscal Digital, no toca los campos (se siguen capturando a mano)", async () => {
    leerCfdiTimbradoMock.mockResolvedValue({
      ok: false,
      motivo: "todavía no está timbrado",
      folio_fiscal_sat: null,
      fecha_timbrado: null,
      serie_timbrado: null,
    });
    const { container } = render(
      <RegistrarTimbradoForm
        numeroFactura="FMEX-1246"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const inputs = container.querySelectorAll('input[type="file"]');
    elegirArchivo(inputs[0], "cfdi_sin_timbrar.xml");

    await vi.waitFor(() => expect(leerCfdiTimbradoMock).toHaveBeenCalled());
    const folioInput = screen.getByPlaceholderText(
      "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
    ) as HTMLInputElement;
    expect(folioInput.value).toBe("");
  });
});
