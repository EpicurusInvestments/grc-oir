/** Tanda 3: alta de OrdenEstacion — balance de spots en vivo (incluyendo OI ya existentes de
 * la misma OC) y validaciones "antes de guardar" (1.2, 1.3).
 *
 * El formulario solo LEE `state.ordenesCliente`/`state.ordenesEstacion` (vía `useOrdenes()`);
 * `onGuardar` es un callback que la pantalla real conecta al backend, aquí un `vi.fn()`. Así
 * que cada prueba arma su propia OC (y, si hace falta, sus propias OE previas) como objetos
 * planos y los pasa directo como `initialState` de `OrdenesProvider` — no hace falta pasar por
 * `crearOC`/`crearOE` (que en Tanda 5b llaman al backend real vía HTTP).
 */

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionForm } from "../ordenEstacion/components/OrdenEstacionForm";
import { OrdenesProvider } from "../state/OrdenesContext";
import { estaciones, tarifas } from "../state/catalogosCache";
import type { OrdenCliente, OrdenEstacion } from "../types";
import { fieldByLabelText } from "./domHelpers";
import { makeOC, makeOE } from "./fixtures";

// ADR-109: sube el material a S3 en cuanto se elige (antes de guardar la OE) — se mockea
// para no pegarle a la red real desde jsdom; el resto de `escrituraApi` sigue real.
vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return {
    ...actual,
    subirMaterialStagingApi: vi
      .fn()
      .mockImplementation((archivo: File) =>
        Promise.resolve({ ref: `orden_estacion/audios/abc_${archivo.name}`, nombre_archivo: archivo.name }),
      ),
  };
});

