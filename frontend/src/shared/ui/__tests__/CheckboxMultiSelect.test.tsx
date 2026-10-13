/** Cubre el desplegable de casillas (ADR-187, `PeriodoTransmisionGrid.tsx`). Incluye la
 * regresión real: arrastrar la barra de scroll de un contenedor ANCESTRO (p.ej. el panel
 * con `overflow: auto` donde vive la grid) no debe cerrar el panel — antes sí lo hacía,
 * porque ese `mousedown` se detectaba como "clic afuera".
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CheckboxMultiSelect } from "../CheckboxMultiSelect";
import type { OpcionBuscable } from "../SearchableSelect";

const OPCIONES: OpcionBuscable[] = [
  { value: "a", label: "material-a.mp3" },
  { value: "b", label: "material-b.mp3" },
  { value: "c", label: "material-c.mp3" },
];

describe("CheckboxMultiSelect — panel de casillas", () => {
  it("el campo cerrado muestra el placeholder sin selección, y abre el panel al hacer clic", () => {
    render(<CheckboxMultiSelect value={[]} onChange={vi.fn()} options={OPCIONES} placeholder="Elige…" />);
    expect(screen.getByRole("button", { name: "Elige…" })).toBeInTheDocument();
    expect(screen.queryByText("[Selecciona todos]")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Elige…" }));
    expect(screen.getByText("[Selecciona todos]")).toBeInTheDocument();
    OPCIONES.forEach((o) => expect(screen.getByLabelText(o.label)).toBeInTheDocument());
  });

  it("marcar una casilla la agrega; desmarcarla la quita", () => {
    const onChange = vi.fn();
    render(<CheckboxMultiSelect value={["a"]} onChange={onChange} options={OPCIONES} />);
    fireEvent.click(screen.getByRole("button"));

    fireEvent.click(screen.getByLabelText("material-b.mp3"));
    expect(onChange).toHaveBeenCalledWith(["a", "b"]);

    fireEvent.click(screen.getByLabelText("material-a.mp3"));
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("'[Selecciona todos]' marca todas las opciones visibles; al volver a hacer clic, las desmarca", () => {
    const onChange = vi.fn();
    render(<CheckboxMultiSelect value={[]} onChange={onChange} options={OPCIONES} />);
    fireEvent.click(screen.getByRole("button"));

    fireEvent.click(screen.getByText("[Selecciona todos]"));
    expect(onChange).toHaveBeenCalledWith(["a", "b", "c"]);
  });

  it("con maxSelected, las opciones no elegidas se deshabilitan al llegar al tope (pero se pueden desmarcar)", () => {
    render(<CheckboxMultiSelect value={["a", "b"]} onChange={vi.fn()} options={OPCIONES} maxSelected={2} />);
    fireEvent.click(screen.getByRole("button"));

    expect(screen.getByLabelText("material-c.mp3")).toBeDisabled();
    expect(screen.getByLabelText("material-a.mp3")).not.toBeDisabled();
  });

  it("un nombre largo se abrevia a 20 caracteres + '…' en el campo cerrado y en la casilla", () => {
    const largo: OpcionBuscable[] = [{ value: "x", label: "un-nombre-de-archivo-realmente-largo.mp3" }];
    render(<CheckboxMultiSelect value={["x"]} onChange={vi.fn()} options={largo} />);
    const abreviado = "un-nombre-de-archivo…";
    expect(screen.getByRole("button", { name: abreviado })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: abreviado }));
    expect(screen.getByLabelText(abreviado)).toBeInTheDocument();
  });

  it("clic genuino afuera (un elemento HERMANO, no ancestro) cierra el panel", () => {
    render(
      <div>
        <CheckboxMultiSelect value={[]} onChange={vi.fn()} options={OPCIONES} />
        <div data-testid="hermano">Otro contenido de la página</div>
      </div>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("[Selecciona todos]")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId("hermano"));
    expect(screen.queryByText("[Selecciona todos]")).toBeNull();
  });

  it("corrige un bug real: arrastrar el scroll de un contenedor ANCESTRO (overflow: auto) no cierra el panel", () => {
    render(
      <div data-testid="contenedor-con-scroll" style={{ overflow: "auto" }}>
        <table>
          <tbody>
            <tr>
              <td>
                <CheckboxMultiSelect value={[]} onChange={vi.fn()} options={OPCIONES} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("[Selecciona todos]")).toBeInTheDocument();

    // jsdom no hace layout real — se simula un contenedor de 300x200 con una barra de
    // scroll vertical de 20px (clientWidth 280 < el ancho real) y se dispara el
    // `mousedown` justo en esa franja (x=290), que es donde cae un clic en la barra.
    const contenedor = screen.getByTestId("contenedor-con-scroll");
    vi.spyOn(contenedor, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, right: 300, bottom: 200, width: 300, height: 200, x: 0, y: 0, toJSON: () => {},
    });
    Object.defineProperty(contenedor, "clientWidth", { value: 280, configurable: true });
    Object.defineProperty(contenedor, "clientHeight", { value: 200, configurable: true });

    fireEvent.mouseDown(contenedor, { clientX: 290, clientY: 100 });
    expect(screen.getByText("[Selecciona todos]")).toBeInTheDocument();
  });

  it("un clic genuino en el FONDO de ese mismo contenedor ancestro (dentro de su área de contenido, no la barra de scroll) SÍ cierra el panel", () => {
    render(
      <div data-testid="contenedor-con-scroll" style={{ overflow: "auto" }}>
        <table>
          <tbody>
            <tr>
              <td>
                <CheckboxMultiSelect value={[]} onChange={vi.fn()} options={OPCIONES} />
              </td>
            </tr>
          </tbody>
        </table>
      </div>,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("[Selecciona todos]")).toBeInTheDocument();

    const contenedor = screen.getByTestId("contenedor-con-scroll");
    vi.spyOn(contenedor, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, right: 300, bottom: 200, width: 300, height: 200, x: 0, y: 0, toJSON: () => {},
    });
    Object.defineProperty(contenedor, "clientWidth", { value: 280, configurable: true });
    Object.defineProperty(contenedor, "clientHeight", { value: 200, configurable: true });

    // x=50 cae DENTRO del área de contenido (clientWidth=280) — un clic de verdad en el
    // fondo del formulario, no en su barra de scroll.
    fireEvent.mouseDown(contenedor, { clientX: 50, clientY: 100 });
    expect(screen.queryByText("[Selecciona todos]")).toBeNull();
  });
});
