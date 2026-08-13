/** Pantalla de inicio de sesión (F5-00) — la primera que ve el cliente en las demos.
 *
 * Tarjeta centrada con el logo de Grupo Radio Centro, email + contraseña y un solo botón.
 * Usa los tokens de `theme.css` (paleta, tipografía IBM Plex, radios) y las clases de
 * formulario del patrón (`fl`, `fi`, `fe`), para que se lea como parte del mismo producto
 * que el resto del sistema.
 *
 * El mensaje de error es **el que devuelve el backend** ("Usuario o contraseña
 * incorrectos."), deliberadamente genérico: la pantalla no debe delatar si un correo está
 * dado de alta.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { useSession } from "@/modules/auth/sessionContext";
import logoPng from "@/assets/logo-grc.png";
import logoWebp from "@/assets/logo-grc.webp";
import { ApiRequestError } from "@/shared/lib/apiClient";

const schema = z.object({
  email: z.string().trim().min(1, "El correo es obligatorio.").email("Correo no válido."),
  password: z.string().min(1, "La contraseña es obligatoria."),
});

type LoginFormValues = z.infer<typeof schema>;

const ERROR_GENERICO = "No se pudo iniciar sesión. Inténtalo de nuevo.";

export function LoginPage() {
  const { estado, iniciarSesion } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [errorEnvio, setErrorEnvio] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  // Ya hay sesión (o el modo dev no pide login): no tiene sentido mostrar la pantalla.
  if (estado === "autenticado") {
    const destino = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
    return <Navigate to={destino ?? "/"} replace />;
  }

  const enviar = handleSubmit(async (datos) => {
    setErrorEnvio(null);
    setEnviando(true);
    try {
      await iniciarSesion(datos.email.trim(), datos.password);
      // `from` solo llega cuando la sesión se perdió trabajando (lo pone `RequireSession`);
      // en un login desde cero no existe y se entra al Dashboard, que es el Home del sistema.
      const destino = (location.state as { from?: { pathname: string } } | null)?.from?.pathname;
      navigate(destino ?? "/", { replace: true });
    } catch (error) {
      // El backend ya manda un mensaje genérico y legible; se muestra tal cual.
      setErrorEnvio(error instanceof ApiRequestError ? error.message : ERROR_GENERICO);
    } finally {
      setEnviando(false);
    }
  });

  return (
    <div className="login-page">
      <main className="login-card">
        <picture>
          <source srcSet={logoWebp} type="image/webp" />
          <img src={logoPng} alt="Grupo Radio Centro" className="login-logo" />
        </picture>

        <h1 className="login-title">Sistema GRC-OIR</h1>
        <p className="login-sub">Inicia sesión para continuar</p>

        <form onSubmit={enviar} noValidate>
          <label className="fl fl-required" htmlFor="login-email">
            Correo electrónico
          </label>
          <input
            id="login-email"
            className="fi"
            type="email"
            autoComplete="username"
            autoFocus
            disabled={enviando}
            aria-invalid={Boolean(errors.email)}
            {...register("email")}
          />
          <div className="fe">{errors.email?.message}</div>

          <label className="fl fl-required" htmlFor="login-password">
            Contraseña
          </label>
          <input
            id="login-password"
            className="fi"
            type="password"
            autoComplete="current-password"
            disabled={enviando}
            aria-invalid={Boolean(errors.password)}
            {...register("password")}
          />
          <div className="fe">{errors.password?.message}</div>

          {errorEnvio && (
            <div className="login-error" role="alert">
              <i className="pi pi-exclamation-circle" aria-hidden="true" />
              <span>{errorEnvio}</span>
            </div>
          )}

          <button type="submit" className="btn btn-phase login-submit" disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <p className="login-footer">Grupo Radio Centro · OIR</p>
      </main>
    </div>
  );
}