// `es1` (plaza pl2): la estación que usan las pruebas de este archivo — el formulario la
// resuelve contra `state/catalogosCache.ts`, que nace vacío.
estaciones.push({ id: "es1", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-AM", frecuencia: "900 AM", tipo_senal: "am" });
// Fix: una estación dada de baja no debe aparecer en el select de "Estación".
estaciones.push({ id: "es-inactiva", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-FM (baja)", frecuencia: "88.1 FM", tipo_senal: "fm", activo: false });

function renderForm(
  opts: { oc?: Partial<OrdenCliente>; oesPrevias?: Partial<OrdenEstacion>[]; oe?: Partial<OrdenEstacion> } = {},
) {
  const onGuardar = vi.fn();
  const onCancelar = vi.fn();
  const oc = makeOC(opts.oc);
  const oesPrevias = (opts.oesPrevias ?? []).map((oe) => makeOE({ ...oe, orden_id: oc.id }));
  const oe = opts.oe ? makeOE({ ...opts.oe, orden_id: oc.id }) : undefined;
  const ordenesEstacion = oe ? [...oesPrevias, oe] : oesPrevias;
  const utils = render(
    <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion, incidencias: [], historialComisiones: [] }}>
      <OrdenEstacionForm ocIdFijo={oc.id} oe={oe} onGuardar={onGuardar} onCancelar={onCancelar} />
    </OrdenesProvider>,
  );
  return { ...utils, onGuardar, onCancelar, oc, oe };
}

// ADR-110: "Material a Transmitir" es obligatorio para CREAR — antes de poder usar
// "+ Agregar día" hace falta al menos un audio subido (staging). Sube uno de una vez si
// hace falta (no-op si ya hay alguno, p.ej. una prueba que ya lo subió ella misma antes).
// Selector por `accept` (no por posición): "Reporte del afiliado" también es un
// input[type="file"] en el mismo formulario, y el orden de las secciones en el DOM
// puede cambiar (petición del usuario) — ".mp3" en `accept` solo lo trae este input.
function inputDeMaterial(container: HTMLElement): HTMLInputElement {
  return container.querySelector('input[type="file"][accept*=".mp3"]') as HTMLInputElement;
}

async function asegurarMaterial(container: HTMLElement) {
  if (!screen.queryByText("Sin audios elegidos todavía.")) return;
  const input = inputDeMaterial(container);
  const archivo = new File(["contenido"], "uno.mp3", { type: "audio/mpeg" });
  fireEvent.change(input, { target: { files: [archivo] } });
  await waitFor(() => expect(screen.queryByText("Sin audios elegidos todavía.")).toBeNull());
}

async function agregarDia(container: HTMLElement, spots: number) {
  await asegurarMaterial(container);
  fireEvent.click(screen.getByRole("button", { name: "+ Agregar día" }));
  const spotsInputs = container.querySelectorAll('input[type="number"]');
  const ultimo = spotsInputs[spotsInputs.length - 1] as HTMLInputElement;
  fireEvent.change(ultimo, { target: { value: String(spots) } });
}

describe("Balance de spots en vivo — 1.2", () => {
  it("agregar días refleja 'faltan N por asignar', luego 100%, luego sobre-asignación", async () => {
    const { container } = renderForm({ oc: { total_spots: 120 } });

    await agregarDia(container, 50);
    expect(screen.getByText("faltan 70 spots por asignar")).toBeInTheDocument();

    await agregarDia(container, 70);
    expect(screen.getByText("✓ 100% asignado")).toBeInTheDocument();

    await agregarDia(container, 1);
    expect(screen.getByText("⚠ excedente de 1 spots")).toBeInTheDocument();
  });

  it("las OE ya existentes de la misma OC cuentan como 'ya asignados' desde que se abre el formulario", async () => {
    const { container } = renderForm({
      oc: { total_spots: 120 },
      oesPrevias: [{ periodo_transmision: [{ fecha: "2025-06-01", hora_inicio: "07:00", hora_termino: "08:00", spots_diarios: 50 }] }],
    });

    // Sin agregar nada en ESTA OI todavía, ya refleja los 50 de la OE previa.
    expect(screen.getByText("faltan 70 spots por asignar")).toBeInTheDocument();

    await agregarDia(container, 70);
    expect(screen.getByText("✓ 100% asignado")).toBeInTheDocument();
  });
});

describe("Validaciones 'antes de guardar' — 1.3", () => {
  it("acumula errores (sin periodo, sin tarifa) y deshabilita 'Guardar'", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });

    // "Captura al menos un día..." aparece dos veces (el estado vacío del propio grid, sin
    // viñeta, y el panel "Antes de guardar", con viñeta "• "): se matchea el del grid con
    // texto exacto. El de la tarifa solo vive en el panel con viñeta, así que se matchea
    // con regex (coincidencia parcial) en vez de texto exacto.
    expect(screen.getByText("Captura al menos un día de transmisión.")).toBeInTheDocument();
    expect(screen.getByText(/Captura una tarifa por spot mayor a 0\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeDisabled();

    const tarifaInput = fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot");
    fireEvent.change(tarifaInput, { target: { value: "800" } });
    await agregarDia(container, 50);

    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();
  });

  it("ADR-101: la tarifa de la estación puede superar la del cliente — el % OIR se vuelve negativo, sin bloquear Guardar", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "1500" } }); // > tarifa cliente (1000)
    await agregarDia(container, 50);

    expect(screen.getByText("-50%")).toBeInTheDocument(); // (1000-1500)/1000*100
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    expect(onGuardar).toHaveBeenCalledTimes(1);
  });

  it("una fecha fuera del rango de la campaña se reporta como error por día", async () => {
    const { container } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000, fecha_inicio_campania: "2025-06-01", fecha_fin_campania: "2025-06-30" },
    });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);

    const fechaInput = container.querySelector('input[type="date"]') as HTMLInputElement;
    fireEvent.change(fechaInput, { target: { value: "2025-07-15" } }); // fuera del rango

    expect(screen.getByText(/Día 1: La fecha cae fuera del rango de la campaña\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeDisabled();
  });

  it("al resolver todos los errores, 'Guardar' llama a onGuardar con el input correcto", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    expect(onGuardar).toHaveBeenCalledTimes(1);
    const [ocIdArg, input] = onGuardar.mock.calls[0];
    expect(typeof ocIdArg).toBe("string");
    expect(input.estacion_id).toBe("es1");
    expect(input.plaza_id).toBe("pl2"); // heredada de la estación es1
    expect(input.precio_spot).toBe(800);
    expect(input.periodo_transmision).toHaveLength(1);
    expect(input.periodo_transmision[0].spots_diarios).toBe(50);
  });
});

