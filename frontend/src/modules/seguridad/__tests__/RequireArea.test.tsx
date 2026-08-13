/** La fase Seguridad es exclusiva de Admin: guard de área + su entrada en el registro. */

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireArea } from "@/modules/auth/components/RequireArea";
import { RequireSession } from "@/modules/auth/components/RequireSession";
import { SessionProvider } from "@/modules/auth/session";
import { phaseRegistry } from "@/shared/phases/phaseRegistry";

vi.mock("@/modules/auth/api", () => ({
  login: vi.fn(),
  obtenerSesion: vi.fn(),
}));

const { obtenerSesion } = await import("@/modules/auth/api");
const obtenerSesionMock = vi.mocked(obtenerSesion);

function renderSeguridad() {
  return render(
    <SessionProvider>
      <MemoryRouter initialEntries={["/seguridad"]}>
        <Routes>
          <Route path="/login" element={<div>Pantalla de login</div>} />
          <Route element={<RequireSession />}>
            <Route path="/" element={<div>Dashboard</div>} />
            <Route element={<RequireArea areas={["admin"]} />}>
              <Route path="/seguridad" element={<div>Gestión de usuarios</div>} />
            </Route>
          </Route>
        </Routes>
      </MemoryRouter>
    </SessionProvider>,
  );
}

describe("fase Seguridad en el registro de fases", () => {
  it("está encendida y apunta a /seguridad", () => {
    const f5 = phaseRegistry.find((p) => p.key === "f5");

    expect(f5?.enabled).toBe(true);
    expect(f5?.route).toBe("/seguridad");
    // Color de fase rojo (mismo token de marca que el login).
    expect(f5?.accent).toBe("red");
  });
});

describe("RequireArea", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    window.localStorage.setItem("grcoir.token", "token-vigente");
  });

  it("un admin entra a la pantalla", async () => {
    obtenerSesionMock.mockResolvedValue({
      usuario_id: "0000-1",
      nombre_usuario: "ada.admin",
      email: "ada@grcoir.com",
      area: "admin",
    });

    renderSeguridad();

    expect(await screen.findByText("Gestión de usuarios")).toBeInTheDocument();
  });

  it("otra área NO entra, y recibe un mensaje claro en vez de una pantalla en blanco", async () => {
    obtenerSesionMock.mockResolvedValue({
      usuario_id: "0000-2",
      nombre_usuario: "vera.ventas",
      email: "vera@grcoir.com",
      area: "ventas",
    });

    renderSeguridad();

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent(/exclusiva del área/i);
    expect(aviso).toHaveTextContent("ventas");
    expect(screen.queryByText("Gestión de usuarios")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /volver al inicio/i })).toBeInTheDocument();
  });

  it("sin sesión no llega ni al guard de área", async () => {
    window.localStorage.clear();

    renderSeguridad();

    expect(await screen.findByText("Pantalla de login")).toBeInTheDocument();
  });
});
