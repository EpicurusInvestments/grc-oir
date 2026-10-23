/** Fix (petición del usuario, con captura): "Registrar pago" solo validaba AL HACER
 * CLIC — el botón mismo siempre estaba habilitado, sin señal visual de qué faltaba (y en
 * algún momento de la captura ni siquiera aparecía). Ahora se deshabilita en vivo
 * mientras no estén los 4 campos obligatorios, pero NUNCA desaparece del DOM.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RegistrarPagoForm } from "../cobranzaFactura/components/RegistrarPagoForm";
import type { CobranzaFactura } from "../types";

vi.mock("../api", () => ({
  metodosDePago: vi.fn().mockResolvedValue([{ id: "03", etiqueta: "03 · Transferencia" }]),
  adjuntosCobranzaApi: { subir: vi.fn(), ver: vi.fn() },
  nombreDeAdjuntoCobranzaRef: (ref: string) => ref,
}));

const cobranza: CobranzaFactura = {
  cobranza_id: "cb-1",
  factura_id: "f-1",
  anunciante_id: "an-1",
  metodo_pago_clave: "03",
  dias_credito: 30,
  fecha_estimada_cobro: "2026-11-01",
  fecha_cobro: null,
  estatus_cobro: "pendiente",
  comentarios_cobranza: null,
  created_by: "dev.admin",
  created_at: "2026-10-01",
  updated_at: null,
  importe_cobrado: "0.00",
  importe_pendiente_cobro: "991800.00",
  vencida: false,
  numero_factura: "B-0010023454343",
};

function renderForm(onConfirm = vi.fn(), onCancel = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <RegistrarPagoForm
        cobranza={cobranza}
        numeroFactura="B-0010023454343"
        anunciante="Grupo Femsa"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onConfirm, onCancel };
}

describe("Fix: 'Registrar pago' se deshabilita en vivo en vez de desaparecer", () => {
  it("nace deshabilitado (faltan campos) pero SIEMPRE presente en el DOM", () => {
    renderForm();
    expect(screen.getByRole("button", { name: "Registrar pago" })).toBeDisabled();
  });

  it("se habilita al completar los 4 campos obligatorios, y vuelve a deshabilitarse si uno se borra", async () => {
    const { container } = renderForm();
    const boton = screen.getByRole("button", { name: "Registrar pago" });

    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "500000" } });
    expect(boton).toBeDisabled();

    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    expect(boton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });
    expect(boton).toBeEnabled();

    // Borrar un campo ya lleno lo vuelve a deshabilitar — nunca lo oculta.
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "" } });
    expect(boton).toBeDisabled();
    expect(boton).toBeInTheDocument();
  });

  it("un monto mayor al pendiente deja el botón deshabilitado", async () => {
    const { container } = renderForm();
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "9999999" } });
    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });
    expect(screen.getByRole("button", { name: "Registrar pago" })).toBeDisabled();
  });

  it("con los 4 campos válidos, 'Registrar pago' llama a onConfirm con los datos capturados", async () => {
    const { container, onConfirm } = renderForm();
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "500000" } });
    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago" }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        monto_aplicado: "500000",
        metodo_pago_clave: "03",
        referencia_pago: "SPEI-12345678",
      }),
    );
  });
});