describe("Spots bonificables de la OI (ADR-068)", () => {
  it("el Importe se calcula sobre spots facturables (asignados − bonificables), no sobre el total asignado", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables"), { target: { value: "20" } });

    expect(screen.getAllByText("30").length).toBeGreaterThan(0); // Spots facturables = 50-20
    expect(screen.getByText("$24,000.00")).toBeInTheDocument(); // Importe = 30*800
  });

  it("spots bonificables mayores a los asignados de esta OI muestran error y bloquean Guardar", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables"), { target: { value: "51" } });

    expect(screen.getByText(/Los spots bonificables \(51\) no pueden exceder los spots asignados de esta OI \(50\)\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeDisabled();
  });

  it("'Guardar' llama a onGuardar con cantidad_spots_bonificables capturado", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables"), { target: { value: "10" } });

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    const [, input] = onGuardar.mock.calls[0];
    expect(input.cantidad_spots_bonificables).toBe(10);
  });

  it("al editar una OE, precarga los spots bonificables ya guardados", async () => {
    const { container } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000 },
      oe: { estacion_id: "es1", precio_spot: 700, cantidad_spots_bonificables: 15 },
    });
    expect(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables").value).toBe("15");
  });
});

// es1 = XEW-AM (tipo_senal "am"). ta-am-60-spot: la ÚNICA tarifa vigente para
// es1/am/60s/spot — 60s a propósito (NO 30s, que ya usan otras pruebas de este archivo
// sin esperar ninguna tarifa sembrada) para no interferir con ellas.
tarifas.push({
  id: "ta-am-60-spot",
  estacion_id: "es1",
  tipo_senal: "am",
  duracion_spot: "60s",
  producto: "spot",
  tarifa_bruta: 1000,
  descuento_pct: 0,
  tarifa_neta: 1000,
});

describe("Tarifa sugerida del catálogo y motivo de cambio — 1.3 (ADR-102/ADR-106)", () => {
  it("precio_spot coincide con la tarifa sugerida: no pide motivo y no bloquea Guardar por eso", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });

    // La tarifa se autocarga a 1000 (coincide con `ta-am-30-spot`) — no aparece "Motivo".
    expect(screen.getByText(/Tarifa del catálogo: \$1,000\.00/)).toBeInTheDocument();
    expect(screen.queryByText("Motivo del cambio de tarifa")).toBeNull();

    await agregarDia(container, 10);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    const [, input] = onGuardar.mock.calls[0];
    expect(input.motivo_cambio_tarifa).toBeUndefined();
  });

  it("precio_spot diverge de la tarifa sugerida: exige motivo, bloquea Guardar sin él, y lo manda al backend con él", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });
    // Se aparta de la tarifa sugerida (1000) a propósito.
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "1500" } });
    await agregarDia(container, 10);

    expect(screen.getByText("Motivo del cambio de tarifa")).toBeInTheDocument();
    expect(
      screen.getByText(/El precio no coincide con la tarifa sugerida del catálogo: captura el motivo del cambio\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeDisabled();

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Motivo del cambio de tarifa"), {
      target: { value: "Negociación especial con el afiliado" },
    });
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.motivo_cambio_tarifa).toBe("Negociación especial con el afiliado");
  });

  it("ADR-115 (fix): al cambiar a una duración SIN tarifa en el catálogo, el campo se limpia para capturarla a mano", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });

    const tarifaInput = fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot");
    expect(tarifaInput.value).toBe("1,000.00");

    // "30s" no tiene tarifa sembrada para es1/am/spot — antes del fix se quedaba
    // arrastrando el "1,000.00" de la duración anterior en vez de vaciarse.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    expect(tarifaInput.value).toBe("");

    // Volver a "60s" (que sí tiene tarifa) la vuelve a autocargar normalmente.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });
    expect(tarifaInput.value).toBe("1,000.00");
  });

  it("ADR-115 (fix): un precio tecleado a mano NO se borra al cambiar a una duración sin tarifa", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });

    const tarifaInput = fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot");
    fireEvent.change(tarifaInput, { target: { value: "1234" } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    expect(tarifaInput.value).toBe("1,234.00");
  });
});

