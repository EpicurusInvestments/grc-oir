/** Bug reportado por el usuario (con captura): al elegir una "Factura de la
 * emisora"/"Factura de la agencia"/"Factura del vendedor" en el alta de una
 * Requisicion, el monto que se ve en el selector no se pintaba en "Monto de la
 * requisición" — había que teclearlo a mano aunque ya estuviera a la vista. Se
 * agrega el autollenado (siempre editable después: `monto_requisicion` nunca deja
 * de ser un `<input>` normal).
 *
 * Los `<select>` del formulario no tienen `<label>` asociado (mismo criterio que
 * `RegistrarPagoForm.test.tsx`), así que se ubican por posición con
 * `container.querySelectorAll("select.fsel")` en vez de por accesible name.
 *
 * ADR-221b (petición del usuario, "combos largos → buscador"): Afiliado/Agencia/
 * Vendedor dejaron de ser `<select>` nativos — ahora son `SearchableSelect`, un
 * `<input>` de texto cuyas opciones solo existen en el DOM mientras está abierto (y
 * viven en un portal, no dentro del propio campo). `elegirEnBuscable` abre, escribe y
 * confirma por clic — y esa misma espera (`findByText`) ya cubre que el catálogo
 * mockeado haya resuelto, así que no hace falta un `findByText` previo "solo para
 * sincronizar" antes de elegir esa misma opción.
 */

import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RequisicionForm } from "../requisicion/components/RequisicionForm";

vi.mock("../api", () => ({
  afiliadosInfo: vi.fn().mockResolvedValue([
    { afiliado_id: "af-1", nombre_afiliado: "Radio Fórmula MX", razon_social_afiliado: "Radio Fórmula MX SA de CV" },
    // Sin facturas en `facturasAfiliadoPagables` — usado para probar que cambiar de
    // afiliado limpia el monto aunque el nuevo no tenga nada que autollenar.
    { afiliado_id: "af-2", nombre_afiliado: "Afiliado Sin Facturas", razon_social_afiliado: "Afiliado Sin Facturas SA de CV" },
  ]),
  agenciasInfo: vi.fn().mockResolvedValue([
    { agencia_id: "ag-1", nombre_agencia: "Mindshare México", rfc_agencia: "MIN010101AAA", porcentaje_comision_agencia_default: "10.00" },
    { agencia_id: "ag-2", nombre_agencia: "OMD México", rfc_agencia: "OMD010101AAA", porcentaje_comision_agencia_default: "12.00" },
  ]),
  vendedoresInfo: vi.fn().mockResolvedValue([
    { vendedor_id: "vd-1", nombre_vendedor: "Juan Arturo Rodríguez Morales", porcentaje_comision_default: "5.00" },
    { vendedor_id: "vd-2", nombre_vendedor: "María López Castro", porcentaje_comision_default: "8.00" },
  ]),
  facturasAfiliadoPagables: vi.fn().mockResolvedValue([
    { factura_afiliado_id: "fa-1", afiliado_id: "af-1", factura_emisora: "AFI-004", total_factura_afiliado: "290.25" },
  ]),
  facturasAgenciaPagables: vi.fn().mockResolvedValue([
    { factura_agencia_id: "fg-1", agencia_id: "ag-1", orden_id: "oc-1", folio_factura_agencia: "AGE-009", total_factura_agencia: "704.70" },
  ]),
  facturasVendedorPagables: vi.fn().mockResolvedValue([
    { factura_vendedor_id: "fv-1", vendedor_id: "vd-1", orden_id: "oc-1", folio_factura_vendedor: "VND-009", total_factura_vendedor: "4698.00" },
  ]),
  ordenesInfo: vi.fn().mockResolvedValue([{ orden_id: "oc-1", folio_orden: "OC-2026-0041", total: "4698.00" }]),
}));

// Elige una opción ya existente: escribe su texto y confirma con clic.
async function elegirEnBuscable(input: HTMLElement, texto: string) {
  fireEvent.change(input, { target: { value: texto } });
  fireEvent.mouseDown(await screen.findByText(texto));
}

// Solo espera a que el catálogo mockeado haya resuelto (sin elegir nada) — abre el
// buscador, confirma que la opción ya está, y lo cierra sin tocarla.
async function esperarCatalogo(input: HTMLElement, texto: string) {
  fireEvent.focus(input);
  await screen.findByText(texto);
  fireEvent.mouseDown(document.body);
}

