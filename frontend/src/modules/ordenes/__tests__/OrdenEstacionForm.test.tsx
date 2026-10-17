/** Tanda 3: alta de OrdenEstacion — balance de spots en vivo (incluyendo OI ya existentes de
 * la misma OC) y validaciones "antes de guardar" (1.2, 1.3).
 *
 * El formulario solo LEE `state.ordenesCliente`/`state.ordenesEstacion` (vía `useOrdenes()`);
 * `onGuardar` es un callback que la pantalla real conecta al backend, aquí un `vi.fn()`. Así
 * que cada prueba arma su propia OC (y, si hace falta, sus propias OE previas) como objetos
 * planos y los pasa directo como `initialState` de `OrdenesProvider` — no hace falta pasar por
 * `crearOC`/`crearOE` (que en Tanda 5b llaman al backend real vía HTTP).
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OrdenEstacionForm } from "../ordenEstacion/components/OrdenEstacionForm";
import { OrdenesProvider } from "../state/OrdenesContext";
import { anunciantes, estaciones, tarifas } from "../state/catalogosCache";
import type { OrdenCliente, OrdenEstacion } from "../types";
import { fieldByLabelText } from "./domHelpers";
import { makeOC, makeOE } from "./fixtures";
import { listarAudiosOrdenEstacionApi } from "../adapters/escrituraApi";

// ADR-109: sube el material a S3 en cuanto se elige (antes de guardar la OE) — se mockea
// para no pegarle a la red real desde jsdom; el resto de `escrituraApi` sigue real.
// ADR-210: `listarAudiosOrdenEstacionApi` también se mockea — al CLONAR, el formulario la
// llama para precargar el Material a Transmitir (ver `OrdenEstacionForm.tsx`); por
// default no devuelve nada (la mayoría de las pruebas no clonan material), las que sí lo
// verifican la sobreescriben con `mockResolvedValueOnce`.
vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return {
    ...actual,
    subirMaterialStagingApi: vi
      .fn()
      .mockImplementation((archivo: File) =>
        Promise.resolve({ ref: `orden_estacion/audios/abc_${archivo.name}`, nombre_archivo: archivo.name }),
      ),
    listarAudiosOrdenEstacionApi: vi.fn().mockResolvedValue([]),
  };
});

// ADR-169: "Producto"/"Duración" se llenan desde el catálogo "Producto Duración" — mock
// del catálogo (sin pegarle a la red real desde jsdom), con 2 productos: uno con
// duraciones reales (Spot) y uno cuyo único registro es "sin resultado" (Mención).
vi.mock("@/modules/catalogos/duracionSpot/api", () => ({
  duracionSpotCatalogoApi: {
    list: vi.fn().mockResolvedValue({
      items: [
        { duracion_spot_catalogo_id: "d1", producto: "spot", descripcion_duracion: "30s", activo: true },
        { duracion_spot_catalogo_id: "d2", producto: "spot", descripcion_duracion: "60s", activo: true },
        { duracion_spot_catalogo_id: "d3", producto: "mencion", descripcion_duracion: "sin resultado", activo: true },
        { duracion_spot_catalogo_id: "d4", producto: "Jingle promocional", descripcion_duracion: "15", activo: true },
      ],
      total: 4,
      page: 1,
      size: 100,
      pages: 1,
    }),
  },
}));

// ADR-183: catálogo Constantes del Sistema (grupo MotivoCambio, clave CambioTarifa) para
// el select de "Motivo del cambio de tarifa".
vi.mock("@/modules/catalogos/constantesSistema/api", () => ({
  constanteApi: {
    list: vi.fn().mockResolvedValue({
      items: [
        { constante_sistema_id: "mc1", grupo: "MotivoCambio", clave: "CambioTarifa_1", descripcion: "Por oferta de la emisora", valor: null, activo: true },
        { constante_sistema_id: "mc2", grupo: "MotivoCambio", clave: "CambioTarifa_2", descripcion: "Por incremento de tarifa", valor: null, activo: true },
      ],
      total: 2,
      page: 1,
      size: 100,
      pages: 1,
    }),
  },
}));

// ADR-182: "an1" es el `anunciante_id` default de `makeOC()` (fixtures.ts) — se siembra
// para probar que la tarjeta "Orden de Servicio de origen" muestra su nombre.
anunciantes.push({
  id: "an1",
  agencia_id: null,
  nombre_comercial: "Televisa Publicidad",
  nombre_fiscal: "Televisa Publicidad SA de CV",
  rfc_anunciante: "TPU900101XX1",
  dias_credito_default: 30,
  categoria_id: "",
});

// `es1` (plaza pl2): la estación que usan las pruebas de este archivo — el formulario la
// resuelve contra `state/catalogosCache.ts`, que nace vacío.
// ADR-191: `frecuencia` ya NO lleva el tipo de señal embebido como texto libre (el
// catálogo real lo captura aparte, en `tipo_senal`) — el selector de Orden de
// Transmisión arma "Siglas Frecuencia TIPO Plaza Nombre" concatenando ambos campos por
// separado; con `frecuencia: "900 AM"` (viejo) saldría "900 AM AM" duplicado.
estaciones.push({ id: "es1", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-AM", frecuencia: "900", tipo_senal: "am" });
// `es2`: segunda estación activa — usada por la prueba de ADR-199 (cambiar de estación
// limpia Producto/Duración/Tarifa) para simular un cambio real entre dos emisoras.
estaciones.push({ id: "es2", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XHMT-FM", frecuencia: "90.1", tipo_senal: "fm" });
// Fix: una estación dada de baja no debe aparecer en el select de "Estación".
estaciones.push({ id: "es-inactiva", afiliado_id: "af1", plaza_id: "pl2", nombre_estacion: "XEW-FM (baja)", frecuencia: "88.1", tipo_senal: "fm", activo: false });

function renderForm(
  opts: {
    oc?: Partial<OrdenCliente>;
    oesPrevias?: Partial<OrdenEstacion>[];
    oe?: Partial<OrdenEstacion>;
    clonarDesde?: Partial<OrdenEstacion>;
  } = {},
) {
  const onGuardar = vi.fn();
  const onCancelar = vi.fn();
  const oc = makeOC(opts.oc);
  const oesPrevias = (opts.oesPrevias ?? []).map((oe) => makeOE({ ...oe, orden_id: oc.id }));
  const oe = opts.oe ? makeOE({ ...opts.oe, orden_id: oc.id }) : undefined;
  const clonarDesde = opts.clonarDesde ? makeOE({ ...opts.clonarDesde, orden_id: oc.id }) : undefined;
  const ordenesEstacion = oe ? [...oesPrevias, oe] : oesPrevias;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <OrdenesProvider initialState={{ ordenesCliente: [oc], ordenesEstacion, incidencias: [], historialComisiones: [] }}>
        <OrdenEstacionForm
          ocIdFijo={oc.id}
          oe={oe}
          clonarDesde={clonarDesde}
          onGuardar={onGuardar}
          onCancelar={onCancelar}
        />
      </OrdenesProvider>
    </QueryClientProvider>,
  );
  return { ...utils, onGuardar, onCancelar, oc, oe, clonarDesde };
}

// ADR-110: "Material a Transmitir" es obligatorio para CREAR — antes de poder usar
// "+ Agregar día" hace falta al menos un audio subido (staging). Sube uno de una vez si
// hace falta (no-op si ya hay alguno, p.ej. una prueba que ya lo subió ella misma antes).
// Selector por `accept` (no por posición): el orden de las secciones en el DOM puede
// cambiar (petición del usuario) — ".mp3" en `accept` solo lo trae este input.
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

describe("ADR-182: la tarjeta 'Orden de Servicio de origen' muestra el Anunciante heredado", () => {
  it("muestra el nombre comercial del anunciante de la OC junto al folio", () => {
    renderForm({ oc: { anunciante_id: "an1" } });
    expect(screen.getByText("Televisa Publicidad")).toBeInTheDocument();
  });

  it("si el anunciante no está en el catálogo cargado, muestra un guion en vez de romperse", () => {
    renderForm({ oc: { anunciante_id: "an-no-existe" } });
    const card = screen.getByText("Orden de Servicio de origen").closest(".form-card") as HTMLElement;
    expect(within(card).getByText("—")).toBeInTheDocument();
  });

  it("fix: en el alta SUELTA (sin ocIdFijo), al elegir una OC del selector también aparece el Anunciante", () => {
    const oc = makeOC({ anunciante_id: "an1" });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { container } = render(
      <QueryClientProvider client={qc}>
        <OrdenesProvider
          initialState={{ ordenesCliente: [oc], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}
        >
          <OrdenEstacionForm onGuardar={vi.fn()} onCancelar={vi.fn()} />
        </OrdenesProvider>
      </QueryClientProvider>,
    );

    // Antes de elegir una OC, sin Anunciante que mostrar.
    expect(screen.queryByText("Televisa Publicidad")).toBeNull();

    const combo = fieldByLabelText<HTMLInputElement>(container, "Orden de Servicio de origen");
    fireEvent.focus(combo);
    fireEvent.mouseDown(screen.getByText(`${oc.folio_orden} — ${oc.numero_orden_cliente}`));

    expect(screen.getByText("Televisa Publicidad")).toBeInTheDocument();
  });
});

describe("ADR-210: 'Clonar' precarga una OE nueva con los datos de otra, sin activar edición", () => {
  it("precarga Estación, Producto, Duración, Tarifa, Spots bonificables y Observaciones", () => {
    const { container } = renderForm({
      clonarDesde: {
        folio_orden_interna: "OE-2025-0009A",
        estacion_id: "es1",
        producto_tarifa: "spot",
        duracion_spot: "30s",
        precio_spot: 950,
        cantidad_spots_bonificables: 3,
        observaciones_estacion: "Observación de la OE original",
      },
    });

    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación").value).toBe("es1");
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("950.00");
    expect(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables del afiliado").value).toBe("3");
    expect(fieldByLabelText<HTMLTextAreaElement>(container, "Observaciones de la estación").value).toBe(
      "Observación de la OE original",
    );
    expect(screen.getByText("Nueva Orden de Transmisión (clonada de OE-2025-0009A)")).toBeInTheDocument();
  });

  it("no activa modo edición: sigue pidiendo Material a Transmitir y guarda con la OC como alta nueva (no PATCH)", async () => {
    const { container, onGuardar, oc } = renderForm({
      clonarDesde: { estacion_id: "es1", producto_tarifa: "spot", duracion_spot: "30s", precio_spot: 950 },
    });

    // ADR-210: se clona el material (vía `listarAudiosOrdenEstacionApi`, mockeada arriba
    // con `[]` por default) — la OE de origen de este caso no tenía ninguno, así que
    // sigue pidiéndolo (ADR-110), pero solo DESPUÉS de resolver esa consulta.
    await screen.findByText("Sin audios elegidos todavía.");
    await asegurarMaterial(container);

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    // `onGuardar(ocId, input)` — firma de ALTA, nunca la de edición (que no recibe ocId).
    expect(onGuardar).toHaveBeenCalledWith(oc.id, expect.anything());
  });

  it("fix (petición del usuario): clona el Material a Transmitir vía `ref` de S3, sin descargar/re-subir el archivo", async () => {
    vi.mocked(listarAudiosOrdenEstacionApi).mockResolvedValueOnce([
      {
        orden_estacion_audio_id: "au-1",
        orden_estacion_id: "oe-vieja",
        nombre_archivo: "uno.mp3",
        orden: 1,
        created_at: "2025-06-01",
        ref: "orden_estacion/audios/uno.mp3",
      },
      {
        orden_estacion_audio_id: "au-0",
        orden_estacion_id: "oe-vieja",
        nombre_archivo: "cero.mp3",
        orden: 0,
        created_at: "2025-06-01",
        ref: "orden_estacion/audios/cero.mp3",
      },
    ]);
    const { onGuardar } = renderForm({
      clonarDesde: { estacion_id: "es1", producto_tarifa: "spot", duracion_spot: "30s", precio_spot: 950 },
    });

    // Se ven de inmediato, YA EN ORDEN (`orden`, no el orden en que llegó la respuesta) —
    // sin pasar por "Sin audios elegidos todavía." ni por el input de archivo. "cero.mp3"
    // aparece 2 veces: en la lista de material subido Y en la columna "Material a
    // Transmitir" del único día (sin asignación propia, le toca por posición — ADR-107).
    await waitFor(() => expect(screen.getAllByText("cero.mp3").length).toBeGreaterThan(0));
    expect(screen.getByText("uno.mp3")).toBeInTheDocument();
    expect(screen.queryByText("Sin audios elegidos todavía.")).toBeNull();
    expect(screen.queryByText("Cargando material de la Orden de Transmisión clonada…")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    const [, input] = onGuardar.mock.calls[0];
    // Exactamente los `ref` que ya traía la OE de origen — ninguna subida nueva.
    expect(input.audios_staging).toEqual([
      { ref: "orden_estacion/audios/cero.mp3", nombre_archivo: "cero.mp3" },
      { ref: "orden_estacion/audios/uno.mp3", nombre_archivo: "uno.mp3" },
    ]);
  });

  it("fix (reportado por el usuario): el material clonado también queda YA ELEGIDO en la columna 'Material a Transmitir' de cada día, no solo en la lista de arriba", async () => {
    vi.mocked(listarAudiosOrdenEstacionApi).mockResolvedValueOnce([
      {
        orden_estacion_audio_id: "au-0",
        orden_estacion_id: "oe-vieja",
        nombre_archivo: "cero.mp3",
        orden: 0,
        created_at: "2025-06-01",
        ref: "orden_estacion/audios/cero.mp3",
      },
      {
        orden_estacion_audio_id: "au-1",
        orden_estacion_id: "oe-vieja",
        nombre_archivo: "uno.mp3",
        orden: 1,
        created_at: "2025-06-01",
        ref: "orden_estacion/audios/uno.mp3",
      },
    ]);
    const { onGuardar } = renderForm({
      clonarDesde: {
        estacion_id: "es1",
        producto_tarifa: "spot",
        duracion_spot: "30s",
        precio_spot: 950,
        periodo_transmision: [
          // Este día, en la OE original, ya tenía "uno.mp3" elegido a mano (no el
          // default por posición) — el clon debe respetar ESA elección puntual, no
          // simplemente repartir por posición desde cero.
          {
            fecha: "2025-06-10",
            hora_inicio: "09:00",
            hora_termino: "10:00",
            spots_diarios: 1,
            orden_estacion_dia_id: "dia-vieja-1",
            orden_estacion_audio_id: "au-1",
          },
        ],
      },
    });

    // Antes del fix, la columna de la tabla se quedaba en "Elige material…" aunque la
    // lista de arriba (Material a Transmitir) ya mostrara "uno.mp3"/"cero.mp3" clonados.
    await waitFor(() =>
      expect(screen.queryByText("Cargando material de la Orden de Transmisión clonada…")).toBeNull(),
    );
    expect(screen.queryByText("Elige material…")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    const [, input] = onGuardar.mock.calls[0];
    // El día clonado manda el `ref` (id de staging) del audio que correspondía al id
    // REAL ("au-1") que tenía en la OE anterior — no el default por posición ("au-0").
    expect(input.periodo_transmision[0].orden_estacion_audio_id).toBe("orden_estacion/audios/uno.mp3");
  });

  it("fix (reportado por el usuario, caso real): un día SIN `orden_estacion_audio_id` propio (usaba el default por posición, ADR-107) también queda elegido al clonar", async () => {
    vi.mocked(listarAudiosOrdenEstacionApi).mockResolvedValueOnce([
      {
        orden_estacion_audio_id: "au-0",
        orden_estacion_id: "oe-vieja",
        nombre_archivo: "Audio_2_30-Second-Timer-Bomb-MISSION-IMPOSSIBLE.mp3",
        orden: 0,
        created_at: "2025-06-01",
        ref: "orden_estacion/audios/Audio_2_30-Second-Timer-Bomb-MISSION-IMPOSSIBLE.mp3",
      },
    ]);
    renderForm({
      clonarDesde: {
        estacion_id: "es1",
        producto_tarifa: "spot",
        duracion_spot: "30s",
        precio_spot: 950,
        periodo_transmision: [
          // Como la OE real reportada por el usuario: un solo día, sin
          // `orden_estacion_audio_id` propio — en la vista de solo lectura "usaba" el
          // único audio disponible por el default de posición (ADR-107), no una
          // elección explícita.
          { fecha: "2026-10-11", hora_inicio: "07:00", hora_termino: "07:00", spots_diarios: 1 },
        ],
      },
    });

    await waitFor(() =>
      expect(screen.queryByText("Cargando material de la Orden de Transmisión clonada…")).toBeNull(),
    );
    // Antes de este fix, un día sin asignación EXPLÍCITA se clonaba igual de vacío —
    // aunque hubiera un solo material disponible (el caso más común de todos).
    expect(screen.queryByText("Elige material…")).toBeNull();
  });

  it("copia el período (fecha/hora/spots) pero SIN ids ni historial de la OE anterior", async () => {
    const { container, onGuardar } = renderForm({
      clonarDesde: {
        estacion_id: "es1",
        producto_tarifa: "spot",
        duracion_spot: "30s",
        precio_spot: 950,
        periodo_transmision: [
          {
            fecha: "2025-06-15",
            hora_inicio: "09:00",
            hora_termino: "10:00",
            spots_diarios: 15,
            orden_estacion_dia_id: "dia-vieja-1",
            orden_estacion_audio_id: "audio-viejo-1",
            cancelada: true,
            hora_real: "09:05",
          },
        ],
      },
    });

    // La fila se ve de inmediato (no hace falta volver a capturarla).
    expect(screen.getByDisplayValue("2025-06-15")).toBeInTheDocument();

    // ADR-210: espera a que se resuelva la consulta de material clonado (vacía en este
    // caso, mock por default) antes de subir uno a mano.
    await screen.findByText("Sin audios elegidos todavía.");
    await asegurarMaterial(container);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());

    const input = onGuardar.mock.calls[0][1];
    expect(input.periodo_transmision).toEqual([
      { fecha: "2025-06-15", hora_inicio: "09:00", hora_termino: "10:00", spots_diarios: 15 },
    ]);
  });

  it("si además viene `oe` (edición), `oe` manda y `clonarDesde` se ignora", () => {
    const { container } = renderForm({
      oe: { folio_orden_interna: "OE-2025-EDITANDO", estacion_id: "es2", precio_spot: 500 },
      clonarDesde: { folio_orden_interna: "OE-2025-CLONADA", estacion_id: "es1", precio_spot: 950 },
    });

    expect(screen.getByText("Editar: OE-2025-EDITANDO")).toBeInTheDocument();
    expect(fieldByLabelText<HTMLSelectElement>(container, "Estación").value).toBe("es2");
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("500.00");
  });
});

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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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

// es1 = XEW-AM. ta-am-60-spot: la ÚNICA tarifa vigente para es1/60s/spot — 60s a
// propósito (NO 30s, que ya usan otras pruebas de este archivo sin esperar ninguna
// tarifa sembrada) para no interferir con ellas.
tarifas.push({
  id: "ta-am-60-spot",
  anunciante_id: "an1",
  estacion_id: "es1",
  duracion_spot: "60s",
  producto: "spot",
  tarifa_bruta: 1000,
  descuento_pct: 0,
  tarifa_neta: 1000,
});
// ADR-169: tarifa con producto/duración TEXTO LIBRE (más allá del enum anterior) — para
// confirmar que la sugerencia de tarifa del catálogo sigue funcionando igual.
tarifas.push({
  id: "ta-am-15-jingle",
  anunciante_id: "an1",
  estacion_id: "es1",
  duracion_spot: "15",
  producto: "Jingle promocional",
  tarifa_bruta: 450,
  descuento_pct: 0,
  tarifa_neta: 450,
});

describe("Tarifa sugerida del catálogo y motivo de cambio — 1.3 (ADR-102/ADR-106)", () => {
  it("precio_spot coincide con la tarifa sugerida: no pide motivo y no bloquea Guardar por eso", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });

    // La tarifa se autocarga a 1000 (coincide con `ta-am-30-spot`) — no hay divergencia,
    // así que el campo "Motivo" ni siquiera se muestra (ADR-183b).
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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });
    // Se aparta de la tarifa sugerida (1000) a propósito.
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "1500" } });
    await agregarDia(container, 10);

    expect(
      screen.getByText(/El precio no coincide con la tarifa sugerida del catálogo: captura el motivo del cambio\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeDisabled();

    // ADR-183/183b: "Motivo del cambio de tarifa" es un select con las Descripciones
    // del catálogo MotivoCambio/CambioTarifa — se espera a que cargue (mock); se MUESTRA
    // (siempre habilitado) porque lo último que se tocó fue la tarifa misma.
    await screen.findByText("Por oferta de la emisora");
    const motivoSelect = fieldByLabelText<HTMLSelectElement>(container, "Motivo del cambio de tarifa");
    expect(motivoSelect).toBeEnabled();
    fireEvent.change(motivoSelect, { target: { value: "Por incremento de tarifa" } });
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.motivo_cambio_tarifa).toBe("Por incremento de tarifa");
  });

  it("fix (reportado por el usuario): al CLONAR con una tarifa que ya diverge del catálogo, el selector de motivo aparece de inmediato (sin tocar nada) y exige elegirlo", async () => {
    const { container, onGuardar } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000 },
      // La OE original ya traía la tarifa ajustada a mano (1500 vs. los 1000 de
      // `ta-am-60-spot`) — nada se "toca" al clonar, así que antes del fix
      // `requiereMotivoTarifa` se quedaba en `false` y el selector ni se mostraba,
      // aunque el backend igual exige el motivo en todo alta con tarifa divergente.
      clonarDesde: { estacion_id: "es1", producto_tarifa: "spot", duracion_spot: "60s", precio_spot: 1500 },
    });

    await screen.findByText("Por oferta de la emisora");
    expect(
      screen.getByText(/El precio no coincide con la tarifa sugerida del catálogo: captura el motivo del cambio\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeDisabled();

    const motivoSelect = fieldByLabelText<HTMLSelectElement>(container, "Motivo del cambio de tarifa");
    expect(motivoSelect).toBeEnabled();
    fireEvent.change(motivoSelect, { target: { value: "Por incremento de tarifa" } });
    // El período clonado (1 día, dentro de la campaña de la OC) ya alcanza para guardar
    // — solo falta el material (mock por default sin ninguno clonado, ADR-210).
    await screen.findByText("Sin audios elegidos todavía.");
    await asegurarMaterial(container);
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    await waitFor(() => expect(onGuardar).toHaveBeenCalled());
    const [, input] = onGuardar.mock.calls[0];
    expect(input.motivo_cambio_tarifa).toBe("Por incremento de tarifa");
  });

  it("ADR-183b (petición del usuario): tocar Spots bonificables DESPUÉS de divergir la tarifa oculta el motivo y ya no lo exige", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "1500" } });
    await screen.findByText("Motivo del cambio de tarifa");

    // Toca "Spots bonificables del afiliado" después de divergir — el precio SIGUE
    // siendo 1500 (sigue divergiendo numéricamente), pero el motivo ya no es lo último
    // que se tocó: el campo debe ocultarse y dejar de bloquear Guardar.
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Spots bonificables del afiliado"), {
      target: { value: "5" },
    });
    expect(screen.queryByText("Motivo del cambio de tarifa")).toBeNull();

    await agregarDia(container, 10);
    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    const [, input] = onGuardar.mock.calls[0];
    expect(input.precio_spot).toBe(1500);
    expect(input.motivo_cambio_tarifa).toBeUndefined();
  });

  it("ADR-115 (fix): al cambiar a una duración SIN tarifa en el catálogo, el campo se limpia para capturarla a mano", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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

  it("ADR-170 (petición del usuario, reemplaza ADR-115): cambiar de Duración SIEMPRE limpia un precio tecleado a mano", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });

    const tarifaInput = fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot");
    fireEvent.change(tarifaInput, { target: { value: "1234" } });

    // "30s" no tiene tarifa sembrada para es1/spot — antes (ADR-115) se preservaba el
    // valor tecleado a mano; ahora (ADR-170) se limpia siempre al cambiar de Duración.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    expect(tarifaInput.value).toBe("");

    // Volver a "60s" (que SÍ tiene tarifa) recarga su tarifa del catálogo, no el valor
    // editado a mano que ya se perdió al cambiar de Duración.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });
    expect(tarifaInput.value).toBe("1,000.00");
  });

  it("ADR-170 (petición del usuario): cambiar de Producto SIEMPRE limpia un precio tecleado a mano", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "60s" } });

    const tarifaInput = fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot");
    fireEvent.change(tarifaInput, { target: { value: "9999" } });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "mencion" } });
    expect(tarifaInput.value).toBe("");
  });

  it("ADR-162 (fix): al editar una OE cuyo precio ya diverge del catálogo, SIN cambiarlo, no vuelve a pedir motivo", async () => {
    const { onGuardar } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000 },
      oe: { estacion_id: "es1", producto_tarifa: "spot", duracion_spot: "60s", precio_spot: 1500 },
    });

    // El precio (1500) ya diverge de la tarifa del catálogo (1000), pero no se tocó en
    // esta edición — no debe aparecer el campo de motivo (ADR-183b) ni bloquear Guardar.
    expect(screen.getByText(/Tarifa del catálogo: \$1,000\.00/)).toBeInTheDocument();
    expect(screen.queryByText("Motivo del cambio de tarifa")).toBeNull();
    expect(screen.getByRole("button", { name: "Guardar cambios" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.precio_spot).toBe(1500);
    expect(input.motivo_cambio_tarifa).toBeUndefined();
  });

  it("ADR-162 (fix): al editar y cambiar el precio a otro valor que también diverge, vuelve a pedir motivo", async () => {
    const { container, onGuardar } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000 },
      oe: { estacion_id: "es1", producto_tarifa: "spot", duracion_spot: "60s", precio_spot: 1500 },
    });

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "1600" } });

    expect(screen.getByRole("button", { name: "Guardar cambios" })).toBeDisabled();

    await screen.findByText("Por oferta de la emisora");
    const motivoSelect = fieldByLabelText<HTMLSelectElement>(container, "Motivo del cambio de tarifa");
    expect(motivoSelect).toBeEnabled();
    fireEvent.change(motivoSelect, { target: { value: "Por oferta de la emisora" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar cambios" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.precio_spot).toBe(1600);
    expect(input.motivo_cambio_tarifa).toBe("Por oferta de la emisora");
  });

  it("ADR-169: producto con solo 'sin resultado' en el catálogo deja Duración deshabilitada, pero SÍ permite capturar tarifa y guardar", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("mencion")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "mencion" } });

    const selectDuracion = fieldByLabelText<HTMLSelectElement>(container, "Duración");
    expect(selectDuracion).toBeDisabled();
    expect(within(selectDuracion).queryByText("sin resultado")).toBeNull();

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "300" } });
    await agregarDia(container, 10);

    expect(screen.getByRole("button", { name: "Guardar Orden de Transmisión" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));

    const [, input] = onGuardar.mock.calls[0];
    expect(input.producto_tarifa).toBe("mencion");
    expect(input.duracion_spot).toBeUndefined();
    expect(input.precio_spot).toBe(300);
  });

  it("ADR-169 (petición del usuario): producto/duración texto libre coinciden con una tarifa ya sembrada y la autocargan igual que antes", async () => {
    const { container } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(
        within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("Jingle promocional"),
      ).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), {
      target: { value: "Jingle promocional" },
    });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "15" } });

    expect(screen.getByText(/Tarifa del catálogo: \$450\.00/)).toBeInTheDocument();
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("450.00");
    expect(screen.queryByText("Motivo del cambio de tarifa")).toBeNull();
  });
});

describe("ADR-173 (petición del usuario): Producto/Duración se precargan desde la OC de origen al CREAR", () => {
  it("al elegir la estación, Producto y Duración ya vienen seleccionados con los de la OC y autocargan su tarifa", async () => {
    const { container, onGuardar } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000, producto_tarifa: "spot", duracion_spot: "60s" },
    });

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });

    // Sin tocar los selects de Producto/Duración, ya vienen con el valor de la OC...
    expect(fieldByLabelText<HTMLSelectElement>(container, "Producto").value).toBe("spot");
    expect(fieldByLabelText<HTMLSelectElement>(container, "Duración").value).toBe("60s");
    // ...y la tarifa sembrada para es1/60s/spot (1000) se autocarga sola, igual que si el
    // usuario los hubiera elegido a mano.
    await waitFor(() =>
      expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("1,000.00"),
    );
    expect(screen.getByText(/Tarifa del catálogo: \$1,000\.00/)).toBeInTheDocument();

    await agregarDia(container, 10);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.producto_tarifa).toBe("spot");
    expect(input.duracion_spot).toBe("60s");
  });

  it("el usuario sigue pudiendo cambiar el Producto/Duración precargados", async () => {
    const { container, onGuardar } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000, producto_tarifa: "spot", duracion_spot: "60s" },
    });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Duración")).getByText("30s")).toBeInTheDocument(),
    );

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("");

    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "900" } });
    await agregarDia(container, 10);
    fireEvent.click(screen.getByRole("button", { name: "Guardar Orden de Transmisión" }));
    const [, input] = onGuardar.mock.calls[0];
    expect(input.duracion_spot).toBe("30s");
    expect(input.precio_spot).toBe(900);
  });

  it("si la OC no capturó Duración, el select de Duración arranca vacío (deshabilitado si el producto no tiene duraciones reales, igual que siempre)", async () => {
    const { container } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000, producto_tarifa: "mencion", duracion_spot: null },
    });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });

    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("mencion")).toBeInTheDocument(),
    );
    expect(fieldByLabelText<HTMLSelectElement>(container, "Producto").value).toBe("mencion");
    const selectDuracion = fieldByLabelText<HTMLSelectElement>(container, "Duración");
    expect(selectDuracion.value).toBe("");
    expect(selectDuracion).toBeDisabled();
  });

  it("si la OC capturó 'sin resultado' como duración, el select de Duración arranca vacío (no lo muestra como opción)", async () => {
    const { container } = renderForm({
      oc: { total_spots: 120, precio_unitario: 1000, producto_tarifa: "mencion", duracion_spot: "sin resultado" },
    });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });

    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("mencion")).toBeInTheDocument(),
    );
    expect(fieldByLabelText<HTMLSelectElement>(container, "Duración").value).toBe("");
  });
});

describe("ADR-199 (petición del usuario): cambiar de Estación en el alta limpia Producto/Duración/Tarifa", () => {
  it("elegir OTRA estación después de ya tener una vacía Producto, Duración y Tarifa", async () => {
    const { container } = renderForm({ oc: { total_spots: 120 } });

    // Precarga de ADR-173 (producto_tarifa/duracion_spot de la OC, default "spot"/"30s"
    // en `makeOC`) al elegir la PRIMERA estación — no debe limpiarse.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() => expect(fieldByLabelText<HTMLSelectElement>(container, "Producto").value).toBe("spot"));
    expect(fieldByLabelText<HTMLSelectElement>(container, "Duración").value).toBe("30s");

    // El usuario captura una tarifa a mano (es1/spot/30s no tiene tarifa sembrada en el
    // catálogo de este archivo).
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "500" } });
    expect(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot").value).toBe("500.00");

    // Cambia a OTRA estación ya elegida antes (es1 -> es2): Producto/Duración/Tarifa se
    // deben limpiar — no tiene sentido arrastrar una tarifa/producto de la emisora
    // anterior a la nueva.
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es2" } });

    expect(fieldByLabelText<HTMLSelectElement>(container, "Producto").value).toBe("");
    const selectDuracion = fieldByLabelText<HTMLSelectElement>(container, "Duración");
    expect(selectDuracion.value).toBe("");
    expect(selectDuracion).toBeDisabled();
    // Sin Producto elegido, la tarjeta de "Tarifa por spot" ni siquiera se muestra
    // (ADR-169: requiere Producto elegido o estar editando).
    expect(screen.queryByText("Tarifa por spot (MXN)")).toBeNull();
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
    expect(screen.getByText("#1")).toBeInTheDocument();

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
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
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

  it("ADR-111/ADR-187: con 2+ audios subidos, un día de 1 solo renglón (sin rango) asigna por posición y permite reasignar a otro material", async () => {
    const { container, onGuardar } = renderForm({ oc: { total_spots: 120, precio_unitario: 1000 } });

    elegirArchivo(container, "uno.mp3");
    await waitFor(() => expect(screen.getByText("uno.mp3")).toBeInTheDocument());
    elegirArchivo(container, "dos.wav");
    await waitFor(() => expect(screen.getByText("dos.wav")).toBeInTheDocument());

    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Estación"), { target: { value: "es1" } });
    await waitFor(() =>
      expect(within(fieldByLabelText<HTMLSelectElement>(container, "Producto")).getByText("spot")).toBeInTheDocument(),
    );
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Producto"), { target: { value: "spot" } });
    fireEvent.change(fieldByLabelText<HTMLSelectElement>(container, "Duración"), { target: { value: "30s" } });
    fireEvent.change(fieldByLabelText<HTMLInputElement>(container, "Tarifa por spot"), { target: { value: "800" } });
    await agregarDia(container, 50);

    // "+ Agregar día" genera UN solo renglón (sin rango, `hora_inicio === hora_termino`)
    // con `spots_diarios = 50` — por dentro sigue siendo 1 sola fila real, así que solo
    // puede llevar 1 material (el tope del multi-select es `grupo.filas.length`, no los
    // spots): le toca el primero por posición (ADR-187).
    expect(screen.getAllByText("uno.mp3").length).toBeGreaterThanOrEqual(2);

    // Para reasignar: abrir el panel, desmarcar "uno.mp3" (ya está al tope de 1) y
    // marcar "dos.wav".
    const tabla = container.querySelector("table.cat-table") as HTMLElement;
    fireEvent.click(within(tabla).getByRole("button", { name: "uno.mp3" }));
    fireEvent.click(within(tabla).getByLabelText("uno.mp3"));
    fireEvent.click(within(tabla).getByLabelText("dos.wav"));

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
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const utils = render(
      <QueryClientProvider client={qc}>
        <OrdenesProvider initialState={{ ordenesCliente: [oc1, oc2], ordenesEstacion: [], incidencias: [], historialComisiones: [] }}>
          <OrdenEstacionForm onGuardar={onGuardar} onCancelar={onCancelar} />
        </OrdenesProvider>
      </QueryClientProvider>,
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
    // ADR-191: el combo muestra "Siglas Frecuencia TIPO Plaza Nombre" — sin siglas
    // capturadas ni plaza registrada en este fixture (`findPlaza("pl2")` no existe en
    // esta suite), ambas partes se OMITEN (no un "—" ni un espacio de más).
    expect(within(select).getByText("900 AM XEW-AM")).toBeInTheDocument();
    expect(within(select).queryByText(/XEW-FM \(baja\)/)).toBeNull();
  });
});

describe("ADR-191 (petición del usuario): el combo de Estación muestra 'Siglas Frecuencia TIPO Nombre' (sin Plaza)", () => {
  it("con todos los datos capturados (siglas), arma las 4 partes en ese orden, separadas por un solo espacio", async () => {
    estaciones.push({
      id: "es-completa",
      afiliado_id: "af1",
      plaza_id: "pl2",
      nombre_estacion: "Multimedios Estrellas de Oro",
      siglas: "XHMT",
      frecuencia: "90.1",
      tipo_senal: "fm",
    });

    const { container } = renderForm({ oc: { total_spots: 120 } });
    const select = fieldByLabelText<HTMLSelectElement>(container, "Estación");
    expect(within(select).getByText("XHMT 90.1 FM Multimedios Estrellas de Oro")).toBeInTheDocument();
  });
});
