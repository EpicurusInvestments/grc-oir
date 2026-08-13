import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "@/modules/auth/pages/LoginPage";
import { SessionProvider } from "@/modules/auth/session";
import { ApiRequestError } from "@/shared/lib/apiClient";

vi.mock("@/modules/auth/api", () => ({
  login: vi.fn(),
  obtenerSesion: vi.fn(),
}));

const { login } = await import("@/modules/auth/api");
const loginMock = vi.mocked(login);

function renderLogin() {
  return render(
    <SessionProvider>
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<div>Dashboard simulado</div>} />
        </Routes>
      </MemoryRouter>
    </SessionProvider>,
  );
}

/** Llena el formulario y lo envía. Se usa `fireEvent` (viene con testing-library) en vez
 *  de `user-event` para no añadir una dependencia solo por estas pruebas. */
function llenarYEnviar(email: string, password: string) {
  fireEvent.change(screen.getByLabelText(/correo electrónico/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /entrar/i }));
}

describe("LoginPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it("muestra el logo de Grupo Radio Centro y los campos de acceso", () => {
    renderLogin();

    expect(screen.getByAltText("Grupo Radio Centro")).toBeInTheDocument();
    expect(screen.getByLabelText(/correo electrónico/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /entrar/i })).toBeInTheDocument();
  });

  it("valida en el cliente antes de llamar al backend", async () => {
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /entrar/i }));

    expect(await screen.findByText("El correo es obligatorio.")).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("guarda el token y entra al dashboard cuando las credenciales son correctas", async () => {
    loginMock.mockResolvedValue({
      access_token: "token-de-prueba",
      token_type: "bearer",
      expira_en: "2026-08-12T20:00:00Z",
      usuario: {
        usuario_id: "0000-1",
        nombre_usuario: "ada.admin",
        email: "ada@grcoir.com",
        area: "admin",
      },
    });
    renderLogin();

    llenarYEnviar("ada@grcoir.com", "Contrasena-1");

    expect(await screen.findByText("Dashboard simulado")).toBeInTheDocument();
    expect(window.localStorage.getItem("grcoir.token")).toBe("token-de-prueba");
    expect(loginMock).toHaveBeenCalledWith({
      email: "ada@grcoir.com",
      password: "Contrasena-1",
    });
  });

  it("muestra el mensaje GENÉRICO del backend y no guarda token si fallan", async () => {
    loginMock.mockRejectedValue(
      new ApiRequestError("no_autenticado", "Usuario o contraseña incorrectos.", 401),
    );
    renderLogin();

    llenarYEnviar("ada@grcoir.com", "equivocada");

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Usuario o contraseña incorrectos.");
    // No debe filtrarse si el correo existe.
    expect(alerta).not.toHaveTextContent(/no existe|no registrado|contraseña incorrecta para/i);

    await waitFor(() => {
      expect(window.localStorage.getItem("grcoir.token")).toBeNull();
    });
    expect(screen.queryByText("Dashboard simulado")).not.toBeInTheDocument();
  });
});
