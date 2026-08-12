import { describe, expect, it } from "vitest";

import { checklistProgress, FROZEN_STATES, isChecklistComplete, ODC_REVIEW_CHECKLIST, rootBadgeClass, rootLabel, rootState } from "../constants";

describe("isChecklistComplete / checklistProgress", () => {
  const TODOS_LOS_KEYS = ODC_REVIEW_CHECKLIST.map((it) => it.key);

  function checklistCompleto(): Record<string, boolean> {
    return Object.fromEntries(TODOS_LOS_KEYS.map((k) => [k, true]));
  }

  it("checklist undefined no está completo y tiene progreso 0", () => {
    expect(isChecklistComplete(undefined)).toBe(false);
    expect(checklistProgress(undefined)).toBe(0);
  });

  it("checklist vacío no está completo", () => {
    expect(isChecklistComplete({})).toBe(false);
    expect(checklistProgress({})).toBe(0);
  });

  it("9 de 10 no está completo (el checklist es todo o nada)", () => {
    const nueve = checklistCompleto();
    delete nueve[TODOS_LOS_KEYS[0]];
    expect(isChecklistComplete(nueve)).toBe(false);
    expect(checklistProgress(nueve)).toBe(9);
  });

  it("10 de 10 sí está completo", () => {
    const completo = checklistCompleto();
    expect(isChecklistComplete(completo)).toBe(true);
    expect(checklistProgress(completo)).toBe(10);
  });

  it("claves ajenas al checklist (typos, campos futuros) no inflan el progreso ni cuentan como completo", () => {
    const conBasura = checklistCompleto();
    delete conBasura[TODOS_LOS_KEYS[0]];
    conBasura["clave_que_no_existe"] = true;
    expect(checklistProgress(conBasura)).toBe(9);
    expect(isChecklistComplete(conBasura)).toBe(false);
  });
});

describe("rootState / rootLabel — jerarquía v5 de 5 raíces", () => {
  it("mapea cada EstadoOC a su raíz numérica esperada", () => {
    expect(rootState("orden_cliente_sin_vobo")).toBe(1);
    expect(rootState("orden_cliente_con_vobo")).toBe(1);
    expect(rootState("orden_interna")).toBe(2);
    expect(rootState("orden_cerrada")).toBe(3);
    expect(rootState("facturada_archivo_plano")).toBe(4);
    expect(rootState("facturada_timbrada")).toBe(4);
    expect(rootState("cobrada")).toBe(5);
  });

  it("cancelada no tiene raíz (null), no una raíz inventada", () => {
    expect(rootState("cancelada")).toBeNull();
  });

  it("rootLabel antepone el número de raíz al nombre, salvo en cancelada", () => {
    expect(rootLabel("orden_interna")).toBe("2 · Orden interna");
    expect(rootLabel("cancelada")).toBe("Cancelada");
  });
});

describe("rootBadgeClass", () => {
  it("regresa la clase de badge correcta para cada raíz 1-5", () => {
    expect(rootBadgeClass(1)).toBe("b-red");
    expect(rootBadgeClass(2)).toBe("b-blue");
    expect(rootBadgeClass(3)).toBe("b-teal");
    expect(rootBadgeClass(4)).toBe("b-purple");
    expect(rootBadgeClass(5)).toBe("b-dark");
  });

  it("null cae en 'cancel' (b-gray)", () => {
    expect(rootBadgeClass(null)).toBe("b-gray");
  });

  it("una raíz numérica desconocida no revienta: cae al fallback b-gray", () => {
    expect(rootBadgeClass(99)).toBe("b-gray");
  });
});

describe("FROZEN_STATES — no debe repetir el bug del prototipo HTML", () => {
  it("contiene exactamente los 4 estados congelados correctos", () => {
    expect(FROZEN_STATES).toEqual(["orden_cerrada", "facturada_archivo_plano", "facturada_timbrada", "cobrada"]);
  });

  it("NO contiene 'facturada' a secas (el valor inexistente que trae el HTML aprobado)", () => {
    expect(FROZEN_STATES).not.toContain("facturada");
  });

  it("no marca como congelados los estados 1.x ni el estado 2 (orden_interna)", () => {
    expect(FROZEN_STATES).not.toContain("orden_cliente_sin_vobo");
    expect(FROZEN_STATES).not.toContain("orden_cliente_con_vobo");
    expect(FROZEN_STATES).not.toContain("orden_interna");
  });
});