describe("Material a Transmitir — subida durante la captura (ADR-109)", () => {
  function elegirArchivo(container: HTMLElement, nombre = "uno.mp3") {
    const input = inputDeMaterial(container);
    const archivo = new File(["contenido"], nombre, { type: "audio/mpeg" });
    fireEvent.change(input, { target: { files: [archivo] } });
    return input;
  }

  it("al elegir un audio (CREAR, antes de guardar) se sube de inmediato y se ve en la lista y en la tabla", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    expect(screen.getByText("Sin audios elegidos todavía.")).toBeInTheDocument();
    elegirArchivo(container);

    await waitFor(() => expect(screen.getByText("uno.mp3")).toBeInTheDocument());
    expect(screen.getByText("Default")).toBeInTheDocument();

    // También aparece como material por default en la tabla de días (aunque el día
    // todavía no tenga `orden_estacion_dia_id` real).
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await agregarDia(container, 5);
    expect(screen.getAllByText("uno.mp3").length).toBeGreaterThanOrEqual(2);
  });

  it("'Guardar' manda los audios ya subidos (staging) en el input, en el mismo orden", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    elegirArchivo(container, "uno.mp3");
    await waitFor(() => expect(screen.getByText("uno.mp3")).toBeInTheDocument());

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    const [, input] = onGuardar.mock.calls[0];
    expect(input.audios_staging).toEqual([{ ref: "orden_estacion/audios/abc_uno.mp3", nombre_archivo: "uno.mp3" }]);
  });

  it("'Quitar' descarta un audio ya subido antes de guardar", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    elegirArchivo(container);
    await waitFor(() => expect(screen.getByText("uno.mp3")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Quitar" }));
    expect(screen.queryByText("uno.mp3")).toBeNull();
    expect(screen.getByText("Sin audios elegidos todavía.")).toBeInTheDocument();
  });

  it("ADR-111: con 2+ audios subidos, 'Sustitución de Material' permite elegir otro para un día ya generado", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    elegirArchivo(container, "uno.mp3");
    await waitFor(() => expect(screen.getByText("uno.mp3")).toBeInTheDocument());
    elegirArchivo(container, "dos.wav");
    await waitFor(() => expect(screen.getByText("dos.wav")).toBeInTheDocument());

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);

    // Por default se pinta el primero subido (aparece tanto en la lista de audios como
    // en la tabla de días).
    expect(screen.getAllByText("uno.mp3").length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByRole("button", { name: "Sustitución de Material" }));
    const selectSustitucion = container.querySelector("table.cat-table select") as HTMLSelectElement;
    fireEvent.change(selectSustitucion, { target: { value: "orden_estacion/audios/abc_dos.wav" } });

    await waitFor(() => expect(screen.queryByText("Sin audios elegidos todavía.")).toBeNull());
    expect(screen.getAllByText("dos.wav").length).toBeGreaterThanOrEqual(2);

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.periodo_transmision[0].orden_estacion_audio_id).toBe("orden_estacion/audios/abc_dos.wav");
  });
});

