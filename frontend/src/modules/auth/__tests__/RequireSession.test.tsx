import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireSession } from "@/modules/auth/components/RequireSession";
import { LoginPage } from "@/modules/auth/pages/LoginPage";
import { SessionProvider } from "@/modules/auth/session";
import { cerrarSesionActual } from "@/shared/lib/currentUser";
import { notificarSesionExpirada } from "@/shared/lib/session";

vi.mock("@/modules/auth/api", () => ({
  login: vi.fn(),
  obtenerSesion: vi.fn(),
}));

const { login, obtenerSesion } = await import("@/modules/auth/api");
const obtenerSesionMock = vi.mocked(obtenerSesion);
const loginMock = vi.mocked(login);

const USUARIO = {
  usuario_id: "0000-1",
  nombre_usuario: "ada.admin",
  email: "ada@grcoir.com",
  area: "admin",
};

function renderProtegido() {
  return render(
    <SessionProvider>
      <MemoryRouter initialEntries={["/catalogos"]}>
        <Routes>
          <Route path="/login" element={<div>Pantalla de login</div>} />
          <Route element={<RequireSession />}>
            <Route path="/catalogos" element={<div>Contenido protegido</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </SessionProvider>,
  );
}

describe("RequireSession", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it("sin sesión, redirige a /login sin mostrar el contenido", () => {
    renderProtegido();

    expect(screen.getByText("Pantalla de login")).toBeInTheDocument();
    expect(screen.queryByText("Contenido protegido")).not.toBeInTheDocument();
  });

  it("con token guardado, espera a validarlo en vez de rebotar a /login", () => {
    window.localStorage.setItem("grcoir.token", "token-guardado");
    obtenerSesionMock.mockReturnValue(new Promise(() => {})); // nunca resuelve

    renderProtegido();

    expect(screen.getByRole("status")).toHaveTextContent("Verificando sesión…");
    expect(screen.queryByText("Pantalla de login")).not.toBeInTheDocument();
  });

  it("token válido: muestra el contenido protegido", async () => {
    window.localStorage.setItem("grcoir.token", "token-guardado");
    obtenerSesionMock.mockResolvedValue({
      usuario_id: "0000-1",
      nombre_usuario: "ada.admin",
      email: "ada@grcoir.com",
      area: "admin",
    });

    renderProtegido();

    expect(await screen.findByText("Contenido protegido")).toBeInTheDocument();
  });

  it("token inválido o expirado: lo descarta y manda a /login", async () => {
    window.localStorage.setItem("grcoir.token", "token-vencido");
    obtenerSesionMock.mockRejectedValue(new Error("401"));

    renderProtegido();

    expect(await screen.findByText("Pantalla de login")).toBeInTheDocument();
    expect(window.localStorage.getItem("grcoir.token")).toBeNull();
  });
});

/** A dónde se aterriza tras autenticarse. Son dos casos que se ven igual (la misma
 *  pantalla de login) pero deben terminar en destinos distintos. */
describe("destino después de iniciar sesión", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    loginMock.mockResolvedValue({
      access_token: "token-nuevo",
      token_type: "bearer",
      expira_en: "2026-08-12T20:00:00Z",
      usuario: USUARIO,
    });
  });

  function renderApp(rutaInicial: string) {
    return render(
      <SessionProvider>
        <MemoryRouter initialEntries={[rutaInicial]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireSession />}>
              <Route path="/" element={<div>Dashboard</div>} />
              <Route path="/catalogos" element={<div>Catálogos</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </SessionProvider>,
    );
  }

  function entrar() {
    fireEvent.change(screen.getByLabelText(/correo electrónico/i), {
      target: { value: "ada@grcoir.com" },
    });
    fireEvent.change(screen.getByLabelText(/contraseña/i), {
      target: { value: "Contrasena-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /entrar/i }));
  }

  it("login DESDE CERO lleva al Dashboard, aunque la URL pedida fuera otra", async () => {
    // Sin sesión previa: escribir /catalogos en la barra no es "retomar una tarea".
    renderApp("/catalogos");
    entrar();

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Catálogos")).not.toBeInTheDocument();
  });

  it("si la sesión EXPIRÓ trabajando, se vuelve a la pantalla interrumpida", async () => {
    window.localStorage.setItem("grcoir.token", "token-vigente");
    obtenerSesionMock.mockResolvedValue(USUARIO);

    renderApp("/catalogos");
    expect(await screen.findByText("Catálogos")).toBeInTheDocument();

    // El backend responde 401 a media tarea (token vencido / usuario desactivado).
    notificarSesionExpirada();

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeInTheDocument();
    entrar();

    expect(await screen.findByText("Catálogos")).toBeInTheDocument();
  });

  it("tras cerrar sesión a propósito se entra al Dashboard, no a donde estaba", async () => {
    window.localStorage.setItem("grcoir.token", "token-vigente");
    obtenerSesionMock.mockResolvedValue(USUARIO);

    renderApp("/catalogos");
    expect(await screen.findByText("Catálogos")).toBeInTheDocument();

    cerrarSesionActual();

    expect(await screen.findByRole("button", { name: /entrar/i })).toBeInTheDocument();
    entrar();

    expect(await screen.findByText("Dashboard")).toBeInTheDocument();
  });
});
