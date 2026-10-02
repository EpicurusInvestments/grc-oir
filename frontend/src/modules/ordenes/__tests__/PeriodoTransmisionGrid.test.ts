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

  // ADR-108: "Horario de transmisión" es UNA sola hora — hora_inicio/hora_termino se
  // capturan siempre iguales; ya no se valida un rango entre ambos.
  it("ADR-108: ya no valida un rango entre hora_inicio/hora_termino (es un solo horario)", () => {
    expect(problemasDeFila(makeRow({ hora_inicio: "08:00", hora_termino: "08:00" }), RANGO)).toEqual([]);
    expect(problemasDeFila(makeRow({ hora_inicio: "10:00", hora_termino: "09:00" }), RANGO)).toEqual([]);
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