describe("Selector de OC de origen con filtro de búsqueda — abierta suelta (sin ocIdFijo)", () => {
  function renderSuelto() {
    const oc1 = makeOC({ folio_orden: "OC-2026-0041", numero_orden_cliente: "PO-cliente-001", estatus_orden: "orden_interna" });
    const oc2 = makeOC({ folio_orden: "OC-2026-0043", numero_orden_cliente: "PO-CLIENTE-V02", estatus_orden: "orden_interna" });
    const onGuardar = vi.fn();
    const onCancelar = vi.fn();
    const utils = render(
      <OrdenesProvider initialState={{ ordenesCliente: [oc1, oc2], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionForm onGuardar={onGuardar} onCancelar={onCancelar} />
      </OrdenesProvider>,
    );
    return { ...utils, oc1, oc2 };
  }

  it("escribir en el buscador filtra la lista por folio o número de orden", async () => {
    const { container, oc1, oc2 } = renderSuelto();
    const buscador = fieldByLabelText<HTMLInputElement>(container, "Orden de Servicio de origen");
    fireEvent.change(buscador, { target: { value: "0043" } });

    expect(screen.getByText(`${oc2.folio_orden} — ${oc2.numero_orden_cliente}`)).toBeInTheDocument();
    expect(screen.queryByText(`${oc1.folio_orden} — ${oc1.numero_orden_cliente}`)).toBeNull();
  });

  it("elegir una opción de la lista selecciona esa OC (aparece la sección 'Estación')", async () => {
    const { container, oc2 } = renderSuelto();
    const buscador = fieldByLabelText<HTMLInputElement>(container, "Orden de Servicio de origen");
    fireEvent.change(buscador, { target: { value: "V02" } });
    fireEvent.mouseDown(screen.getByText(`${oc2.folio_orden} — ${oc2.numero_orden_cliente}`));

    expect(screen.getByText("Estación")).toBeInTheDocument();
    expect((fieldByLabelText<HTMLInputElement>(container, "Orden de Servicio de origen")).value).toBe(
      `${oc2.folio_orden} — ${oc2.numero_orden_cliente}`,
    );
  });
});

describe("Edición de OE existente (corrección de errores de captura, antes de transmitir)", () => {
  it("precarga tarifa/observaciones/periodo, y título/botón cambian a modo edición", async () => {
    const { container, oe } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000 },
      oe: { estacion_id: "es1", precio_spot: 700, observaciones_estacion: "Nota original" },
    });

    expect(screen.getByText(`Editar: ${oe!.folio_orden_interna}`)).toBeInTheDocument();
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("700.00");
    expect(screen.getByDisplayValue("Nota original")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar cambios" })).toBeInTheDocument();
  });

  it("bloquea el selector de Estación: el backend no permite reasignarla al editar", async () => {
    const { container } = renderForm({ oc: { total_spots: 120 }, oe: { estacion_id: "es1" } });
    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación").disabled).toBe(true);
  });

  it("el balance en vivo no cuenta dos veces la propia OE que se está editando", async () => {
    // makeOE() por defecto trae un solo día con 10 spots — son "la propia OE", no "otra".
    renderForm({ oc: { total_spots: 120 }, oe: { estacion_id: "es1" } });
    expect(screen.getByText("faltan 110 spots por asignar")).toBeInTheDocument();
  });

  it("'Guardar cambios' llama a onGuardar con los valores editados", async () => {
    const { container, onGuardar } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000 },
      oe: { estacion_id: "es1", precio_spot: 700 },
    });

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "750" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(onGuardar).toHaveBeenCalledTimes(1);
    const [, input] = onGuardar.mock.calls[0];
    expect(input.precio_spot).toBe(750);
    expect(input.periodo_transmision).toHaveLength(1);
  });
});

describe("Fix: estaciones inactivas no aparecen en el select", () => {
  it("la estación activa aparece en el select, la dada de baja no", async () => {
    const { container } = renderForm({ oc: { total_spots: 120 } });
    const select = fieldByLabelText<HTMLSelectElement>(container, "Estación");
    expect(within(select).getByText("XEW-AM (900 AM)")).toBeInTheDocument();
    expect(within(select).queryByText(/XEW-FM \(baja\)/)).toBeNull();
  });
});
