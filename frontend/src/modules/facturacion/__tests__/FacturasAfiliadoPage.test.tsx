/** Rediseño del detalle de Facturas de afiliado (F2), a la par del resto de las pantallas
 * de facturación (tarjetas de importes, secciones, "Editar" conectado). "+ Asignar OE"
 * queda solo visual por ahora (el usuario acotó el alcance a diseño + editar) — estas
 * pruebas no lo ejercitan.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FacturasAfiliadoPage } from "../facturaAfiliado/pages/FacturasAfiliadoPage";
import type { FacturaAfiliado, FacturaAfiliadoOrden } from "../types";

const listMock = vi.fn();
const asignacionesMock = vi.fn();
const actualizarMock = vi.fn();
const cambiarEstatusMock = vi.fn();
const autorizarMock = vi.fn();

vi.mock("../api", () => ({
  facturaAfiliadoApi: {
    list: (params: unknown) => listMock(params),
    create: vi.fn(),
    actualizar: (id: string, data: unknown) => actualizarMock(id, data),
    asignaciones: (id: string) => asignacionesMock(id),
    ordenesFacturables: vi.fn().mockResolvedValue([]),
    cambiarEstatus: (...args: unknown[]) => cambiarEstatusMock(...args),
    autorizar: (...args: unknown[]) => autorizarMock(...args),
  },
  facturaClienteApi: {},
  facturaAgenciaApi: {},
  costoApi: {},
  adjuntosFacturacionApi: { subir: vi.fn(), ver: vi.fn() },
  nombreDeAdjuntoFacturacionRef: (ref: string) => ref,
  ordenesPorFacturar: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, size: 1, pages: 1 }),
  anunciantesFacturables: vi.fn().mockResolvedValue([]),
  ordenesFacturables: vi.fn().mockResolvedValue([]),
  cuentasContables: vi.fn().mockResolvedValue([]),
  metodosDePago: vi.fn().mockResolvedValue([]),
  formasDePago: vi.fn().mockResolvedValue([]),
  afiliadosActivos: vi.fn().mockResolvedValue([{ id: "af-1", etiqueta: "Radiorama Jalisco SA de CV" }]),
  agenciasActivas: vi.fn().mockResolvedValue([]),
}));

const base: FacturaAfiliado = {
  factura_afiliado_id: "fa-1",
  afiliado_id: "af-1",
  razon_social_afiliada: "Radiorama Jalisco SA de CV",
  factura_emisora: "EMI-2025-118",
  fecha_factura_afiliado: "2025-04-10",
  monto_factura_afiliado: "334904.00",
  iva_factura_afiliado: "53584.64",
  total_factura_afiliado: "388488.64",
  archivo_nombre: "fact_radiorama_abril.pdf",
  archivo_path: "/recibidas/af/EMI-2025-118.pdf",
  archivo_pdf_path: null,
  archivo_xml_path: null,
  estatus_factura_afiliado: "autorizada",
  created_by: "u-1",
  created_at: "2025-04-10T10:00:00",
  updated_at: null,
};

// Dos asignaciones cuya SUMA (264,384.00) no coincide con ninguna de las dos por
// separado — evita ambigüedad en las pruebas entre la tarjeta "Asignado" (el total) y
// el renglón individual de cada una.
const asignaciones2: FacturaAfiliadoOrden[] = [
  {
    id: "asig-1",
    factura_afiliado_id: "fa-1",
    orden_estacion_id: "9cbc85c3-aaaa-bbbb-cccc-000000000000",
    monto_asignado: "200000.00",
    notas_asignacion: null,
  },
  {
    id: "asig-2",
    factura_afiliado_id: "fa-1",
    orden_estacion_id: "bc89ce9d-aaaa-bbbb-cccc-000000000000",
    monto_asignado: "64384.00",
    notas_asignacion: null,
  },
];

function renderCon(factura: FacturaAfiliado) {
  listMock.mockResolvedValue({ items: [factura], total: 1, page: 1, size: 20, pages: 1 });
  asignacionesMock.mockResolvedValue(asignaciones2);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FacturasAfiliadoPage />
    </QueryClientProvider>,
  );
}

async function abrirDetalle(factura: FacturaAfiliado) {
  const utils = renderCon(factura);
  (await screen.findByText(factura.factura_emisora)).click();
  await screen.findByText("Datos generales");
  // Las asignaciones resuelven en un tick aparte (otra consulta): sin esperar a que
  // termine, "Sin asignar" se calcula sobre un arreglo vacío y puede COINCIDIR por
  // accidente con el subtotal completo, dando falsos "elemento duplicado" en las pruebas.
  await waitFor(() => expect(screen.queryByText("Cargando…")).toBeNull());
  return utils;
}

/** El total de la factura también aparece en la columna "Total" de la tabla (la misma
 *  fila, seleccionada) — se acota al panel de detalle para no ambigüar esas pruebas. */
function panelDeDetalle(): HTMLElement {
  return document.querySelector(".detail-pane") as HTMLElement;
}

