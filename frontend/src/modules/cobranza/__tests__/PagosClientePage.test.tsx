/** Pagos recibidos (F3) — ADR-271 (petición del usuario, "Cancelación de Pago", con
 * desarrolladores consultados): la tabla principal ahora agrupa por pago GLOBAL
 * (columnas Fecha/Referencia/Monto/Factura/Estatus), no por factura aplicada. Cubre el
 * orden por default, el buscador, el combo de orden, el detalle con sus facturas
 * aplicadas + total, el botón "Cancelación de Pago", y que "No asignados"/"Asignar"/
 * "Repartir con Pago Múltiple" (ADR-229/230) siguen funcionando igual.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PagosClientePage } from "../pagoCliente/pages/PagosClientePage";
import type { CobranzaFactura, PagoCliente, PagoGrupo, PagoGrupoDetalle } from "../types";

const gruposMock = vi.fn();
const detalleMock = vi.fn();
const cancelarMutate = vi.fn();
const noAsignadosMock = vi.fn();
const crearNoAsignadoMutate = vi.fn();
const asignarPagoMutate = vi.fn();
const cobranzasMock = vi.fn();
const anunciantesMock = vi.fn();
const crearMultipleMutate = vi.fn();

vi.mock("../hooks", () => ({
  useGruposPagoCliente: () => gruposMock(),
  usePagoGrupoDetalle: (pagoId: string | null) => detalleMock(pagoId),
  useCancelarPago: () => ({ mutate: cancelarMutate, isPending: false }),
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

function grupo(overrides: Partial<PagoGrupo> & { pago_cliente_id: string }): PagoGrupo {
  return {
    pago_multiple_id: null,
    fecha_pago_cliente: "2026-03-10",
    referencia_pago: null,
    monto_pago: "1000.00",
    cantidad_facturas: 1,
    estatus_pago: "pagado",
    ...overrides,
  };
}

function pagoSinAsignar(overrides: Partial<PagoCliente> & { pago_cliente_id: string }): PagoCliente {
  return {
    cobranza_id: null,
    fecha_pago_cliente: "2026-03-10",
    monto_aplicado: "1000.00",
    ajuste: "0.00",
    estatus_pago: "pagado",
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
  };
}

// Mismo día (2026-03-10): "REF-A" < "REF-B" pero cantidad_facturas 2 > 1 — los 2 grupos
// quedan en orden CONTRARIO según el criterio activo, para distinguir ambos modos.
const grupoA = grupo({ pago_cliente_id: "pg-A", referencia_pago: "REF-A", cantidad_facturas: 2 });
const grupoB = grupo({ pago_cliente_id: "pg-B", referencia_pago: "REF-B", cantidad_facturas: 1 });
const grupoViejo = grupo({
  pago_cliente_id: "pg-viejo",
  referencia_pago: "REF-Z",
  fecha_pago_cliente: "2026-03-05",
});

function renderPagina(grupos = [grupoA, grupoB, grupoViejo]) {
  gruposMock.mockReturnValue({ data: grupos, isLoading: false, isError: false });
  detalleMock.mockReturnValue({ data: undefined, isLoading: false, isError: false });
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

function referenciasEnOrden(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("tbody tr td:nth-child(2)")).map(
    (td) => td.textContent ?? "",
  );
}

describe("PagosClientePage", () => {
  beforeEach(() => {
    gruposMock.mockReset();
    detalleMock.mockReset();
    cancelarMutate.mockReset();
    noAsignadosMock.mockReset();
    crearNoAsignadoMutate.mockReset();
    asignarPagoMutate.mockReset();
    cobranzasMock.mockReset();
    anunciantesMock.mockReset();
    crearMultipleMutate.mockReset();
  });

  it("la tabla tiene las columnas Fecha/Referencia/Monto/Factura/Estatus", () => {
    const { container } = renderPagina();
    const encabezados = Array.from(container.querySelectorAll("thead th")).map((th) => th.textContent);
    expect(encabezados).toEqual(["Fecha", "Referencia", "Monto", "Factura", "Estatus"]);
  });

  it("por default ordena por Fecha (desc) y luego Referencia (asc)", () => {
    const { container } = renderPagina();
    // Mismo día: REF-A antes que REF-B; REF-Z (fecha anterior) al final.
    expect(referenciasEnOrden(container)).toEqual(["REF-A", "REF-B", "REF-Z"]);
  });

  it("el buscador filtra por referencia", () => {
    const { container } = renderPagina();
    const buscador = screen.getByPlaceholderText("Buscar pago, referencia, fecha o monto…");

    fireEvent.change(buscador, { target: { value: "REF-B" } });
    expect(referenciasEnOrden(container)).toEqual(["REF-B"]);
  });

  it("cambiar el combo a 'Fecha y Cantidad de facturas' reordena por cantidad (asc) dentro del mismo día", () => {
    const { container } = renderPagina();
    fireEvent.change(screen.getByDisplayValue("Ordenar: Fecha y Referencia"), {
      target: { value: "fecha_cantidad" },
    });
    // REF-B tiene 1 factura, REF-A tiene 2 -> B antes que A.
    expect(referenciasEnOrden(container)).toEqual(["REF-B", "REF-A", "REF-Z"]);
  });

  it("muestra la cantidad de facturas y el estatus de cada pago", () => {
    const { container } = renderPagina([
      grupo({ pago_cliente_id: "pg-1", cantidad_facturas: 3, estatus_pago: "pagado" }),
      grupo({ pago_cliente_id: "pg-2", cantidad_facturas: 1, estatus_pago: "cancelado" }),
    ]);
    const filas = container.querySelectorAll("tbody tr");
    expect(filas[0].textContent).toContain("3 facturas");
    expect(filas[0].textContent).toContain("Pagado");
    expect(filas[1].textContent).toContain("1 factura");
    expect(filas[1].textContent).toContain("Cancelado");
  });

  it("al seleccionar un pago, el detalle muestra sus facturas aplicadas y el total del pago", async () => {
    const detalle: PagoGrupoDetalle = {
      aplicaciones: [
        { pago_cliente_id: "pg-A", cobranza_id: "cb-1", numero_factura: "F-001", numero_pago: "1", monto_aplicado: "600.00" },
        { pago_cliente_id: "pg-A2", cobranza_id: "cb-2", numero_factura: "F-002", numero_pago: "2 de 2", monto_aplicado: "390.00" },
      ],
      total_pago: "998.00", // < suma de aplicaciones: hubo un ajuste, el total NO es la suma mostrada
      estatus_pago: "pagado",
    };
    const { container } = renderPagina();
    detalleMock.mockReturnValue({ data: detalle, isLoading: false, isError: false });

    fireEvent.click(container.querySelectorAll("tbody tr")[0]);

    expect(await screen.findByText("F-001")).toBeInTheDocument();
    expect(screen.getByText("F-002")).toBeInTheDocument();
    expect(screen.getByText("Parcialidad 2 de 2")).toBeInTheDocument();
    expect(screen.getByText("Total del pago")).toBeInTheDocument();
    expect(screen.getByText("$998.00")).toBeInTheDocument();
  });

  // Bug corregido (reportado por el usuario, con captura): la liga "Ver en Cobranza de
  // facturas →" de cada factura aplicada mandaba el `cobranza_id` en el parámetro
  // `factura_id`, que `CobranzaFacturasPage` usa para buscar la cobranza POR número de
  // factura — nunca encontraba nada. Ahora viaja en su propio parámetro `cobranza_id`.
  it("'Ver en Cobranza de facturas' navega con el cobranza_id de esa factura aplicada", async () => {
    function MostrarUbicacion() {
      const location = useLocation();
      return <div data-testid="ubicacion">{location.pathname + location.search}</div>;
    }
    const detalle: PagoGrupoDetalle = {
      aplicaciones: [
        { pago_cliente_id: "pg-A", cobranza_id: "cb-1", numero_factura: "F-001", numero_pago: "1", monto_aplicado: "600.00" },
      ],
      total_pago: "600.00",
      estatus_pago: "pagado",
    };
    gruposMock.mockReturnValue({ data: [grupoA, grupoB, grupoViejo], isLoading: false, isError: false });
    detalleMock.mockReturnValue({ data: detalle, isLoading: false, isError: false });
    noAsignadosMock.mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isError: false });
    cobranzasMock.mockReturnValue({
      data: { items: [{ ...cobranzaBase, cobranza_id: "cb-1", estatus_cobro: "cobro_parcial" }] },
    });
    anunciantesMock.mockReturnValue({ data: [{ anunciante_id: "an-1", nombre_comercial: "Grupo Bimbo" }] });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider client={qc}>
          <PagosClientePage />
          <MostrarUbicacion />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    fireEvent.click(container.querySelectorAll("tbody tr")[0]);

    fireEvent.click(await screen.findByText("Ver en Cobranza de facturas →"));

    expect(screen.getByTestId("ubicacion")).toHaveTextContent("/cobranza?cobranza_id=cb-1");
  });

  // ADR-271 (petición del usuario, "Cancelación de Pago"): el botón nuevo del detalle.
  it("'Cancelación de Pago' pide confirmación y llama a cancelar con el id del pago", async () => {
    detalleMock.mockReturnValue({
      data: { aplicaciones: [], total_pago: "1000.00", estatus_pago: "pagado" },
      isLoading: false,
      isError: false,
    });
    const { container } = renderPagina();

    fireEvent.click(container.querySelectorAll("tbody tr")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelación de Pago" }));

    expect(screen.getByText(/¿Cancelar este pago/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar pago" }));

    expect(cancelarMutate).toHaveBeenCalledWith("pg-A", expect.anything());
  });

  it("'Cancelación de Pago' está deshabilitado si el pago ya está cancelado", async () => {
    const { container } = renderPagina([
      grupo({ pago_cliente_id: "pg-1", estatus_pago: "cancelado" }),
    ]);
    detalleMock.mockReturnValue({
      data: { aplicaciones: [], total_pago: "1000.00", estatus_pago: "cancelado" },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(container.querySelectorAll("tbody tr")[0]);

    expect(await screen.findByRole("button", { name: "Cancelación de Pago" })).toBeDisabled();
  });

  it("si el backend rechaza la cancelación, muestra el mensaje de error", async () => {
    const { container } = renderPagina();
    detalleMock.mockReturnValue({
      data: { aplicaciones: [], total_pago: "1000.00", estatus_pago: "pagado" },
      isLoading: false,
      isError: false,
    });

    fireEvent.click(container.querySelectorAll("tbody tr")[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Cancelación de Pago" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancelar pago" }));

    // `mensajeDeError` solo usa el mensaje real si es un `ApiRequestError` — un error
    // genérico (como el que recibiría aquí cualquier rechazo que no sea de la API) cae
    // al mensaje de respaldo.
    const onError = cancelarMutate.mock.calls[0][1].onError;
    onError(new Error("algo trueno"));

    await waitFor(() =>
      expect(screen.getByText("Ocurrió un error inesperado.")).toBeInTheDocument(),
    );
  });

  // ADR-229 (petición del usuario): filtro "Pagos no asignados" — sin cambios.
  it("el filtro 'No asignados' muestra solo los pagos sin cobranza, con el badge 'Sin asignar'", () => {
    const pagoNA = pagoSinAsignar({ pago_cliente_id: "sa-1", referencia_pago: "REF-A" });
    const { container } = renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoNA], total: 1 },
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
  // ($1,000.00) — no debe asignarse de más a la factura por default.
  it("asigna un pago no asignado a la factura elegida, con el monto precargado (tope al pendiente)", async () => {
    const pagoNA = pagoSinAsignar({ pago_cliente_id: "sa-1", monto_aplicado: "1000.00" });
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoNA], total: 1 },
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
    const pagoNA = pagoSinAsignar({ pago_cliente_id: "sa-1", monto_aplicado: "1000.00" });
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoNA], total: 1 },
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
    const pagoNA = pagoSinAsignar({ pago_cliente_id: "sa-1", monto_aplicado: "1000.00" });
    renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [pagoNA], total: 1 },
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
    const huerfano = pagoSinAsignar({
      pago_cliente_id: "sa-2",
      monto_aplicado: "3000.00",
      forma_pago_clave: "01",
      cuenta_contable_id: "cc-1",
    });
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
    const huerfano = pagoSinAsignar({
      pago_cliente_id: "sa-3",
      monto_aplicado: "3000.00",
      forma_pago_clave: "01",
      cuenta_contable_id: "cc-1",
    });
    const { container } = renderPagina();
    noAsignadosMock.mockReturnValue({
      data: { items: [huerfano], total: 1 },
      isLoading: false,
      isError: false,
    });
    // ADR-273: el reparto ya no puede dejar un sobrante — el pendiente de la factura
    // debe cuadrar EXACTO contra el monto del huérfano (3000.00), si no el botón
    // rechaza el guardado (ver `PagoMultipleForm`).
    cobranzasMock.mockReturnValue({
      data: { items: [{ ...cobranzaBase, cobranza_id: "cb-1", importe_pendiente_cobro: "3000.00" }] },
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
