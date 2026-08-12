import { describe, expect, it } from "vitest";

import { diaDeSemana, fmtMonto, fmtPct, fmtRangoFechas, oGuion } from "../format";

describe("fmtMonto", () => {
  it("formatea como moneda MXN con 2 decimales por default", () => {
    expect(fmtMonto(1234567.891)).toBe("$1,234,567.89");
  });

  it("respeta sinDecimales", () => {
    expect(fmtMonto(1234567.891, { sinDecimales: true })).toBe("$1,234,568");
  });

  it("formatea negativos", () => {
    expect(fmtMonto(-1600)).toBe("-$1,600.00");
  });

  it("regresa — para null, undefined, NaN e Infinity", () => {
    expect(fmtMonto(null)).toBe("—");
    expect(fmtMonto(undefined)).toBe("—");
    expect(fmtMonto(NaN)).toBe("—");
    expect(fmtMonto(Infinity)).toBe("—");
  });

  it("formatea 0 como monto, no como vacío", () => {
    expect(fmtMonto(0)).toBe("$0.00");
  });
});

describe("fmtPct", () => {
  it("enteros sin decimales", () => {
    expect(fmtPct(4)).toBe("4%");
  });

  it("decimales se muestran sin ceros de sobra", () => {
    expect(fmtPct(4.5)).toBe("4.5%");
  });

  it("un decimal entero (4.50) se reduce a 4.5%, no dos ceros", () => {
    expect(fmtPct(4.5)).toBe("4.5%");
    expect(fmtPct(4.0)).toBe("4%");
  });

  it("regresa — para null/undefined/NaN", () => {
    expect(fmtPct(null)).toBe("—");
    expect(fmtPct(undefined)).toBe("—");
    expect(fmtPct(NaN)).toBe("—");
  });

  it("0% se muestra como 0%, no como —", () => {
    expect(fmtPct(0)).toBe("0%");
  });
});

describe("diaDeSemana", () => {
  it("calcula el día correcto en UTC (2025-01-01 es miércoles)", () => {
    expect(diaDeSemana("2025-01-01")).toBe("Miércoles");
  });

  it("calcula el día correcto para otra fecha conocida (2025-06-01 es domingo)", () => {
    expect(diaDeSemana("2025-06-01")).toBe("Domingo");
  });

  it("regresa — para fecha vacía", () => {
    expect(diaDeSemana("")).toBe("—");
  });
});

describe("fmtRangoFechas", () => {
  it("misma fecha de inicio y fin cuenta como 1 día (inclusivo), no 0", () => {
    expect(fmtRangoFechas("2025-06-15", "2025-06-15")).toBe("2025-06-15 → 2025-06-15 (1 días)");
  });

  it("un rango de un mes cuenta los días inclusive en ambos extremos", () => {
    // Junio tiene 30 días; del 1 al 30 son 30 días, no 29.
    expect(fmtRangoFechas("2025-06-01", "2025-06-30")).toBe("2025-06-01 → 2025-06-30 (30 días)");
  });

  it("regresa — si falta cualquiera de las dos fechas", () => {
    expect(fmtRangoFechas("", "2025-06-30")).toBe("—");
    expect(fmtRangoFechas("2025-06-01", "")).toBe("—");
  });
});

describe("oGuion", () => {
  it("regresa el valor si tiene contenido no vacío", () => {
    expect(oGuion("hola")).toBe("hola");
  });

  it("regresa — para null, undefined, vacío o solo espacios", () => {
    expect(oGuion(null)).toBe("—");
    expect(oGuion(undefined)).toBe("—");
    expect(oGuion("")).toBe("—");
    expect(oGuion("   ")).toBe("—");
  });
});
