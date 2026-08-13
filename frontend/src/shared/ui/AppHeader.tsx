/** Header del patrón: hamburguesa (menú global) · logo · tag de fase · menú de usuario.
 *
 * El menú de usuario (F5-00) muestra quién está dentro y ofrece "Cerrar sesión". Se apoya
 * en `cerrarSesionActual()` del shim `currentUser` en vez de `useSession()` a propósito:
 * así este componente COMPARTIDO no depende de un módulo de negocio (`modules/auth`), y
 * las 14 pantallas de F0 que lo montan no necesitaron cambiar.
 */

import { useEffect, useRef, useState } from "react";

import { cerrarSesionActual } from "@/shared/lib/currentUser";
import { esModoDevHeaders } from "@/shared/lib/session";

import { AppNavDrawer } from "./AppNavDrawer";

interface AppHeaderProps {
  faseLabel: string;
  user: { username: string; area: string };
}

function iniciales(username: string): string {
  const limpio = username.replace(/[._-]+/g, " ").trim();
  const partes = limpio.split(/\s+/).slice(0, 2);
  return partes.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

export function AppHeader({ faseLabel, user }: AppHeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Cerrar el menú de usuario al hacer clic fuera o con Escape.
  useEffect(() => {
    if (!userMenuOpen) return;
    const alClic = (e: MouseEvent) => {
      if (!userMenuRef.current?.contains(e.target as Node)) setUserMenuOpen(false);
    };
    const alTeclado = (e: KeyboardEvent) => {
      if (e.key === "Escape") setUserMenuOpen(false);
    };
    document.addEventListener("mousedown", alClic);
    document.addEventListener("keydown", alTeclado);
    return () => {
      document.removeEventListener("mousedown", alClic);
      document.removeEventListener("keydown", alTeclado);
    };
  }, [userMenuOpen]);

  return (
    <>
      <header className="app-header">
        <button
          type="button"
          className="hamburger"
          onClick={() => setMenuOpen(true)}
          aria-label="Abrir menú de navegación"
          aria-haspopup="dialog"
          aria-expanded={menuOpen}
        >
          <i className="pi pi-bars" />
        </button>
        <div className="logo">
          GRC<span>·</span>OIR
        </div>
        <div className="fase-tag">{faseLabel}</div>
        <div className="header-spacer" />

        <div className="user-menu" ref={userMenuRef}>
          <button
            type="button"
            className="user-chip"
            onClick={() => setUserMenuOpen((abierto) => !abierto)}
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            aria-label={`Menú de ${user.username}`}
          >
            <div className="user-avatar">{iniciales(user.username)}</div>
            <span>
              {user.area} · {user.username}
            </span>
            <i className="pi pi-angle-down user-chip-caret" aria-hidden="true" />
          </button>

          {userMenuOpen && (
            <div className="user-dropdown" role="menu">
              <div className="user-dropdown-head">
                <div className="user-dropdown-name">{user.username}</div>
                <div className="user-dropdown-area">Área: {user.area}</div>
              </div>
              {esModoDevHeaders ? (
                // Sin login que cerrar: la identidad viene de los headers de desarrollo.
                <div className="user-dropdown-note">
                  Modo desarrollo (<span className="mono">dev_headers</span>)
                </div>
              ) : (
                <button
                  type="button"
                  className="user-dropdown-item"
                  role="menuitem"
                  onClick={() => {
                    setUserMenuOpen(false);
                    cerrarSesionActual();
                  }}
                >
                  <i className="pi pi-sign-out" aria-hidden="true" />
                  Cerrar sesión
                </button>
              )}
            </div>
          )}
        </div>
      </header>
      <AppNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
}
