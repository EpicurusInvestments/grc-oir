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

// ADR-225: "Forma de pago"/"Cuenta contable" se reutilizan de F2 (`../hooks` las
// re-exporta desde `@/modules/facturacion/hooks`) — se mockea ESE módulo directamente,
// sin pasar por su API real.
vi.mock("@/modules/facturacion/hooks", () => ({
  useCuentasContables: () => ({
    data: [{ id: "cc-1", etiqueta: "4100-001 · Ingresos" }],
  }),
  useFormasDePago: () => ({
    data: [{ id: "01", etiqueta: "01 · Efectivo" }],
  }),
}));

const cobranza: CobranzaFactura = {
  cobranza_id: "cb-1",
  factura_id: "f-1",
  anunciante_id: "an-1",
  agencia_id: null,
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
  ultimo_numero_pago: null,
  siguiente_numero_pago: "1",
};

/** ADR-225: selecciona Forma de pago y Cuenta contable (obligatorios, además de Método
 *  de pago) — orden en el DOM: Método de pago, Forma de pago, Cuenta contable. */
function completarCamposNuevos(container: HTMLElement) {
  const selects = container.querySelectorAll("select.fsel");
  fireEvent.change(selects[1], { target: { value: "01" } });
  fireEvent.change(selects[2], { target: { value: "cc-1" } });
}

function renderForm(onConfirm = vi.fn(), onCancel = vi.fn(), numeroPagoSugerido = "1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <RegistrarPagoForm
        cobranza={cobranza}
        numeroFactura="B-0010023454343"
        anunciante="Grupo Femsa"
        numeroPagoSugerido={numeroPagoSugerido}
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
    expect(boton).toBeDisabled(); // ADR-225: aún faltan Forma de pago/Cuenta contable.

    await screen.findByText("01 · Efectivo");
    completarCamposNuevos(container);
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
    completarCamposNuevos(container);
    expect(screen.getByRole("button", { name: "Registrar pago" })).toBeDisabled();
  });

  it("con los campos válidos, 'Registrar pago' llama a onConfirm con los datos capturados", async () => {
    const { container, onConfirm } = renderForm();
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "500000" } });
    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });
    completarCamposNuevos(container);

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago" }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        monto_aplicado: "500000",
        metodo_pago_clave: "03",
        referencia_pago: "SPEI-12345678",
        forma_pago_clave: "01",
        cuenta_contable_id: "cc-1",
      }),
    );
  });
});

// ADR-256 (petición del usuario, "NEW FEATURE"): "Pagado en sistema externo" — solo
// identifica el pago, sin ningún efecto hoy (mismo criterio que ADR-248).
describe("ADR-256: checkbox 'Pagado en sistema externo'", () => {
  it("nace sin marcar y manda `false` si no se toca", async () => {
    const { container, onConfirm } = renderForm();
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "500000" } });
    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });
    completarCamposNuevos(container);

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago" }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ pagado_en_sistema_externo: false }),
    );
  });

  it("al marcarlo, manda `true` en el payload", async () => {
    const { container, onConfirm } = renderForm();
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "500000" } });
    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });
    completarCamposNuevos(container);
    fireEvent.click(screen.getByLabelText("Pagado en sistema externo"));

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago" }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ pagado_en_sistema_externo: true }),
    );
  });
});

// ADR-226 (petición del usuario): "Número de pago" ya no se captura a mano.
describe("'Número de pago' se precarga calculado y de solo lectura", () => {
  it("muestra el valor sugerido por el padre y no permite editarlo", () => {
    renderForm(vi.fn(), vi.fn(), "3");
    const campo = screen.getByDisplayValue("3") as HTMLInputElement;
    expect(campo).toBeDisabled();
    fireEvent.change(campo, { target: { value: "99" } });
    expect(campo).toHaveValue("3"); // deshabilitado: el intento de cambio no aplica.
  });

  it("envía el valor sugerido tal cual en el payload, sin que el usuario lo toque", async () => {
    const { container, onConfirm } = renderForm(vi.fn(), vi.fn(), "3");
    fireEvent.change(screen.getByPlaceholderText("991800.00"), { target: { value: "500000" } });
    await screen.findByText("03 · Transferencia");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-12345678" },
    });
    completarCamposNuevos(container);

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago" }));

    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ numero_pago: "3" }));
  });
});
