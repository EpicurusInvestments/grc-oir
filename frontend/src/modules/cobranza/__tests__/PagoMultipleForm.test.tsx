/** Pago múltiple (ADR-225, petición del usuario): un pago se reparte entre varias
 * facturas del mismo anunciante o agencia — cubre el modo "por Anunciante", el tablero
 * de montos en vivo, la validación de "no exceder el monto total" y que una factura ya
 * `cobrada` no se pueda marcar.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagoMultipleForm } from "../cobranzaFactura/components/PagoMultipleForm";
import type { CobranzaFactura } from "../types";

const listMock = vi.fn();
const crearMultipleMock = vi.fn();

const facturaPendiente: CobranzaFactura = {
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
  importe_pendiente_cobro: "6960.00",
  vencida: false,
  numero_factura: "A-0001",
  ultimo_numero_pago: null,
  siguiente_numero_pago: "2",
};

const facturaCobrada: CobranzaFactura = {
  ...facturaPendiente,
  cobranza_id: "cb-2",
  factura_id: "f-2",
  estatus_cobro: "cobrada",
  importe_cobrado: "11600.00",
  importe_pendiente_cobro: "0.00",
  numero_factura: "A-0002",
};

vi.mock("../api", () => ({
  cobranzaFacturaApi: { list: (params: unknown) => listMock(params) },
  pagoClienteApi: { crearMultiple: (data: unknown) => crearMultipleMock(data) },
  anunciantesInfo: vi.fn().mockResolvedValue([
    { anunciante_id: "an-1", nombre_comercial: "Grupo Bimbo", rfc_anunciante: "GBI971120AB3", dias_credito_default: 60 },
  ]),
  agenciasInfo: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/modules/facturacion/hooks", () => ({
  useCuentasContables: () => ({ data: [{ id: "cc-1", etiqueta: "4100-001 · Ingresos" }] }),
  useFormasDePago: () => ({ data: [{ id: "01", etiqueta: "01 · Efectivo" }] }),
}));

function renderForm(onCancelar = vi.fn(), onRegistrado = vi.fn()) {
  listMock.mockResolvedValue({
    items: [facturaPendiente, facturaCobrada],
    total: 2,
    page: 1,
    size: 100,
    pages: 1,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <PagoMultipleForm onCancelar={onCancelar} onRegistrado={onRegistrado} />
    </QueryClientProvider>,
  );
  return { ...utils, onCancelar, onRegistrado };
}

async function elegirAnunciante(container: HTMLElement) {
  const buscador = container.querySelector('input[placeholder="Selecciona…"]') as HTMLInputElement;
  fireEvent.change(buscador, { target: { value: "Bimbo" } });
  fireEvent.mouseDown(await screen.findByText("Grupo Bimbo"));
}

describe("PagoMultipleForm", () => {
  beforeEach(() => {
    listMock.mockReset();
    crearMultipleMock.mockReset();
  });

  // Petición del usuario: las facturas ya `cobrada` no tienen nada que pagar — se
  // excluyen de la lista por completo (antes aparecían con el checkbox deshabilitado).
  it("al elegir el anunciante, lista solo sus facturas pendientes/parciales — la ya cobrada no aparece", async () => {
    const { container } = renderForm();
    await elegirAnunciante(container);

    await screen.findByText("A-0001");
    expect(screen.queryByText("A-0002")).not.toBeInTheDocument();
    expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
  });

  it("marcar una factura precarga el pendiente como monto aplicado y actualiza el tablero", async () => {
    const { container } = renderForm();
    await elegirAnunciante(container);
    await screen.findByText("A-0001");

    fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "10000" } });
    const checkboxPendiente = container.querySelectorAll("tbody tr")[0].querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkboxPendiente);

    expect(screen.getAllByDisplayValue("6960.00")[0]).toBeInTheDocument();
    expect(screen.getByText("Monto asignado")).toBeInTheDocument();
    // $10,000 total - $6,960 asignados = $3,040 por asignar.
    expect(screen.getByText("$3,040.00")).toBeInTheDocument();
  });

  it("registra el pago múltiple con los datos capturados y las facturas seleccionadas", async () => {
    const { container, onRegistrado } = renderForm();
    await elegirAnunciante(container);
    await screen.findByText("A-0001");

    fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "6960" } });
    await screen.findByText("01 · Efectivo");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, {
      target: { value: "01" },
    });
    fireEvent.change(container.querySelectorAll("select.fsel")[1], { target: { value: "cc-1" } });

    const checkboxPendiente = container.querySelectorAll("tbody tr")[0].querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkboxPendiente);

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago múltiple" }));

    await waitFor(() => expect(crearMultipleMock).toHaveBeenCalledTimes(1));
    expect(crearMultipleMock).toHaveBeenCalledWith(
      expect.objectContaining({
        monto_total_pago: "6960",
        forma_pago_clave: "01",
        cuenta_contable_id: "cc-1",
        // ADR-227: "numero_pago" viaja POR RENGLÓN (el calculado de ESA factura), no a
        // nivel del pago múltiple completo.
        pagos: [{ cobranza_id: "cb-1", monto_aplicado: "6960.00", numero_pago: "2" }],
      }),
    );
    expect(crearMultipleMock.mock.calls[0][0]).not.toHaveProperty("numero_pago");
    await waitFor(() => expect(onRegistrado).toHaveBeenCalledTimes(1));
  });

  it("si la suma asignada excede el monto total del pago, no registra y avisa", async () => {
    const { container } = renderForm();
    await elegirAnunciante(container);
    await screen.findByText("A-0001");

    fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "1000" } }); // < 6960
    await screen.findByText("01 · Efectivo");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, {
      target: { value: "01" },
    });
    fireEvent.change(container.querySelectorAll("select.fsel")[1], { target: { value: "cc-1" } });

    const checkboxPendiente = container.querySelectorAll("tbody tr")[0].querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkboxPendiente);

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago múltiple" }));

    expect(await screen.findByText(/no puede exceder el monto total del pago/)).toBeInTheDocument();
    expect(crearMultipleMock).not.toHaveBeenCalled();
  });

  // Petición del usuario: no se permiten pagos de más que sobrepasen lo pendiente de
  // CADA factura (restricción solo de este formulario; el backend no la exige).
  it("si el monto de una factura excede su propio pendiente, no registra y avisa", async () => {
    const { container } = renderForm();
    await elegirAnunciante(container);
    await screen.findByText("A-0001");

    fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "20000" } });
    await screen.findByText("01 · Efectivo");
    fireEvent.change(container.querySelector("select.fsel") as HTMLSelectElement, {
      target: { value: "01" },
    });
    fireEvent.change(container.querySelectorAll("select.fsel")[1], { target: { value: "cc-1" } });

    const checkboxPendiente = container.querySelectorAll("tbody tr")[0].querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkboxPendiente);
    const boton = screen.getByRole("button", { name: "Registrar pago múltiple" });
    expect(boton).toBeEnabled(); // todavía con el pendiente exacto (6960.00).

    // El pendiente real es 6960.00 — se sube el monto aplicado por encima.
    fireEvent.change(screen.getByDisplayValue("6960.00"), { target: { value: "9000" } });

    // Petición del usuario: el botón se deshabilita EN VIVO, sin necesidad de dar clic.
    expect(await screen.findByText(/no puede exceder su pendiente/)).toBeInTheDocument();
    expect(boton).toBeDisabled();
    expect(crearMultipleMock).not.toHaveBeenCalled();

    // Corregir el monto a uno dentro del pendiente lo vuelve a habilitar.
    fireEvent.change(screen.getByDisplayValue("9000"), { target: { value: "5000" } });
    expect(boton).toBeEnabled();
    expect(screen.queryByText(/no puede exceder su pendiente/)).not.toBeInTheDocument();
  });

  // Petición del usuario: cambiar de modo (Anunciante/Agencia) invalida los datos del
  // pago ya capturados, para no arrastrar por error Forma de pago/Monto a otro cliente.
  it("cambiar de modo (Anunciante/Agencia) limpia los campos del pago ya capturados", async () => {
    const { container } = renderForm();
    await elegirAnunciante(container);
    await screen.findByText("A-0001");

    fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "6960" } });
    await screen.findByText("01 · Efectivo");
    const formaPagoSel = container.querySelector("select.fsel") as HTMLSelectElement;
    fireEvent.change(formaPagoSel, { target: { value: "01" } });
    const checkboxPendiente = container.querySelectorAll("tbody tr")[0].querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkboxPendiente);
    expect(formaPagoSel).toHaveValue("01");

    fireEvent.click(screen.getByRole("checkbox", { name: /Pagar Múltiples Facturas de la Agencia/ }));

    expect(screen.getByPlaceholderText("0.00")).toHaveValue("");
    expect(container.querySelector("select.fsel")).toHaveValue("");
    expect(screen.queryByText("A-0001")).not.toBeInTheDocument(); // clienteId también se limpió
  });
});
