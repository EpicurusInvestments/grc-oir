/** Menú lateral global deslizante (drawer) — navegación entre fases del sistema.
 *
 * Componente COMPARTIDO: se monta desde `AppHeader`, por lo que cualquier pantalla que
 * use el header obtiene el menú sin re-trabajo. Contiene el acceso al Home (Dashboard) y
 * las 6 fases (generadas desde `phaseRegistry`). Las fases no construidas se muestran como
 * "Próximamente" (deshabilitadas), consistente con el Dashboard.
 *
 * Se cierra con: clic en el overlay, tecla Escape, o el botón de cerrar.
 */

import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { phaseRegistry } from "@/shared/phases/phaseRegistry";

interface AppNavDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function AppNavDrawer({ open, onClose }: AppNavDrawerProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const closeRef = useRef<HTMLButtonElement>(null);

  // Escape para cerrar + foco inicial en el botón de cerrar (accesibilidad).
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const go = (route: string) => {
    onClose();
    navigate(route);
  };

  const isHome = location.pathname === "/";

  return (
    <div className={`nav-drawer-root ${open ? "open" : ""}`} aria-hidden={!open}>
      <div className="nav-overlay" onClick={onClose} />
      <aside
        className="nav-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Navegación del sistema"
      >
        <div className="nav-drawer-head">
          <div className="logo">
            GRC<span>·</span>OIR
          </div>
          <button
            type="button"
            ref={closeRef}
            className="nav-close"
            onClick={onClose}
            aria-label="Cerrar menú"
          >
            <i className="pi pi-times" />
          </button>
        </div>

        <nav className="nav-drawer-body">
          <button
            type="button"
            className={`nav-home ${isHome ? "active" : ""}`}
            onClick={() => go("/")}
          >
            <i className="pi pi-home" />
            <span>Inicio</span>
          </button>

          <div className="nav-section-title">Fases</div>

          {phaseRegistry.map((phase) => {
            const active = phase.enabled && phase.route !== null;
            const current = phase.route !== null && location.pathname.startsWith(phase.route);
            return (
              <button
                type="button"
                key={phase.key}
                className={`nav-phase pc-accent-${phase.accent} ${active ? "" : "disabled"} ${
                  current ? "current" : ""
                }`}
                onClick={active && phase.route ? () => go(phase.route!) : undefined}
                disabled={!active}
                aria-disabled={!active}
              >
                <picture>
                  <source srcSet={phase.imageWebp} type="image/webp" />
                  <img src={phase.imagePng} alt="" className="nav-phase-img" loading="lazy" />
                </picture>
                <span className="nav-phase-text">
                  <span className="nav-phase-name">
                    <span className="nav-phase-code">{phase.code}</span>
                    {phase.name}
                  </span>
                </span>
                {!active && <span className="badge b-gray nav-phase-badge">Próximamente</span>}
              </button>
            );
          })}
        </nav>
      </aside>
    </div>
  );
}
