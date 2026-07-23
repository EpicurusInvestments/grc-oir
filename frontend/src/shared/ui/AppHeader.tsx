/** Header del patrón: hamburguesa (menú global) · logo · tag de fase · usuario activo. */

import { useState } from "react";

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
        <div className="user-chip">
          <div className="user-avatar">{iniciales(user.username)}</div>
          <span>
            {user.area} · {user.username}
          </span>
        </div>
      </header>
      <AppNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)} />
    </>
  );
}
