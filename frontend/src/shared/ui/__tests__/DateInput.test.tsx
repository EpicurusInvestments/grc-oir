/** ADR-271c/ADR-272: `DateInput` reemplaza `<input type="date">` en todos los formularios
 * de captura — siempre se ve día/mes/año (2 dígitos de año), el valor por `onChange`
 * sigue siendo ISO "aaaa-mm-dd". Bug real reportado por el usuario (con captura): el panel del calendario
 * se abría SIEMPRE hacia abajo sin revisar si había espacio — con el campo cerca del
 * final del formulario, el mes y los días de la semana cabían pero la cuadrícula de
 * números quedaba fuera de la ventana (recortada por el borde de la pantalla, no por
 * CSS). La prueba de "abre el calendario" confirma que la cuadrícula de días SÍ existe en
 * el DOM — descarta que sea un problema de marcado/CSS y confirma que era de
 * posicionamiento (la lógica de "voltear hacia arriba" vive en un `useLayoutEffect` que
 * depende de medir el panel ya montado, no reproducible en jsdom con `getBoundingClientRect`
 * siempre en cero, así que no se prueba aquí el volteo en sí). */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DateInput } from "../DateInput";

describe("DateInput", () => {
  it("muestra el valor ISO recibido como día/mes/año (2 dígitos)", () => {
    render(<DateInput value="2026-11-17" onChange={vi.fn()} />);
    expect(screen.getByDisplayValue("17/11/26")).toBeInTheDocument();
  });

  it("al escribir día/mes/año completo y válido, llama a onChange con el ISO equivalente", () => {
    const onChange = vi.fn();
    render(<DateInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("dd/mm/aa"), { target: { value: "171126" } });
    expect(onChange).toHaveBeenCalledWith("2026-11-17");
  });

  it("rechaza una fecha imposible (30/02) y no llama a onChange", () => {
    const onChange = vi.fn();
    render(<DateInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("dd/mm/aa"), { target: { value: "300226" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("acepta un valor ISO puesto de golpe (compatibilidad con pruebas/paste)", () => {
    const onChange = vi.fn();
    render(<DateInput value="" onChange={onChange} />);
    fireEvent.change(screen.getByPlaceholderText("dd/mm/aa"), { target: { value: "2026-11-17" } });
    expect(onChange).toHaveBeenCalledWith("2026-11-17");
  });

  it("abre el calendario y la cuadrícula de días SÍ está en el DOM (descarta un problema de marcado/CSS)", () => {
    render(<DateInput value="2026-11-17" onChange={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir calendario" }));
    expect(screen.getAllByRole("gridcell").length).toBeGreaterThan(20);
  });

  it("elegir un día del calendario llama a onChange con el ISO de ese día y cierra el panel", () => {
    const onChange = vi.fn();
    render(<DateInput value="2026-11-17" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Abrir calendario" }));
    fireEvent.click(screen.getByRole("button", { name: "viernes, 20 de noviembre de 2026" }));
    expect(onChange).toHaveBeenCalledWith("2026-11-20");
    expect(screen.queryAllByRole("gridcell")).toHaveLength(0);
  });
});