function buscador(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input[placeholder="Selecciona…"]') as HTMLInputElement;
}

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RequisicionForm onSubmit={vi.fn()} onCancel={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("RequisicionForm: autollenado del monto al elegir una factura", () => {
  it("pago_afiliado: elegir la factura de la emisora pinta su total en 'Monto de la requisición', y sigue editable", async () => {
    const { container } = renderForm();

    await elegirEnBuscable(buscador(container), "Radio Fórmula MX");
    const [, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFactura, { target: { value: "fa-1" } });

    const monto = screen.getByDisplayValue("290.25") as HTMLInputElement;
    expect(monto).toBeInTheDocument();

    fireEvent.change(monto, { target: { value: "250.00" } });
    expect(monto.value).toBe("250.00");
  });

  it("pago_agencia: elegir la factura de la agencia pinta su total", async () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "pago_agencia" } });

    await elegirEnBuscable(buscador(container), "Mindshare México");
    const [, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFactura, { target: { value: "fg-1" } });

    expect(screen.getByDisplayValue("704.70")).toBeInTheDocument();
  });

  it("comision_vendedor: elegir la factura del vendedor pinta su total", async () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "comision_vendedor" } });

    await elegirEnBuscable(buscador(container), "Juan Arturo Rodríguez Morales");
    const [, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFactura, { target: { value: "fv-1" } });

    expect(screen.getByDisplayValue("4698.00")).toBeInTheDocument();
  });
});

describe("RequisicionForm: bug reportado por el usuario — el monto quedaba con un dato pasado al cambiar de combo", () => {
  it("pago_afiliado: cambiar de afiliado (aunque el nuevo no tenga facturas) limpia el monto ya autollenado", async () => {
    const { container } = renderForm();

    const afiliadoInput = buscador(container);
    await elegirEnBuscable(afiliadoInput, "Radio Fórmula MX");
    const [, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFactura, { target: { value: "fa-1" } });
    expect(screen.getByDisplayValue("290.25")).toBeInTheDocument();

    // "Afiliado Sin Facturas" no tiene nada en `facturasAfiliadoPagables`.
    await elegirEnBuscable(afiliadoInput, "Afiliado Sin Facturas");
    expect(screen.queryByDisplayValue("290.25")).not.toBeInTheDocument();
  });

  it("pago_afiliado: volver la factura a '— Ninguna —' también limpia el monto", async () => {
    const { container } = renderForm();

    await elegirEnBuscable(buscador(container), "Radio Fórmula MX");
    const [, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFactura, { target: { value: "fa-1" } });
    expect(screen.getByDisplayValue("290.25")).toBeInTheDocument();

    fireEvent.change(selectFactura, { target: { value: "" } });
    expect(screen.queryByDisplayValue("290.25")).not.toBeInTheDocument();
  });

  it("comision_vendedor: cambiar de vendedor limpia el monto autollenado por la factura del vendedor anterior", async () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "comision_vendedor" } });

    const vendedorInput = buscador(container);
    await elegirEnBuscable(vendedorInput, "Juan Arturo Rodríguez Morales");
    const [, selectFactura] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFactura, { target: { value: "fv-1" } });
    expect(screen.getByDisplayValue("4698.00")).toBeInTheDocument();

    await elegirEnBuscable(vendedorInput, "María López Castro");
    expect(screen.queryByDisplayValue("4698.00")).not.toBeInTheDocument();
  });
});

describe("RequisicionForm: 'Comisión agencia' se quita del selector (petición del usuario)", () => {
  it("el selector 'Tipo de requisición' ya no ofrece 'Comisión agencia'", () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    const opciones = Array.from(selectTipo.querySelectorAll("option")).map((o) => o.textContent);
    expect(opciones).toEqual(["Pago afiliado", "Pago agencia", "Pagos vendedor"]);
    expect(opciones).not.toContain("Comisión agencia");
  });
});