describe("FacturasAfiliadoPage — rediseño del detalle", () => {
  beforeEach(() => {
    listMock.mockReset();
    asignacionesMock.mockReset();
    actualizarMock.mockReset();
    cambiarEstatusMock.mockReset();
    autorizarMock.mockReset();
  });

  it("el timeline muestra las 4 fases reales, en orden", async () => {
    const { container } = await abrirDetalle(base);
    // Acotado a `.timeline`: el badge del encabezado también dice "Autorizada".
    const timeline = within(container.querySelector(".timeline") as HTMLElement);
    const pasos = [...container.querySelectorAll(".tl-lbl")].map((el) => el.textContent);
    expect(pasos).toEqual(["Recibida", "En revisión", "Autorizada", "Pagada"]);
    expect(timeline.getByText("Autorizada")).toBeInTheDocument();
  });

  it("en 'autorizada', las 3 primeras fases quedan 'done' y esa es la 'current'", async () => {
    const { container } = await abrirDetalle(base); // base viene con estatus "autorizada"
    const pasos = container.querySelectorAll(".tl-step");
    expect(pasos).toHaveLength(4);
    expect(pasos[0]).toHaveClass("done");
    expect(pasos[1]).toHaveClass("done");
    expect(pasos[2]).toHaveClass("current");
    expect(pasos[3]).not.toHaveClass("done");
    expect(pasos[3]).not.toHaveClass("current");
  });

  it("en 'recibida' (la primera fase), ningún paso previo queda 'done'", async () => {
    const { container } = await abrirDetalle({ ...base, estatus_factura_afiliado: "recibida" });
    const pasos = container.querySelectorAll(".tl-step");
    expect(pasos[0]).toHaveClass("current");
    expect(pasos[0]).not.toHaveClass("done");
    expect(pasos[1]).not.toHaveClass("done");
  });

  it("muestra las tarjetas Subtotal/IVA/Total", async () => {
    await abrirDetalle(base);
    const panel = within(panelDeDetalle());
    expect(panel.getByText("Subtotal")).toBeInTheDocument();
    expect(panel.getByText("$334,904.00")).toBeInTheDocument();
    expect(panel.getByText("$53,584.64")).toBeInTheDocument();
    expect(panel.getByText("$388,488.64")).toBeInTheDocument();
  });

  it("la sección 'Datos generales' muestra razón social, folio y fecha", async () => {
    await abrirDetalle(base);
    expect(screen.getByText("Razón social emisora")).toBeInTheDocument();
    expect(screen.getAllByText("Radiorama Jalisco SA de CV").length).toBeGreaterThan(0);
    expect(screen.getByText("10/04/2025")).toBeInTheDocument();
  });

  it("muestra el archivo adjunto cuando existe", async () => {
    await abrirDetalle(base);
    expect(screen.getByText("fact_radiorama_abril.pdf")).toBeInTheDocument();
  });

  it("la sección 'Asignación a órdenes estación' resume Asignado/Sin asignar", async () => {
    await abrirDetalle(base);
    expect(screen.getByText("Asignación a órdenes estación")).toBeInTheDocument();
    expect(screen.getByText("Asignado")).toBeInTheDocument();
    expect(screen.getByText("$264,384.00")).toBeInTheDocument();
    expect(screen.getByText("Sin asignar")).toBeInTheDocument();
    // 334,904.00 (subtotal) - 264,384.00 asignado = 70,520.00 sin asignar.
    expect(screen.getByText("$70,520.00")).toBeInTheDocument();
  });

  it("fix: una factura autorizada no permite editar (candado del backend)", async () => {
    await abrirDetalle(base);
    expect(screen.getByRole("button", { name: "Editar" })).toBeDisabled();
  });

  it("una factura 'recibida' sí permite editar, y precarga el formulario", async () => {
    await abrirDetalle({ ...base, estatus_factura_afiliado: "recibida" });
    const boton = screen.getByRole("button", { name: "Editar" });
    expect(boton).toBeEnabled();

    fireEvent.click(boton);
    expect(await screen.findByText("Editar factura de afiliado")).toBeInTheDocument();
    expect(screen.getByDisplayValue("EMI-2025-118")).toBeInTheDocument();
    expect(screen.getByDisplayValue("334904.00")).toBeInTheDocument();
    // El afiliado no se puede reasignar al editar.
    expect(screen.getByTitle("El afiliado no se puede cambiar al editar.")).toBeDisabled();
  });

  it("guardar la edición llama a actualizar con el id correcto y sin afiliado_id", async () => {
    actualizarMock.mockResolvedValue({ ...base, estatus_factura_afiliado: "recibida", monto_factura_afiliado: "999.00" });
    await abrirDetalle({ ...base, estatus_factura_afiliado: "recibida" });
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    await screen.findByText("Editar factura de afiliado");

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(actualizarMock).toHaveBeenCalledTimes(1));
    const [id, payload] = actualizarMock.mock.calls[0];
    expect(id).toBe("fa-1");
    expect(payload).not.toHaveProperty("afiliado_id");
    expect(payload.factura_emisora).toBe("EMI-2025-118");

    // Vuelve a la vista de detalle (ya no el formulario).
    expect(await screen.findByText("Datos generales")).toBeInTheDocument();
  });
});
