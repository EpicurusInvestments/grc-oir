/** ADR-119: "Capturar Reales" ya no captura `testigos_url`/`testigos_ubicacion_alterna`
 * — se reemplazan por "Evidencias de lo Transmitido" (mismo patrón de audios que
 * "Material a Transmitir", ver `EvidenciasTransmitido.tsx`).
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RealesForm } from "../ordenEstacion/components/RealesForm";
import { makeOE } from "./fixtures";

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

    await waitFor(() => expect(screen.getByText("Formato de Horarios Reales")).toBeInTheDocument());
    expect(screen.getByText("Sin archivos subidos todavía.")).toBeInTheDocument();

    const inputs = screen.getAllByDisplayValue("") as HTMLInputElement[];
    const inputFormato = inputs.filter((el) => el.type === "file")[1];
    const archivo = new File(["contenido"], "horarios.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    fireEvent.change(inputFormato, { target: { files: [archivo] } });

    await waitFor(() => expect(screen.getByText("horarios.xlsx")).toBeInTheDocument());
  });
});