describe("RequisicionForm: 'Pagos vendedor' (petición del usuario) — mismo patrón que 'Pago agencia'", () => {
  it("ya no muestra 'Orden de cliente' ni '% Comisión'", async () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "comision_vendedor" } });
    await esperarCatalogo(buscador(container), "Juan Arturo Rodríguez Morales");

    expect(screen.queryByText("Orden de cliente")).not.toBeInTheDocument();
    expect(screen.queryByText("% Comisión")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Buscar por folio de orden…")).not.toBeInTheDocument();
  });

  it("'Factura del vendedor' ya no dice '(opcional)' y Guardar exige elegirla", async () => {
    const onSubmit = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <RequisicionForm onSubmit={onSubmit} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "comision_vendedor" } });

    expect(screen.queryByText("Factura del vendedor (opcional)")).not.toBeInTheDocument();
    expect(screen.getByText("Factura del vendedor")).toBeInTheDocument();

    const numero = container.querySelectorAll("input.fi")[0] as HTMLInputElement; // "Número de requisición"
    fireEvent.change(numero, { target: { value: "REQ-TEST" } });

    // Vendedor PRIMERO: elegirlo limpia el monto (fix de un bug anterior), así que debe
    // ir antes de capturar el monto, no después.
    await elegirEnBuscable(buscador(container), "Juan Arturo Rodríguez Morales");

    const monto = container.querySelector('input[inputmode="decimal"]') as HTMLInputElement;
    fireEvent.change(monto, { target: { value: "100.00" } });

    fireEvent.click(screen.getByText("Guardar"));
    expect(screen.getByText("Selecciona el vendedor y la factura del vendedor.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("RequisicionForm: 'Pago afiliado'/'Pago agencia' (petición del usuario) — la factura ya no es opcional", () => {
  it("pago_afiliado: 'Factura de la emisora' ya no dice '(opcional)' y Guardar la exige", async () => {
    const onSubmit = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <RequisicionForm onSubmit={onSubmit} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(screen.queryByText("Factura de la emisora (opcional)")).not.toBeInTheDocument();
    expect(screen.getByText("Factura de la emisora")).toBeInTheDocument();

    await elegirEnBuscable(buscador(container), "Radio Fórmula MX");

    const numero = container.querySelectorAll("input.fi")[0] as HTMLInputElement;
    fireEvent.change(numero, { target: { value: "REQ-TEST" } });
    const monto = container.querySelector('input[inputmode="decimal"]') as HTMLInputElement;
    fireEvent.change(monto, { target: { value: "100.00" } });

    fireEvent.click(screen.getByText("Guardar"));
    expect(screen.getByText("Selecciona el afiliado y la factura de la emisora.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("pago_agencia: 'Factura de la agencia' ya no dice '(opcional)' y Guardar la exige", async () => {
    const onSubmit = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <RequisicionForm onSubmit={onSubmit} onCancel={vi.fn()} />
      </QueryClientProvider>,
    );

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "pago_agencia" } });

    expect(screen.queryByText("Factura de la agencia (opcional)")).not.toBeInTheDocument();
    expect(screen.getByText("Factura de la agencia")).toBeInTheDocument();

    await elegirEnBuscable(buscador(container), "Mindshare México");

    const numero = container.querySelectorAll("input.fi")[0] as HTMLInputElement;
    fireEvent.change(numero, { target: { value: "REQ-TEST" } });
    const monto = container.querySelector('input[inputmode="decimal"]') as HTMLInputElement;
    fireEvent.change(monto, { target: { value: "100.00" } });

    fireEvent.click(screen.getByText("Guardar"));
    expect(screen.getByText("Selecciona la agencia y la factura de la agencia.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("RequisicionForm: bug reportado por el usuario — cambiar de 'Tipo de requisición' no limpiaba los demás campos", () => {
  it("pago_afiliado → pago_agencia: limpia afiliado/factura/monto; el nuevo tipo no hereda nada del anterior", async () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    await elegirEnBuscable(buscador(container), "Radio Fórmula MX");
    const [, selectFacturaAfiliado] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFacturaAfiliado, { target: { value: "fa-1" } });
    expect(screen.getByDisplayValue("290.25")).toBeInTheDocument();

    fireEvent.change(selectTipo, { target: { value: "pago_agencia" } });
    await esperarCatalogo(buscador(container), "Mindshare México");

    // El monto autollenado por la factura de afiliado ya no debe seguir ahí.
    expect(screen.queryByDisplayValue("290.25")).not.toBeInTheDocument();
    // El buscador de Afiliado/su factura ya no están en el DOM (cambió de rama) — si el
    // componente conservara el valor viejo "af-1" en el estado, no se notaría visualmente
    // porque el campo no se renderiza, pero si se vuelve a "pago_afiliado" debe verse limpio.
    fireEvent.change(selectTipo, { target: { value: "pago_afiliado" } });
    const afiliadoInput2 = buscador(container);
    expect(afiliadoInput2.value).toBe("");
  });

  it("comision_vendedor → pago_afiliado: limpia vendedor/factura del vendedor/monto", async () => {
    const { container } = renderForm();

    const [selectTipo] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectTipo, { target: { value: "comision_vendedor" } });

    await elegirEnBuscable(buscador(container), "Juan Arturo Rodríguez Morales");
    const [, selectFacturaVendedor] = container.querySelectorAll("select.fsel");
    fireEvent.change(selectFacturaVendedor, { target: { value: "fv-1" } });
    expect(screen.getByDisplayValue("4698.00")).toBeInTheDocument();

    fireEvent.change(selectTipo, { target: { value: "pago_afiliado" } });

    expect(screen.queryByDisplayValue("4698.00")).not.toBeInTheDocument();
    const monto = container.querySelector('input[inputmode="decimal"]') as HTMLInputElement;
    expect(monto.value).toBe("");
  });
});
