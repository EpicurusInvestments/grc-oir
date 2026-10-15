/** Pruebas de la bandeja "Listas para facturar" (F2).
 *
 * Cubre lo que decide la pantalla: que muestra la tarjeta con los datos ya resueltos por
 * el backend, que el estado vacío es el del mockup, y que «Generar factura →» abre el
 * formulario existente con la orden FIJA (sin selector) — que es el punto de la bandeja.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ListasParaFacturarPage } from "../facturaCliente/pages/ListasParaFacturarPage";
import type { OrdenPorFacturar } from "../types";

const porFacturarMock = vi.fn();
const facturaListMock = vi.fn();
const anunciantesMock = vi.fn();
const agenciasMock = vi.fn();

vi.mock("../api", () => ({
  ordenesPorFacturar: (p: unknown) => porFacturarMock(p),
  anunciantesFacturables: (m: unknown) => anunciantesMock(m),
  agenciasFacturables: (m: unknown) => agenciasMock(m),
  facturaClienteApi: {
    list: (p: unknown) => facturaListMock(p),
    create: vi.fn(),
    enviarATimbrado: vi.fn(),
    timbrar: vi.fn(),
    entregar: vi.fn(),
    cancelar: vi.fn(),
    descargarArchivoPlano: vi.fn(),
  },
  ordenesFacturables: vi.fn().mockResolvedValue([]),
  cuentasContables: vi.fn().mockResolvedValue([]),
  metodosDePago: vi.fn().mockResolvedValue([]),
  formasDePago: vi.fn().mockResolvedValue([]),
  afiliadosActivos: vi.fn().mockResolvedValue([]),
  agenciasActivas: vi.fn().mockResolvedValue([]),
  facturaAfiliadoApi: {},
  facturaAgenciaApi: {},
  costoApi: {},
}));

const orden: OrdenPorFacturar = {
  orden_id: "oc-11",
  folio_orden: "OC-2025-0051",
  numero_orden_cliente: "LALA-YOG-11",
  anunciante_id: "an-11",
  anunciante: "OXXO",
  agencia: null,
  vendedor: "Patricia Méndez",
  producto: "Yoghurt Lala Bebible 900ml",
  fecha_inicio_campania: "2025-06-01",
  fecha_fin_campania: "2025-06-30",
  subtotal: "504000.00",
  total: "584640.00",
  empresa_emisora: "OIR Comercial",
  total_spots: 60,
  duracion_spot: "30s",
  facturacion_directa_cliente: true,
  receptor_razon_social: "Cadena Comercial OXXO SA de CV",
  receptor_rfc: "CCO8605231N4",
  receptor_direccion: "CDMX, Insurgentes Sur 800",
  receptor_uso_cfdi_default: null,
};

/** Segunda orden del MISMO anunciante: es lo que hace posible la factura múltiple.
 *  Importe y periodo distintos a propósito, para comprobar que se suma y que el periodo
 *  abarca de la fecha más temprana a la más tardía. */
const segundaOrden: OrdenPorFacturar = {
  ...orden,
  orden_id: "oc-12",
  folio_orden: "OC-2025-0052",
  numero_orden_cliente: "LALA-YOG-12",
  fecha_inicio_campania: "2025-07-01",
  fecha_fin_campania: "2025-07-31",
  subtotal: "300000.00",
  total: "348000.00",
};

/** Orden "vía agencia" (ADR-201): receptor es la agencia, no el anunciante — la que
 *  usan las pruebas del modo "Facturar Múltiples Órdenes por Agencia". */
const ordenAgencia: OrdenPorFacturar = {
  ...orden,
  orden_id: "oc-21",
  folio_orden: "OC-2025-0061",
  numero_orden_cliente: "LALA-YOG-21",
  agencia: "Mindshare México",
  facturacion_directa_cliente: false,
  receptor_razon_social: "Mindshare México SA de CV",
  receptor_rfc: "MMX900101AB1",
  receptor_direccion: "CDMX, Reforma 222",
  receptor_uso_cfdi_default: null,
};

