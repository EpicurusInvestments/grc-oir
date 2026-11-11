/** Pagos recibidos (F3) — orden de columnas y criterio de orden (petición del usuario):
 * por default Fecha (desc) + Referencia (asc); el usuario puede cambiar a Fecha (desc) +
 * Factura (asc) desde un combo en la toolbar.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagosClientePage } from "../pagoCliente/pages/PagosClientePage";
import type { CobranzaFactura, PagoClienteConCobranza } from "../types";

const historialMock = vi.fn();
const noAsignadosMock = vi.fn();
const crearNoAsignadoMutate = vi.fn();
const asignarPagoMutate = vi.fn();
const cobranzasMock = vi.fn();
const anunciantesMock = vi.fn();
const crearMultipleMutate = vi.fn();

vi.mock("../hooks", () => ({
  useHistorialPagosCliente: () => historialMock(),
  useNoAsignados: () => noAsignadosMock(),
  useCrearPagoNoAsignado: () => ({ mutate: crearNoAsignadoMutate, isPending: false, error: null }),
  useAsignarPago: () => ({ mutate: asignarPagoMutate, isPending: false }),
  useCobranzaFacturas: () => ({ list: cobranzasMock() }),
  useAnunciantesInfo: () => anunciantesMock(),
  // ADR-229: `PagoSinAsignarForm` usa estos 3 combos directamente de `../../hooks`.
  useMetodosDePago: () => ({ data: [{ id: "03", etiqueta: "03 · Transferencia" }] }),
  useFormasDePago: () => ({ data: [{ id: "01", etiqueta: "01 · Efectivo" }] }),
  useCuentasContables: () => ({ data: [{ id: "cc-1", etiqueta: "4100-001 · Ingresos" }] }),
  // ADR-230: `PagoMultipleForm` (abierto desde "Repartir con Pago Múltiple") usa estos.
  useAgenciasInfo: () => ({ data: [] }),
  useCrearPagoMultiple: () => ({ mutate: crearMultipleMutate, isPending: false, isError: false }),
}));

const cobranzaBase: CobranzaFactura = {
  cobranza_id: "cb-1",
  factura_id: "f-1",
  anunciante_id: "an-1",
  agencia_id: null,
  metodo_pago_clave: "03",
  dias_credito: 30,
  fecha_estimada_cobro: "2026-04-01",
  fecha_cobro: null,
  estatus_cobro: "cobro_parcial",
  comentarios_cobranza: null,
  created_by: "dev.admin",
  created_at: "2026-03-01",
  updated_at: null,
  importe_cobrado: "1000.00",
  importe_pendiente_cobro: "500.00",
  vencida: false,
  numero_factura: "F-000",
  ultimo_numero_pago: null,
  siguiente_numero_pago: "2",
};

function pago(
  overrides: Partial<PagoClienteConCobranza> & { numero_factura: string },
): PagoClienteConCobranza {
  return {
    pago_cliente_id: overrides.pago_cliente_id ?? overrides.numero_factura,
    cobranza_id: "cb-1",
    fecha_pago_cliente: "2026-03-10",
    monto_aplicado: "1000.00",
    metodo_pago_clave: "03",
    referencia_pago: null,
    archivo_nombre: null,
    archivo_path: null,
    forma_pago_clave: null,
    fecha_deposito: null,
    numero_pago: null,
    cuenta_contable_id: null,
    pago_multiple_id: null,
    pagado_en_sistema_externo: false,
    created_by: "dev.admin",
    created_at: "2026-03-10",
    ...overrides,
    cobranza: { ...cobranzaBase, numero_factura: overrides.numero_factura },
  };
}

// Mismo día (2026-03-10): "REF-A" < "REF-B" pero "F-001" < "F-002" — las dos facturas
// quedan en orden CONTRARIO según el criterio activo, para distinguir ambos modos.
const pagoA = pago({ numero_factura: "F-002", referencia_pago: "REF-A", fecha_pago_cliente: "2026-03-10" });
const pagoB = pago({ numero_factura: "F-001", referencia_pago: "REF-B", fecha_pago_cliente: "2026-03-10" });
const pagoViejo = pago({ numero_factura: "F-999", referencia_pago: "REF-Z", fecha_pago_cliente: "2026-03-05" });

function renderPagina(historial = [pagoA, pagoB, pagoViejo]) {
  historialMock.mockReturnValue({ data: historial, isLoading: false, isError: false });
  noAsignadosMock.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isError: false });
  cobranzasMock.mockReturnValue({
    data: { items: [{ ...cobranzaBase, cobranza_id: "cb-1", estatus_cobro: "cobro_parcial" }] },
  });
  anunciantesMock.mockReturnValue({
    data: [{ anunciante_id: "an-1", nombre_comercial: "Grupo Bimbo" }],
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <PagosClientePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function facturasEnOrden(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("tbody tr td.td-main")).map(
    (td) => td.textContent ?? "",
  );
}

describe("PagosClientePage", () => {
  beforeEach(() => {
    historialMock.mockReset();
    noAsignadosMock.mockReset();
    crearNoAsignadoMutate.mockReset();
    asignarPagoMutate.mockReset();
    cobranzasMock.mockReset();
    anunciantesMock.mockReset();
    crearMultipleMutate.mockReset();
  });

  it("la columna Referencia va justo después de Fecha", () => {
    const { container } = renderPagina();
    const encabezados = Array.from(container.querySelectorAll("thead th")).map((th) => th.textContent);
    expect(encabezados.slice(0, 2)).toEqual(["Fecha", "Referencia"]);
  });

  // Petición del usuario: columna "Número de parcialidad" entre Monto y Método.
  it("la columna 'Número de parcialidad' va entre Monto y Método, con el numero_pago de cada pago", () => {
    const pagoConParcialidad = { ...pagoA, numero_pago: "2 de 3" };
    const { container } = renderPagina([pagoConParcialidad, pagoB, pagoViejo]);

    const encabezados = Array.from(container.querySelectorAll("thead th")).map((th) => th.textContent);
    expect(encabezados).toEqual([
      "Fecha",
      "Referencia",
      "Factura",
      "Monto",
      "Número de parcialidad",
      "Método",
    ]);

    const primeraFila = container.querySelectorAll("tbody tr")[0];
    expect(primeraFila.querySelectorAll("td")[4].textContent).toBe("2 de 3");
  });

  it("por default ordena por Fecha (desc) y luego Referencia (asc)", () => {
    const { container } = renderPagina();
    // Mismo día: REF-A (F-002) antes que REF-B (F-001); F-999 (fecha anterior) al final.
    expect(facturasEnOrden(container)).toEqual(["F-002", "F-001", "F-999"]);
  });

  // Petición del usuario: el buscador de la toolbar debe filtrar por número de pago
  // (parcialidad), referencia y factura — no solo por fecha/monto.
  it("el buscador filtra por número de pago, referencia y factura", () => {
    const pagoConParcialidad = { ...pagoA, numero_pago: "2 de 3" };
    const { container } = renderPagina([pagoConParcialidad, pagoB, pagoViejo]);
    const buscador = screen.getByPlaceholderText(
      "Buscar pago, referencia, factura, fecha o monto…",
    );

    fireEvent.change(buscador, { target: { value: "2 de 3" } });
    expect(facturasEnOrden(container)).toEqual(["F-002"]);

    fireEvent.change(buscador, { target: { value: "REF-B" } });
    expect(facturasEnOrden(container)).toEqual(["F-001"]);

    fireEvent.change(buscador, { target: { value: "F-999" } });
    expect(facturasEnOrden(container)).toEqual(["F-999"]);
  });

  it("cambiar el combo a 'Fecha y Factura' reordena por Factura (asc) dentro del mismo día", () => {
    const { container } = renderPagina();
    fireEvent.change(screen.getByDisplayValue("Ordenar: Fecha y Referencia"), {
      target: { value: "fecha_factura" },
    });
    expect(facturasEnOrden(container)).toEqual(["F-001", "F-002", "F-999"]);
  });

  // ADR-229 (petición del usuario): filtro "Pagos no asignados".
  it("el filtro 'No asignados' muestra solo los pagos sin cobranza, con el badge 'Sin asignar'", () => {
    const pagoSinAsignar = {
      ...pagoA,
      pago_cliente_id: "sa-1",
      cobranza_id: null,
      referencia_pago: null,
    };
    const { container } = renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoSinAsignar], total: 1 },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "No asignados" }));

    expect(screen.getByText("Sin asignar")).toBeInTheDocument();
    expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
  });

  it("'+ Pago sin asignar' abre el formulario y lo registra con crearNoAsignado", () => {
    const { container } = renderPagina();
    fireEvent.click(screen.getByRole("button", { name: "+ Pago sin asignar" }));

    // Scoped a `.form-card`: el toolbar también tiene un `select.fsel` ("Ordenar").
    const selects = container.querySelectorAll(".form-card select.fsel");
    fireEvent.change(screen.getByPlaceholderText("0.00"), { target: { value: "1500" } });
    fireEvent.change(selects[0], { target: { value: "03" } });
    fireEvent.change(screen.getByPlaceholderText("SPEI-XXXXX / CHE-XXXX"), {
      target: { value: "SPEI-999" },
    });
    fireEvent.change(selects[1], { target: { value: "01" } });
    fireEvent.change(selects[2], { target: { value: "cc-1" } });

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago sin asignar" }));

    expect(crearNoAsignadoMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        monto_aplicado: "1500",
        metodo_pago_clave: "03",
        referencia_pago: "SPEI-999",
        forma_pago_clave: "01",
        cuenta_contable_id: "cc-1",
      }),
      expect.anything(),
    );
  });

  // ADR-231 (petición del usuario): el monto a asignar se precarga con el MENOR entre
  // el pendiente de la factura ($500.00, `cobranzaBase`) y lo que queda del huérfano
  // ($1,000.00, `pagoA`) — no debe asignarse de más a la factura por default.
  it("asigna un pago no asignado a la factura elegida, con el monto precargado (tope al pendiente)", async () => {
    const pagoSinAsignar = { ...pagoA, pago_cliente_id: "sa-1", cobranza_id: null };
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoSinAsignar], total: 1 },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "No asignados" }));
    fireEvent.click(screen.getByText("Sin asignar"));

    const buscador = screen.getByPlaceholderText("Buscar factura…") as HTMLInputElement;
    fireEvent.change(buscador, { target: { value: "F-000" } });
    fireEvent.mouseDown(await screen.findByText(/F-000/));

    expect(screen.getByDisplayValue("500.00")).toBeInTheDocument(); // precargado

    fireEvent.click(screen.getByRole("button", { name: "Asignar" }));

    expect(asignarPagoMutate).toHaveBeenCalledWith(
      { pagoId: "sa-1", cobranzaId: "cb-1", montoAplicado: "500.00" },
      expect.anything(),
    );
  });

  it("el usuario puede bajar el monto a asignar para dejar el resto sin asignar", async () => {
    const pagoSinAsignar = { ...pagoA, pago_cliente_id: "sa-1", cobranza_id: null };
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoSinAsignar], total: 1 },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "No asignados" }));
    fireEvent.click(screen.getByText("Sin asignar"));
    const buscador = screen.getByPlaceholderText("Buscar factura…") as HTMLInputElement;
    fireEvent.change(buscador, { target: { value: "F-000" } });
    fireEvent.mouseDown(await screen.findByText(/F-000/));

    fireEvent.change(screen.getByDisplayValue("500.00"), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Asignar" }));

    expect(asignarPagoMutate).toHaveBeenCalledWith(
      { pagoId: "sa-1", cobranzaId: "cb-1", montoAplicado: "200" },
      expect.anything(),
    );
  });

  it("si el monto a asignar excede el pendiente de la factura, avisa y deshabilita el botón", async () => {
    const pagoSinAsignar = { ...pagoA, pago_cliente_id: "sa-1", cobranza_id: null };
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoSinAsignar], total: 1 },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "No asignados" }));
    fireEvent.click(screen.getByText("Sin asignar"));
    const buscador = screen.getByPlaceholderText("Buscar factura…") as HTMLInputElement;
    fireEvent.change(buscador, { target: { value: "F-000" } });
    fireEvent.mouseDown(await screen.findByText(/F-000/));

    fireEvent.change(screen.getByDisplayValue("500.00"), { target: { value: "700" } });

    expect(screen.getByText(/No puede exceder el pendiente de la factura/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Asignar" })).toBeDisabled();
    expect(asignarPagoMutate).not.toHaveBeenCalled();
  });

  // ADR-230 (petición del usuario): "Repartir con Pago Múltiple" precarga los datos
  // del huérfano y bloquea "Monto total del pago" (es dinero ya recibido).
  it("'Repartir con Pago Múltiple' abre el formulario precargado con los datos del huérfano", () => {
    const huerfano = {
      ...pagoA,
      pago_cliente_id: "sa-2",
      cobranza_id: null,
      monto_aplicado: "3000.00",
      forma_pago_clave: "01",
      cuenta_contable_id: "cc-1",
    };
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [huerfano], total: 1 },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "No asignados" }));
    fireEvent.click(screen.getByText("Sin asignar"));
    fireEvent.click(screen.getByRole("button", { name: "Repartir con Pago Múltiple" }));

    expect(screen.getByText(/Repartiendo el pago sin asignar/)).toBeInTheDocument();
    expect(screen.getByText("$3,000.00")).toBeInTheDocument();
    expect(screen.getByDisplayValue("3000.00")).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "← Cancelar" }));
    expect(screen.getByText("Pagos recibidos")).toBeInTheDocument();
  });

  it("al registrar el reparto, manda pago_origen_id con el id del huérfano", async () => {
    const huerfano = {
      ...pagoA,
      pago_cliente_id: "sa-3",
      cobranza_id: null,
      monto_aplicado: "3000.00",
      forma_pago_clave: "01",
      cuenta_contable_id: "cc-1",
    };
    const { container } = renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [huerfano], total: 1 },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "No asignados" }));
    fireEvent.click(screen.getByText("Sin asignar"));
    fireEvent.click(screen.getByRole("button", { name: "Repartir con Pago Múltiple" }));

    const buscador = container.querySelector('input[placeholder="Selecciona…"]') as HTMLInputElement;
    fireEvent.change(buscador, { target: { value: "Bimbo" } });
    fireEvent.mouseDown(await screen.findByText("Grupo Bimbo"));
    await screen.findByText("F-000");

    const checkbox = container.querySelectorAll("tbody tr")[0].querySelector(
      'input[type="checkbox"]',
    ) as HTMLInputElement;
    fireEvent.click(checkbox);

    fireEvent.click(screen.getByRole("button", { name: "Registrar pago múltiple" }));

    expect(crearMultipleMutate).toHaveBeenCalledWith(
      expect.objectContaining({ monto_total_pago: "3000.00", pago_origen_id: "sa-3" }),
      expect.anything(),
    );
  });
});
