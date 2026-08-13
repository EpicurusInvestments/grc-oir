/** Pantalla de gestión de usuarios: lista, guardarraíl anti-auto-bloqueo y contraseñas. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionContext, type SessionContextValue } from "@/modules/auth/sessionContext";
import { UsuariosPage } from "@/modules/seguridad/usuarios/pages/UsuariosPage";
import type { Usuario } from "@/modules/seguridad/usuarios/types";

vi.mock("@/modules/seguridad/usuarios/api", () => ({
  usuarioApi: {
    resource: "usuarios",
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    setEstado: vi.fn(),
  },
  establecerPassword: vi.fn(),
}));

const { usuarioApi, establecerPassword } = await import("@/modules/seguridad/usuarios/api");

const ADMIN: Usuario = {
  usuario_id: "id-admin",
  nombre_usuario: "ada.admin",
  email: "ada@grcoir.com",
  area: "admin",
  roles_adicionales: null,
  activo: true,
  created_at: "2026-08-01T10:00:00",
  tiene_password: true,
};

const SIN_PASSWORD: Usuario = {
  usuario_id: "id-dani",
  nombre_usuario: "dani.cxp",
  email: "dani@grcoir.com",
  area: "cxp",
  roles_adicionales: null,
  activo: true,
  created_at: "2026-08-02T10:00:00",
  tiene_password: false,
};

function sesionDe(usuarioId: string): SessionContextValue {
  return {
    estado: "autenticado",
    usuario: {
      usuario_id: usuarioId,
      nombre_usuario: "ada.admin",
      email: "ada@grcoir.com",
      area: "admin",
    },
    esModoDesarrollo: false,
    expiroLaSesion: false,
    iniciarSesion: vi.fn(),
    cerrarSesion: vi.fn(),
  };
}

/** Llena el diálogo de contraseña y lo envía. */
function escribirPassword(dialogo: HTMLElement, password: string, confirmacion: string) {
  fireEvent.change(within(dialogo).getByLabelText("Nueva contraseña"), {
    target: { value: password },
  });
  fireEvent.change(within(dialogo).getByLabelText("Confirmar contraseña"), {
    target: { value: confirmacion },
  });
  fireEvent.click(within(dialogo).getByRole("button", { name: /guardar contraseña/i }));
}

function renderPage(sesion: SessionContextValue = sesionDe("id-admin")) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SessionContext.Provider value={sesion}>
        <MemoryRouter>
          <UsuariosPage />
        </MemoryRouter>
      </SessionContext.Provider>
    </QueryClientProvider>,
  );
}

describe("UsuariosPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(usuarioApi.list).mockResolvedValue({
      items: [ADMIN, SIN_PASSWORD],
      total: 2,
      page: 1,
      size: 20,
      pages: 1,
    });
  });

  it("lista los usuarios con su área legible y marca a quien no tiene contraseña", async () => {
    renderPage();

    expect(await screen.findByText("ada.admin")).toBeInTheDocument();
    expect(screen.getByText("dani.cxp")).toBeInTheDocument();
    // El área se muestra con etiqueta legible, no con el valor crudo del ENUM.
    expect(screen.getByText("Cuentas por pagar")).toBeInTheDocument();
    expect(screen.getAllByText("Sin contraseña").length).toBeGreaterThan(0);
  });

  it("nunca muestra el hash de la contraseña", async () => {
    const { container } = renderPage();
    await screen.findByText("ada.admin");

    expect(container.textContent).not.toMatch(/\$2[aby]\$/);
    expect(container.textContent).not.toMatch(/password_hash/);
  });

  it("no deja al admin desactivarse a sí mismo, y explica por qué", async () => {
    renderPage(sesionDe(ADMIN.usuario_id));

    fireEvent.click(await screen.findByText("ada.admin"));

    const boton = await screen.findByRole("button", { name: "Desactivar" });
    expect(boton).toBeDisabled();
    expect(boton).toHaveAttribute("title", expect.stringContaining("perderías el acceso"));
  });

  it("sí deja desactivar a OTRO usuario", async () => {
    renderPage(sesionDe(ADMIN.usuario_id));

    fireEvent.click(await screen.findByText("dani.cxp"));

    expect(await screen.findByRole("button", { name: "Desactivar" })).toBeEnabled();
  });

  it("bloquea el cambio de área propia en el formulario de edición", async () => {
    renderPage(sesionDe(ADMIN.usuario_id));

    fireEvent.click(await screen.findByText("ada.admin"));
    fireEvent.click(await screen.findByRole("button", { name: "Editar" }));

    expect(await screen.findByLabelText("Área")).toBeDisabled();
    expect(screen.getByText(/No puedes cambiar tu propia área/i)).toBeInTheDocument();
  });

  it("permite cambiar el área de otro usuario", async () => {
    renderPage(sesionDe(ADMIN.usuario_id));

    fireEvent.click(await screen.findByText("dani.cxp"));
    fireEvent.click(await screen.findByRole("button", { name: "Editar" }));

    expect(await screen.findByLabelText("Área")).toBeEnabled();
  });

  it("rechaza en el cliente una contraseña de menos de 10 caracteres", async () => {
    renderPage();

    fireEvent.click(await screen.findByText("dani.cxp"));
    fireEvent.click(await screen.findByRole("button", { name: /establecer contraseña/i }));

    const dialogo = await screen.findByRole("dialog");
    escribirPassword(dialogo, "corta1", "corta1");

    expect(await within(dialogo).findByText(/al menos 10 caracteres/i)).toBeInTheDocument();
    expect(establecerPassword).not.toHaveBeenCalled();
  });

  it("rechaza una contraseña que excede 72 BYTES aunque tenga pocos caracteres", async () => {
    renderPage();

    fireEvent.click(await screen.findByText("dani.cxp"));
    fireEvent.click(await screen.findByRole("button", { name: /establecer contraseña/i }));

    const dialogo = await screen.findByRole("dialog");
    const conAcentos = "ñ".repeat(40); // 40 caracteres, pero 80 bytes en UTF-8
    escribirPassword(dialogo, conAcentos, conAcentos);

    expect(await within(dialogo).findByText(/72 bytes/i)).toBeInTheDocument();
    expect(establecerPassword).not.toHaveBeenCalled();
  });

  it("exige que la confirmación coincida antes de llamar al backend", async () => {
    renderPage();

    fireEvent.click(await screen.findByText("dani.cxp"));
    fireEvent.click(await screen.findByRole("button", { name: /establecer contraseña/i }));

    const dialogo = await screen.findByRole("dialog");
    escribirPassword(dialogo, "Contrasena-Buena-1", "Contrasena-Otra-2");

    expect(await within(dialogo).findByText(/no coinciden/i)).toBeInTheDocument();
    expect(establecerPassword).not.toHaveBeenCalled();
  });

  it("envía la contraseña válida al endpoint dedicado", async () => {
    vi.mocked(establecerPassword).mockResolvedValue({ ...SIN_PASSWORD, tiene_password: true });
    renderPage();

    fireEvent.click(await screen.findByText("dani.cxp"));
    fireEvent.click(await screen.findByRole("button", { name: /establecer contraseña/i }));

    const dialogo = await screen.findByRole("dialog");
    escribirPassword(dialogo, "Contrasena-Dani-1", "Contrasena-Dani-1");

    await vi.waitFor(() => {
      expect(establecerPassword).toHaveBeenCalledWith("id-dani", "Contrasena-Dani-1");
    });
  });
});
