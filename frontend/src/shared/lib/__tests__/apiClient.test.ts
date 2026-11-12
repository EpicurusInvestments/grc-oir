/** El apiClient frente a la sesión: manda el token y reacciona al 401. */

import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiRequestError, apiClient } from "@/shared/lib/apiClient";
import {
  guardarToken,
  notificarSesionExpirada,
  registrarManejadorSesionExpirada,
} from "@/shared/lib/session";

/** Adaptador falso: responde sin red y deja ver la petición que se habría enviado. */
function responderCon(status: number, data: unknown = {}): AxiosAdapter {
  return async (config: InternalAxiosRequestConfig) => {
    const respuesta = {
      data,
      status,
      statusText: "",
      headers: config.headers,
      config,
    } as AxiosResponse;

    if (status >= 400) {
      return Promise.reject(Object.assign(new Error("http"), { config, response: respuesta }));
    }
    return respuesta;
  };
}

const adaptadorOriginal = apiClient.defaults.adapter;

describe("apiClient", () => {
  beforeEach(() => {
    window.localStorage.clear();
    registrarManejadorSesionExpirada(null);
  });

  afterEach(() => {
    apiClient.defaults.adapter = adaptadorOriginal;
  });

  it("adjunta Authorization: Bearer cuando hay token", async () => {
    guardarToken("token-abc");
    apiClient.defaults.adapter = responderCon(200);

    const res = await apiClient.get("/catalogos/plazas");

    expect(res.config.headers.Authorization).toBe("Bearer token-abc");
  });

  it("no manda Authorization si no hay sesión", async () => {
    apiClient.defaults.adapter = responderCon(200);

    const res = await apiClient.get("/catalogos/plazas");

    expect(res.config.headers.Authorization).toBeUndefined();
  });

  it("un 401 en una petición normal cierra la sesión", async () => {
    guardarToken("token-vencido");
    const alExpirar = vi.fn();
    registrarManejadorSesionExpirada(alExpirar);
    apiClient.defaults.adapter = responderCon(401, {
      error: { codigo: "no_autenticado", mensaje: "Sesión inválida o expirada." },
    });

    await expect(apiClient.get("/catalogos/plazas")).rejects.toThrow();

    expect(alExpirar).toHaveBeenCalledOnce();
    expect(window.localStorage.getItem("grcoir.token")).toBeNull();
  });

  it("un 401 del LOGIN son credenciales incorrectas, no sesión expirada", async () => {
    const alExpirar = vi.fn();
    registrarManejadorSesionExpirada(alExpirar);
    apiClient.defaults.adapter = responderCon(401, {
      error: { codigo: "no_autenticado", mensaje: "Usuario o contraseña incorrectos." },
    });

    await expect(apiClient.post("/auth/login", {})).rejects.toThrow(
      "Usuario o contraseña incorrectos.",
    );

    // Si se tratara como expiración, un intento fallido expulsaría al usuario de /login.
    expect(alExpirar).not.toHaveBeenCalled();
  });

  it("notificarSesionExpirada borra el token aunque no haya manejador", () => {
    guardarToken("token-abc");
    notificarSesionExpirada();
    expect(window.localStorage.getItem("grcoir.token")).toBeNull();
  });

  // ADR-260 (corrige un bug real, petición del usuario con captura): un 422 solo
  // mostraba "Datos de entrada inválidos" sin decir qué campo — el detalle de Pydantic
  // (loc/msg) se enriquece en el mensaje del error, no solo en `detalles`.
  it("ADR-260: un 422 de validación arma el mensaje con el campo y la razón de cada error", async () => {
    apiClient.defaults.adapter = responderCon(422, {
      error: {
        codigo: "validacion",
        mensaje: "Datos de entrada inválidos",
        detalles: [
          { type: "missing", loc: ["body", "anunciante_id"], msg: "Field required" },
          { type: "missing", loc: ["body", "fecha_venta"], msg: "Field required" },
        ],
      },
    });

    await expect(apiClient.post("/ordenes/clientes", {})).rejects.toThrow(
      "Datos de entrada inválidos — anunciante_id: Field required; fecha_venta: Field required",
    );
  });

  it("ADR-260: un error SIN detalles (u otro código) conserva el mensaje tal cual", async () => {
    apiClient.defaults.adapter = responderCon(400, {
      error: { codigo: "error_dominio", mensaje: "La factura ya está cancelada." },
    });

    await expect(apiClient.post("/facturacion/clientes/x/cancelar", {})).rejects.toThrow(
      "La factura ya está cancelada.",
    );
  });

  it("ADR-260: ApiRequestError sigue exponiendo `detalles` crudo para quien lo necesite", async () => {
    const detalles = [{ type: "missing", loc: ["body", "anunciante_id"], msg: "Field required" }];
    apiClient.defaults.adapter = responderCon(422, {
      error: { codigo: "validacion", mensaje: "Datos de entrada inválidos", detalles },
    });

    try {
      await apiClient.post("/ordenes/clientes", {});
      throw new Error("no debió llegar aquí");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiRequestError);
      expect((e as ApiRequestError).detalles).toEqual(detalles);
    }
  });
});
