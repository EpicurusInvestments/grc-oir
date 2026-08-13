/** El apiClient frente a la sesión: manda el token y reacciona al 401. */

import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/shared/lib/apiClient";
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
});
