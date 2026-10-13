import { describe, expect, it } from "vitest";

import { problemasDeFila } from "../components/PeriodoTransmisionGrid";
import { makeRow } from "./fixtures";

const RANGO = { inicio: "2025-06-01", fin: "2025-06-30" };

describe("problemasDeFila", () => {
  it("una fila válida no reporta problemas", () => {
    expect(problemasDeFila(makeRow({ fecha: "2025-06-15" }), RANGO)).toEqual([]);
  });

  it("rechaza una fecha anterior al inicio de la campaña", () => {
    const problemas = problemasDeFila(makeRow({ fecha: "2025-05-31" }), RANGO);
    expect(problemas).toContain("La fecha cae fuera del rango de la campaña.");
  });

  it("rechaza una fecha posterior al fin de la campaña", () => {
    const problemas = problemasDeFila(makeRow({ fecha: "2025-07-01" }), RANGO);
    expect(problemas).toContain("La fecha cae fuera del rango de la campaña.");
  });

  it("acepta las fechas límite del rango (inclusivas)", () => {
    expect(problemasDeFila(makeRow({ fecha: "2025-06-01" }), RANGO)).toEqual([]);
    expect(problemasDeFila(makeRow({ fecha: "2025-06-30" }), RANGO)).toEqual([]);
  });

  it("rechaza fecha vacía", () => {
    const problemas = problemasDeFila(makeRow({ fecha: "" }), RANGO);
    expect(problemas).toContain("Falta la fecha.");
  });

  it("rechaza horario vacío", () => {
    const problemas = problemasDeFila(makeRow({ hora_inicio: "", hora_termino: "" }), RANGO);
    expect(problemas).toContain("Falta el horario de transmisión.");
  });

  // ADR-185 (petición del usuario, revierte ADR-108): "Hora Inicio"/"Hora Fin" vuelven a
  // ser un rango real — un mismo valor en ambas sigue siendo válido (spot puntual), pero
  // Hora Fin anterior a Hora Inicio ya se rechaza.
  it("ADR-185: acepta hora_inicio == hora_termino, rechaza hora_termino < hora_inicio", () => {
    expect(problemasDeFila(makeRow({ hora_inicio: "08:00", hora_termino: "08:00" }), RANGO)).toEqual([]);
    expect(problemasDeFila(makeRow({ hora_inicio: "10:00", hora_termino: "09:00" }), RANGO)).toContain(
      '"Hora Fin" no puede ser anterior a "Hora Inicio".',
    );
  });

  it("rechaza spots_diarios en 0 o negativos", () => {
    expect(problemasDeFila(makeRow({ spots_diarios: 0 }), RANGO)).toContain("Los spots del día deben ser mayores a 0.");
    expect(problemasDeFila(makeRow({ spots_diarios: -3 }), RANGO)).toContain("Los spots del día deben ser mayores a 0.");
  });

  it("una fila puede acumular varios problemas a la vez", () => {
    const problemas = problemasDeFila(makeRow({ fecha: "", hora_inicio: "", spots_diarios: 0 }), RANGO);
    expect(problemas.length).toBeGreaterThanOrEqual(3);
  });
});