function renderCon(items: OrdenPorFacturar[]) {
  porFacturarMock.mockResolvedValue({
    items,
    total: items.length,
    page: 1,
    size: 20,
    pages: 1,
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ListasParaFacturarPage />
    </QueryClientProvider>,
  );
}

describe("ListasParaFacturarPage", () => {
  beforeEach(() => {
    porFacturarMock.mockReset();
    facturaListMock.mockReset();
    anunciantesMock.mockReset();
    anunciantesMock.mockResolvedValue([]);
    agenciasMock.mockReset();
    agenciasMock.mockResolvedValue([]);
    facturaListMock.mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 0 });
  });

  it("muestra la orden pendiente con los datos ya resueltos por el backend", async () => {
    renderCon([orden]);
    expect(await screen.findByText("OC-2025-0051")).toBeInTheDocument();
    expect(screen.getByText("OXXO")).toBeInTheDocument();
    // Sin agencia se rotula "Trato directo", no un guion suelto.
    expect(screen.getByText(/Trato directo/)).toBeInTheDocument();
    expect(screen.getByText(/\$584,640\.00/)).toBeInTheDocument();
  });

  it("sin pendientes muestra el estado vacío del mockup", async () => {
    renderCon([]);
    expect(
      await screen.findByText(/No hay órdenes pendientes de facturar/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Todas las órdenes cerradas ya tienen factura generada/),
    ).toBeInTheDocument();
  });

  it("«Generar factura →» abre el formulario con la orden FIJA, sin selector", async () => {
    renderCon([orden]);
    (await screen.findByText("Generar factura →")).click();

    await waitFor(() =>
      expect(screen.getByText(/Nueva factura · OC-2025-0051/)).toBeInTheDocument(),
    );
    // El formulario abre con el bloque de datos heredados y SIN selector de orden: la
    // orden ya está decidida por la tarjeta desde la que se entró.
    expect(screen.getByText("Datos heredados de la orden")).toBeInTheDocument();
    expect(screen.getByText("OC-2025-0051")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Busca por folio o número/)).not.toBeInTheDocument();
    // Y la descripción viene pre-cargada, como en la pantalla aprobada.
    expect(screen.getByDisplayValue(/Servicios de transmisión publicitaria/)).toBeInTheDocument();
  });

  it('"Factura relacionada" se filtra por el anunciante de la orden y admite varias (ADR-062)', async () => {
    facturaListMock.mockResolvedValue({
      items: [
        { factura_id: "f-1", numero_factura: "A-1010", estado_facturacion: "timbrada" },
        { factura_id: "f-2", numero_factura: "A-1020", estado_facturacion: "cancelada" },
      ],
      total: 2,
      page: 1,
      size: 100,
      pages: 1,
    });

    renderCon([orden]);
    (await screen.findByText("Generar factura →")).click();
    await waitFor(() =>
      expect(screen.getByText(/Nueva factura · OC-2025-0051/)).toBeInTheDocument(),
    );

    const buscador = await screen.findByPlaceholderText(/Busca por número de factura/);
    fireEvent.focus(buscador);

    // Se pidieron filtradas por el anunciante de la ORDEN (no todas las del sistema).
    await waitFor(() =>
      expect(facturaListMock).toHaveBeenCalledWith({ anunciante_id: "an-11", size: 100 }),
    );

    fireEvent.mouseDown(await screen.findByText("A-1010 · Timbrada"));
    fireEvent.mouseDown(await screen.findByText("A-1020 · Cancelada"));

    // Ambas quedan seleccionadas como chips — incluida la cancelada, que es justo el
    // control que pidió negocio (ver que una factura del cliente se canceló).
    expect(screen.getByText("A-1010 · Timbrada")).toBeInTheDocument();
    expect(screen.getByText("A-1020 · Cancelada")).toBeInTheDocument();
  });

  // ── Facturación múltiple (ADR-064) ──────────────────────────────────────────
  it("el check revela el combo y el botón, y hasta elegir anunciante no lista órdenes", async () => {
    anunciantesMock.mockResolvedValue([
      { anunciante_id: "an-11", anunciante: "OXXO", ordenes: 3 },
    ]);
    renderCon([orden]);
    await screen.findByText("OC-2025-0051");

    fireEvent.click(screen.getByLabelText(/Facturar Múltiples Órdenes por Anunciante/));

    // El botón está desde el principio: valida al hacer clic, no se deshabilita.
    expect(await screen.findByText("Generar Factura Múltiple")).toBeInTheDocument();
    // Sin anunciante elegido, la bandeja invita a elegirlo en vez de mostrar órdenes.
    expect(
      screen.getByText(/Elige un anunciante para ver sus órdenes cerradas/),
    ).toBeInTheDocument();
    expect(screen.queryByText("OC-2025-0051")).not.toBeInTheDocument();
  });

  it("al elegir anunciante pide SOLO sus órdenes y cambia el botón por la casilla", async () => {
    anunciantesMock.mockResolvedValue([
      { anunciante_id: "an-11", anunciante: "OXXO", ordenes: 2 },
    ]);
    renderCon([orden]);
    await screen.findByText("OC-2025-0051");

    fireEvent.click(screen.getByLabelText(/Facturar Múltiples Órdenes por Anunciante/));
    const combo = await screen.findByPlaceholderText("Seleccionar Anunciante");
    fireEvent.focus(combo);
    // `SearchableSelect` elige en mouseDown (antes del blur), no en click.
    fireEvent.mouseDown(await screen.findByText(/OXXO · 2 órdenes/));

    // La consulta se acotó al anunciante elegido.
    await waitFor(() =>
      expect(porFacturarMock).toHaveBeenCalledWith(
        expect.objectContaining({ anunciante_id: "an-11" }),
      ),
    );
    // La tarjeta cambia su acción: ya no se factura de a una.
    expect(await screen.findByLabelText(/Incluir en la factura/)).toBeInTheDocument();
    expect(screen.queryByText("Generar factura →")).not.toBeInTheDocument();
  });

  it("con menos de 2 marcadas el botón explica por qué no procede", async () => {
    anunciantesMock.mockResolvedValue([
      { anunciante_id: "an-11", anunciante: "OXXO", ordenes: 2 },
    ]);
    renderCon([orden]);
    await screen.findByText("OC-2025-0051");
    fireEvent.click(screen.getByLabelText(/Facturar Múltiples Órdenes por Anunciante/));
    const combo = await screen.findByPlaceholderText("Seleccionar Anunciante");
    fireEvent.focus(combo);
    // `SearchableSelect` elige en mouseDown (antes del blur), no en click.
    fireEvent.mouseDown(await screen.findByText(/OXXO · 2 órdenes/));

    fireEvent.click(await screen.findByLabelText(/Incluir en la factura/));
    fireEvent.click(screen.getByText("Generar Factura Múltiple"));

    // Mensaje, no un botón muerto: el usuario sabe qué le falta.
    expect(await screen.findByText(/Selecciona al menos 2 órdenes/)).toBeInTheDocument();
    expect(screen.getByText(/Llevas 1/)).toBeInTheDocument();
    expect(screen.queryByText(/Nueva factura múltiple/)).not.toBeInTheDocument();
  });

  it("con 2 marcadas abre el formulario con las órdenes y el subtotal SUMADO", async () => {
    anunciantesMock.mockResolvedValue([
      { anunciante_id: "an-11", anunciante: "OXXO", ordenes: 2 },
    ]);
    renderCon([orden, segundaOrden]);
    await screen.findByText("OC-2025-0051");
    fireEvent.click(screen.getByLabelText(/Facturar Múltiples Órdenes por Anunciante/));
    const combo = await screen.findByPlaceholderText("Seleccionar Anunciante");
    fireEvent.focus(combo);
    // `SearchableSelect` elige en mouseDown (antes del blur), no en click.
    fireEvent.mouseDown(await screen.findByText(/OXXO · 2 órdenes/));

    const casillas = await screen.findAllByLabelText(/Incluir en la factura/);
    fireEvent.click(casillas[0]);
    fireEvent.click(casillas[1]);
    fireEvent.click(screen.getByText("Generar Factura Múltiple"));

    await waitFor(() =>
      expect(screen.getByText(/Nueva factura múltiple · 2 órdenes/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Datos heredados de 2 órdenes")).toBeInTheDocument();
    // Los folios salen DOS veces a propósito: en el subtítulo de la cabecera y en el
    // bloque de datos heredados. Se afirma el par, no un solo elemento.
    expect(screen.getAllByText("OC-2025-0051, OC-2025-0052")).toHaveLength(2);
    // 504,000 + 300,000: el formulario previsualiza la suma que hará el servicio.
    expect(screen.getByText(/\$804,000\.00/)).toBeInTheDocument();
    // Y el periodo ABARCA de la fecha más temprana a la más tardía de las dos órdenes.
    expect(screen.getByText(/01\/06\/2025 → 31\/07\/2025/)).toBeInTheDocument();
  });

  it("desmarcar el check devuelve la bandeja completa a su modo normal", async () => {
    anunciantesMock.mockResolvedValue([
      { anunciante_id: "an-11", anunciante: "OXXO", ordenes: 2 },
    ]);
    renderCon([orden]);
    await screen.findByText("OC-2025-0051");
    const check = screen.getByLabelText(/Facturar Múltiples Órdenes por Anunciante/);

    fireEvent.click(check);
    expect(await screen.findByText("Generar Factura Múltiple")).toBeInTheDocument();

    fireEvent.click(check);
    expect(await screen.findByText("Generar factura →")).toBeInTheDocument();
    expect(screen.queryByText("Generar Factura Múltiple")).not.toBeInTheDocument();
  });

  // ── Facturación múltiple por Agencia (ADR-201, petición del usuario) ────────────
  it("el check de Agencia revela el combo y el botón, y hasta elegir agencia no lista órdenes", async () => {
    agenciasMock.mockResolvedValue([
      { agencia_id: "ag-11", agencia: "Mindshare México", ordenes: 3 },
    ]);
    renderCon([ordenAgencia]);
    await screen.findByText("OC-2025-0061");

    fireEvent.click(screen.getByLabelText(/Facturar Múltiples Órdenes por Agencia/));

    expect(await screen.findByText("Generar Factura Múltiple")).toBeInTheDocument();
    expect(
      screen.getByText(/Elige una agencia para ver sus órdenes cerradas/),
    ).toBeInTheDocument();
    expect(screen.queryByText("OC-2025-0061")).not.toBeInTheDocument();
  });

  it("al elegir agencia pide SOLO sus órdenes y cambia el botón por la casilla", async () => {
    agenciasMock.mockResolvedValue([
      { agencia_id: "ag-11", agencia: "Mindshare México", ordenes: 2 },
    ]);
    renderCon([ordenAgencia]);
    await screen.findByText("OC-2025-0061");

    fireEvent.click(screen.getByLabelText(/Facturar Múltiples Órdenes por Agencia/));
    const combo = await screen.findByPlaceholderText("Seleccionar Agencia");
    fireEvent.focus(combo);
    fireEvent.mouseDown(await screen.findByText(/Mindshare México · 2 órdenes/));

    await waitFor(() =>
      expect(porFacturarMock).toHaveBeenCalledWith(
        expect.objectContaining({ agencia_id: "ag-11" }),
      ),
    );
    expect(await screen.findByLabelText(/Incluir en la factura/)).toBeInTheDocument();
    expect(screen.queryByText("Generar factura →")).not.toBeInTheDocument();
  });

  it("marcar Agencia apaga el modo Anunciante (y viceversa) — no se pueden combinar", async () => {
    anunciantesMock.mockResolvedValue([
      { anunciante_id: "an-11", anunciante: "OXXO", ordenes: 2 },
    ]);
    agenciasMock.mockResolvedValue([
      { agencia_id: "ag-11", agencia: "Mindshare México", ordenes: 2 },
    ]);
    renderCon([orden]);
    await screen.findByText("OC-2025-0051");

    const checkAnunciante = screen.getByLabelText(/Facturar Múltiples Órdenes por Anunciante/);
    const checkAgencia = screen.getByLabelText(/Facturar Múltiples Órdenes por Agencia/);

    fireEvent.click(checkAnunciante);
    expect(await screen.findByPlaceholderText("Seleccionar Anunciante")).toBeInTheDocument();

    // Marcar Agencia apaga Anunciante: solo un modo activo a la vez.
    fireEvent.click(checkAgencia);
    expect(screen.queryByPlaceholderText("Seleccionar Anunciante")).not.toBeInTheDocument();
    expect(await screen.findByPlaceholderText("Seleccionar Agencia")).toBeInTheDocument();
    expect((checkAnunciante as HTMLInputElement).checked).toBe(false);
    expect((checkAgencia as HTMLInputElement).checked).toBe(true);
  });
});
