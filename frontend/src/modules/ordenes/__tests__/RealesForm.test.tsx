/** ADR-119: "Capturar Reales" ya no captura `testigos_url`/`testigos_ubicacion_alterna`
 * — se reemplazan por "Evidencias de lo Transmitido" (mismo patrón de audios que
 * "Material a Transmitir", ver `EvidenciasTransmitido.tsx`).
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  eliminarLayoutRealOrdenEstacionApi,
  listarLayoutRealesOrdenEstacionApi,
  subirLayoutRealOrdenEstacionApi,
} from "../adapters/escrituraApi";
import { RealesForm } from "../ordenEstacion/components/RealesForm";
import { makeOC, makeOE, makeRow } from "./fixtures";

vi.mock("../adapters/escrituraApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../adapters/escrituraApi")>();
  return {
    ...actual,
    listarEvidenciasOrdenEstacionApi: vi.fn().mockResolvedValue([]),
    subirEvidenciaOrdenEstacionApi: vi
      .fn()
      .mockImplementation((_oeId: string, archivo: File) =>
        Promise.resolve({
          orden_estacion_evidencia_id: "ev-1",
          orden_estacion_id: _oeId,
          nombre_archivo: archivo.name,
          created_at: "2026-09-24T00:00:00",
        }),
      ),
    listarFormatosRealesOrdenEstacionApi: vi.fn().mockResolvedValue([]),
    subirFormatoRealOrdenEstacionApi: vi
      .fn()
      .mockImplementation((_oeId: string, archivo: File) =>
        Promise.resolve({
          orden_estacion_formato_real_id: "fr-1",
          orden_estacion_id: _oeId,
          nombre_archivo: archivo.name,
          created_at: "2026-09-25T00:00:00",
        }),
      ),
    listarLayoutRealesOrdenEstacionApi: vi.fn().mockResolvedValue([]),
    eliminarLayoutRealOrdenEstacionApi: vi.fn().mockResolvedValue(undefined),
    subirLayoutRealOrdenEstacionApi: vi
      .fn()
      .mockImplementation((_oeId: string, archivo: File) =>
        Promise.resolve({
          archivo: {
            orden_estacion_layout_real_id: "lr-1",
            orden_estacion_id: _oeId,
            nombre_archivo: archivo.name,
            created_at: "2026-09-30T00:00:00",
          },
          aplicados: [],
          nuevos: [],
          errores: [],
        }),
      ),
    listarFormatosRealesClienteOrdenEstacionApi: vi.fn().mockResolvedValue([]),
    subirFormatoRealClienteOrdenEstacionApi: vi
      .fn()
      .mockImplementation((_oeId: string, archivo: File) =>
        Promise.resolve({
          orden_estacion_formato_real_cliente_id: "frc-1",
          orden_estacion_id: _oeId,
          nombre_archivo: archivo.name,
          created_at: "2026-09-30T00:00:00",
        }),
      ),
  };
});

describe("ADR-119: RealesForm ya no tiene testigos, sí Evidencias de lo Transmitido", () => {
  it("no muestra los campos de testigos que se quitaron", async () => {
    const oe = makeOE();
    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Evidencias de lo Transmitido")).toBeInTheDocument());
    expect(screen.queryByText("URL de testigos")).toBeNull();
    expect(screen.queryByText("Ubicación alterna")).toBeNull();
  });

  it("subir una evidencia la refleja en la lista, y 'Avanzar' ya no manda campos de testigos", async () => {
    const oe = makeOE();
    const onAvanzar = vi.fn();
    const { container } = render(<RealesForm oe={oe} onAvanzar={onAvanzar} onCancelar={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Sin evidencias subidas todavía.")).toBeInTheDocument());

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const archivo = new File(["contenido"], "real.mp3", { type: "audio/mpeg" });
    fireEvent.change(input, { target: { files: [archivo] } });
    await waitFor(() => expect(screen.getByText("real.mp3")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Avanzar a 2.3 →" }));

    expect(onAvanzar).toHaveBeenCalledTimes(1);
    const [, extra] = onAvanzar.mock.calls[0];
    expect(extra).not.toHaveProperty("testigosUrl");
    expect(extra).not.toHaveProperty("testigosUbicacionAlterna");
  });
});

describe("ADR-123: RealesForm también ofrece Formato de Horarios Reales, junto a Evidencias", () => {
  it("acepta cualquier formato (p.ej. un PDF) y lo refleja en su propia lista", async () => {
    const oe = makeOE();
    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Horarios Reales Recibidos de la Estación")).toBeInTheDocument(),
    );
    // ADR-146: ahora hay 3 tarjetas de "cualquier formato"/"lista blanca" propias, cada
    // una con el mismo texto vacío — ya no es único en la pantalla.
    expect(screen.getAllByText("Sin archivos subidos todavía.").length).toBeGreaterThan(0);

    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputFormato = inputs.filter((el) => el.type === "file")[1];
    const archivo = new File(["contenido"], "horarios.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    fireEvent.change(inputFormato, { target: { files: [archivo] } });

    await waitFor(() => expect(screen.getByText("horarios.xlsx")).toBeInTheDocument());
  });
});

describe("ADR-146: Carga de Órdenes Reales Desde Layout y Formato Enviado al Cliente", () => {
  it("muestra ambos componentes nuevos y ya no muestra 'Reporte del afiliado'", async () => {
    const oe = makeOE();
    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    expect(screen.getByText("Cargar Formato de Horarios Reales Enviado al Cliente")).toBeInTheDocument();
    expect(screen.queryByText("Reporte del afiliado")).toBeNull();
  });

  it("'Carga de Órdenes Reales Desde Layout' acepta un csv y lo refleja en su lista", async () => {
    const oe = makeOE();
    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );

    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputLayout = inputs.filter((el) => el.type === "file")[2];
    const archivo = new File(["a,b,c"], "layout.csv", { type: "text/csv" });
    fireEvent.change(inputLayout, { target: { files: [archivo] } });

    await waitFor(() => expect(screen.getByText("layout.csv")).toBeInTheDocument());
  });

  it("ADR-147/ADR-157: aplicar un layout reemplaza la tabla, pero CONCILIA contra lo programado (un día no mencionado se marca como faltante, no desaparece)", async () => {
    const diaA = makeRow({ orden_estacion_dia_id: "dia-a", fecha: "2025-06-01", spots_diarios: 10 });
    const diaB = makeRow({ orden_estacion_dia_id: "dia-b", fecha: "2025-06-02", spots_diarios: 5 });
    const oe = makeOE({ periodo_transmision: [diaA, diaB] });

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-2",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      aplicados: [
        {
          orden_estacion_dia_id: "dia-a",
          fecha_transmision: "2025-06-01",
          hora_inicio: "07:00",
          spots: 15,
        },
        // ADR-157: dia-b no viene en el archivo — el backend lo manda igual, en 0
        // (conciliación completa contra lo programado, no un "no se menciona = sin
        // cambio").
        {
          orden_estacion_dia_id: "dia-b",
          fecha_transmision: "2025-06-02",
          hora_inicio: "07:00",
          spots: 0,
        },
      ],
      nuevos: [],
      errores: [{ fila: 3, motivo: "La estación 'Radio MTY' no coincide con la de esta orden." }],
    });

    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputLayout = inputs.filter((el) => el.type === "file")[2];
    fireEvent.change(inputLayout, {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });

    // dia-a (aplicado) pasa a 15 spots, con bonificación de +5 sobre lo programado (10).
    await waitFor(() => expect(screen.getByText("15")).toBeInTheDocument());
    expect(screen.getByText("+5 bonif.")).toBeInTheDocument();
    // ADR-157 (petición del usuario, corrige ADR-151): dia-b no vino en el archivo —
    // sigue mostrándose (ya NO desaparece), marcado como descuento completo (-5).
    expect(screen.getByText("2025-06-02")).toBeInTheDocument();
    expect(screen.getByText("-5 desc.")).toBeInTheDocument();
    expect(screen.queryByText("sin cambio")).toBeNull();

    expect(screen.getByText("Se aplicaron 2 día(s) a la tabla de reales.")).toBeInTheDocument();
    expect(screen.getByText("1 fila(s) no se aplicaron:")).toBeInTheDocument();
    expect(screen.getByText(/Radio MTY/)).toBeInTheDocument();
  });

  it("ADR-151: sin cargar ningún layout, la tabla sigue el flujo normal de siempre (periodo_transmision completo)", async () => {
    const diaA = makeRow({ orden_estacion_dia_id: "dia-a", fecha: "2025-06-01", spots_diarios: 10 });
    const diaB = makeRow({ orden_estacion_dia_id: "dia-b", fecha: "2025-06-02", spots_diarios: 5 });
    const oe = makeOE({ periodo_transmision: [diaA, diaB] });

    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    // Ambos días se ven, sin cambios (nadie cargó un layout ni editó nada a mano).
    expect(screen.getByText("2025-06-01")).toBeInTheDocument();
    expect(screen.getByText("2025-06-02")).toBeInTheDocument();
    expect(screen.getAllByText("sin cambio")).toHaveLength(2);
  });

  it("ADR-151: aplicados y días nuevos del layout conviven en la MISMA tabla (ya no hay una tabla aparte)", async () => {
    const diaA = makeRow({ orden_estacion_dia_id: "dia-a", fecha: "2025-06-01", spots_diarios: 10 });
    const oe = makeOE({ periodo_transmision: [diaA] });

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-5",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      aplicados: [
        { orden_estacion_dia_id: "dia-a", fecha_transmision: "2025-06-01", hora_inicio: "07:00", spots: 10 },
      ],
      nuevos: [{ fecha_transmision: "2025-07-01", hora_inicio: "09:00:00", spots: 6 }],
      errores: [],
    });

    const { container } = render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    fireEvent.change(inputs.filter((el) => el.type === "file")[2], {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });

    await waitFor(() => expect(screen.getByText("Nuevo")).toBeInTheDocument());
    // Una sola tabla en toda la pantalla, con ambas filas dentro.
    expect(container.querySelectorAll("table.cat-table")).toHaveLength(1);
    expect(screen.getByText("2025-06-01")).toBeInTheDocument();
    expect(screen.getByText("2025-07-01")).toBeInTheDocument();
  });

  it("ADR-149: una fecha+hora del layout que no existe se propone como día nuevo, y se puede quitar antes de avanzar", async () => {
    const oe = makeOE();
    const onAvanzar = vi.fn();

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-3",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      aplicados: [],
      nuevos: [{ fecha_transmision: "2025-07-01", hora_inicio: "09:00:00", spots: 6 }],
      errores: [],
    });

    render(<RealesForm oe={oe} onAvanzar={onAvanzar} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputLayout = inputs.filter((el) => el.type === "file")[2];
    fireEvent.change(inputLayout, {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });

    // ADR-151: el día nuevo aparece dentro de la tabla PRINCIPAL (no en una tabla
    // aparte), marcado con la etiqueta "Nuevo".
    await waitFor(() => expect(screen.getByText("2025-07-01")).toBeInTheDocument());
    expect(screen.getByText("09:00")).toBeInTheDocument();
    expect(screen.getByText("Nuevo")).toBeInTheDocument();
    expect(
      screen.getByText("1 día(s) nuevo(s) listo(s) para crear al avanzar a 2.3."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Avanzar a 2.3 →" }));
    expect(onAvanzar).toHaveBeenCalledTimes(1);
    const [, extra] = onAvanzar.mock.calls[0];
    expect(extra.diasNuevos).toEqual([{ fecha: "2025-07-01", hora: "09:00", spots: 6 }]);
  });

  it("ADR-160 (petición del usuario): un día nuevo del layout cuenta como bonificación en el panel de 'Al avanzar a 2.3 se generarán'", async () => {
    const diaA = makeRow({ orden_estacion_dia_id: "dia-a", fecha: "2025-06-01", spots_diarios: 10 });
    const oe = makeOE({ periodo_transmision: [diaA], precio_spot: 800 });

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-8",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      // dia-a sin cambio (sigue en 10) — el backend NUNCA deja de mandar los días ya
      // existentes (ADR-157), aquí se simula el caso "sin cambio" explícitamente.
      aplicados: [
        {
          orden_estacion_dia_id: "dia-a",
          fecha_transmision: "2025-06-01",
          hora_inicio: "07:00",
          spots: 10,
        },
      ],
      // 2 spots que antes NO existían en esta OE — un día nuevo.
      nuevos: [{ fecha_transmision: "2025-07-01", hora_inicio: "09:00:00", spots: 2 }],
      errores: [],
    });

    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputLayout = inputs.filter((el) => el.type === "file")[2];
    fireEvent.change(inputLayout, {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });

    await waitFor(() => expect(screen.getByText("Nuevo")).toBeInTheDocument());

    // ANTES de ADR-160: el panel ignoraba por completo los días nuevos — "no los
    // registró como bonificaciones" (petición del usuario). Ahora sí cuentan: 2 spots
    // nuevos a $800 c/u = +$1,600.00, y se refleja también en "Reales".
    expect(screen.getByText("• 1 bonificación(es)")).toBeInTheDocument();
    expect(screen.queryByText(/descuento\(s\)/)).toBeNull();
    expect(screen.getByText("+$1,600.00")).toBeInTheDocument();
    expect(screen.getByText(/Programados 10 spots → Reales 12/)).toBeInTheDocument();
  });

  it("ADR-152: un día nuevo fuera de la campaña de la OC se marca en la tabla y bloquea 'Avanzar'", async () => {
    const oe = makeOE();
    const oc = makeOC({ fecha_inicio_campania: "2025-06-01", fecha_fin_campania: "2025-06-30" });
    const onAvanzar = vi.fn();

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-6",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      aplicados: [],
      // 2025-07-01 cae FUERA de la campaña de `oc` (2025-06-01 a 2025-06-30).
      nuevos: [{ fecha_transmision: "2025-07-01", hora_inicio: "09:00:00", spots: 6 }],
      errores: [],
    });

    render(<RealesForm oe={oe} oc={oc} onAvanzar={onAvanzar} onCancelar={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    fireEvent.change(inputs.filter((el) => el.type === "file")[2], {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });

    await waitFor(() =>
      expect(screen.getByText(/Fuera del rango de campaña/)).toBeInTheDocument(),
    );
    const botonAvanzar = screen.getByRole("button", { name: "Avanzar a 2.3 →" });
    expect(botonAvanzar).toBeDisabled();

    fireEvent.click(botonAvanzar);
    expect(onAvanzar).not.toHaveBeenCalled();
  });

  it("ADR-153: editar la Fecha de un día nuevo (sin tocar el archivo) corrige el error y habilita 'Avanzar'", async () => {
    const oe = makeOE();
    const oc = makeOC({ fecha_inicio_campania: "2025-06-01", fecha_fin_campania: "2025-06-30" });
    const onAvanzar = vi.fn();

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-7",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      aplicados: [],
      nuevos: [{ fecha_transmision: "2025-07-01", hora_inicio: "09:00:00", spots: 6 }],
      errores: [],
    });

    render(<RealesForm oe={oe} oc={oc} onAvanzar={onAvanzar} onCancelar={vi.fn()} />);
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    fireEvent.change(inputs.filter((el) => el.type === "file")[2], {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText(/Fuera del rango de campaña/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Editar" }));
    const inputFecha = document.querySelector('input[type="date"]') as HTMLInputElement;
    expect(inputFecha).not.toBeNull();
    fireEvent.change(inputFecha, { target: { value: "2025-06-15" } });
    fireEvent.click(screen.getByRole("button", { name: "✓ OK" }));

    expect(screen.queryByText(/Fuera del rango de campaña/)).toBeNull();
    const botonAvanzar = screen.getByRole("button", { name: "Avanzar a 2.3 →" });
    expect(botonAvanzar).not.toBeDisabled();

    fireEvent.click(botonAvanzar);
    expect(onAvanzar).toHaveBeenCalledTimes(1);
    const [, extra] = onAvanzar.mock.calls[0];
    expect(extra.diasNuevos).toEqual([{ fecha: "2025-06-15", hora: "09:00", spots: 6 }]);
  });

  it("ADR-149: 'Quitar' en un día nuevo lo saca de la lista (no se manda al avanzar)", async () => {
    const oe = makeOE();
    const onAvanzar = vi.fn();

    vi.mocked(subirLayoutRealOrdenEstacionApi).mockResolvedValueOnce({
      archivo: {
        orden_estacion_layout_real_id: "lr-4",
        orden_estacion_id: oe.id,
        nombre_archivo: "layout.csv",
        created_at: "2026-09-30T00:00:00",
      },
      aplicados: [],
      nuevos: [{ fecha_transmision: "2025-07-01", hora_inicio: "09:00:00", spots: 6 }],
      errores: [],
    });

    render(<RealesForm oe={oe} onAvanzar={onAvanzar} onCancelar={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    fireEvent.change(inputs.filter((el) => el.type === "file")[2], {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText("2025-07-01")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "✕" }));
    expect(screen.queryByText("2025-07-01")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Avanzar a 2.3 →" }));
    const [, extra] = onAvanzar.mock.calls[0];
    expect(extra.diasNuevos).toEqual([]);
  });

  it("ADR-150: clic en 'Cancelar' + desmontar borra el layout subido EN ESTA SESIÓN", async () => {
    const oe = makeOE();
    const onCancelar = vi.fn();
    const { unmount } = render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={onCancelar} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputLayout = inputs.filter((el) => el.type === "file")[2];
    fireEvent.change(inputLayout, {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText("layout.csv")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onCancelar).toHaveBeenCalledTimes(1);
    // En la app real, `onCancelar` hace que el padre quite este componente del árbol —
    // aquí se simula desmontándolo explícitamente.
    unmount();

    await waitFor(() =>
      expect(eliminarLayoutRealOrdenEstacionApi).toHaveBeenCalledWith(oe.id, "lr-1"),
    );
  });

  it("ADR-150: salir SIN tocar 'Cancelar' (navegar a otra sección) también borra el layout de esta sesión", async () => {
    // Reproduce el bug reportado: el usuario sube un layout y abandona la pantalla de
    // Capturar Reales por cualquier otra vía (no el botón Cancelar) — el archivo subido
    // en esta sesión debe borrarse igual, porque la limpieza ahora vive en el
    // desmontaje del componente, no en el click de un botón en particular.
    vi.mocked(eliminarLayoutRealOrdenEstacionApi).mockClear();
    const oe = makeOE();
    const { unmount } = render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    fireEvent.change(inputs.filter((el) => el.type === "file")[2], {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText("layout.csv")).toBeInTheDocument());

    unmount(); // sin clic en "Cancelar" ni en "Avanzar a 2.3"

    await waitFor(() =>
      expect(eliminarLayoutRealOrdenEstacionApi).toHaveBeenCalledWith(oe.id, "lr-1"),
    );
  });

  it("ADR-150: NO borra un layout que ya existía antes de abrir la pantalla, aunque se desmonte", async () => {
    vi.mocked(eliminarLayoutRealOrdenEstacionApi).mockClear();
    vi.mocked(listarLayoutRealesOrdenEstacionApi).mockResolvedValueOnce([
      {
        orden_estacion_layout_real_id: "lr-viejo",
        orden_estacion_id: "oe-cualquiera",
        nombre_archivo: "layout-anterior.csv",
        created_at: "2026-09-29T00:00:00",
      },
    ]);
    const oe = makeOE();
    const onCancelar = vi.fn();
    const { unmount } = render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={onCancelar} />);

    await waitFor(() => expect(screen.getByText("layout-anterior.csv")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Cancelar/ }));
    expect(onCancelar).toHaveBeenCalledTimes(1);
    unmount();

    expect(eliminarLayoutRealOrdenEstacionApi).not.toHaveBeenCalled();
  });

  it("ADR-150: si 'Avanzar a 2.3' tuvo éxito, desmontar NO borra el layout recién subido", async () => {
    const oe = makeOE();
    const { unmount, rerender } = render(
      <RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />,
    );

    await waitFor(() =>
      expect(screen.getByText("Carga de Órdenes Reales Desde Layout")).toBeInTheDocument(),
    );
    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    fireEvent.change(inputs.filter((el) => el.type === "file")[2], {
      target: { files: [new File(["a,b,c"], "layout.csv", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText("layout.csv")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Avanzar a 2.3 →" }));
    // El padre real recibiría `onAvanzar`, haría el `await` y solo ENTONCES desmontaría
    // esta pantalla — aquí se simula con un `submitting` transitorio y luego el desmontaje.
    rerender(<RealesForm oe={oe} submitting onAvanzar={vi.fn()} onCancelar={vi.fn()} />);
    unmount();

    expect(eliminarLayoutRealOrdenEstacionApi).not.toHaveBeenCalled();
  });

  it("'Cargar Formato de Horarios Reales Enviado al Cliente' rechaza audio en el front", async () => {
    const oe = makeOE();
    render(<RealesForm oe={oe} onAvanzar={vi.fn()} onCancelar={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByText("Cargar Formato de Horarios Reales Enviado al Cliente")).toBeInTheDocument(),
    );

    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputCliente = inputs.filter((el) => el.type === "file")[3];
    const archivo = new File(["contenido"], "cancion.mp3", { type: "audio/mpeg" });
    fireEvent.change(inputCliente, { target: { files: [archivo] } });

    await waitFor(() =>
      expect(screen.getByText(/Formato no permitido \(ejecutable\/script\/audio\): \.mp3/)).toBeInTheDocument(),
    );
  });
});
