/** Tarjeta de fase del Dashboard.
 *
 * Activa (fase construida): clicable, navega a su ruta, con hover (elevación + zoom de
 * imagen) y acento de color por fase. Deshabilitada ("Próximamente"): atenuada, imagen en
 * escala de grises, sin interacción. El estado sale de `PhaseEntry.enabled`.
 */

import { useNavigate } from "react-router-dom";

import type { PhaseEntry } from "@/shared/phases/phaseRegistry";

interface PhaseCardProps {
  phase: PhaseEntry;
  /** Índice para el retardo escalonado del fade-in de entrada. */
  index: number;
}

export function PhaseCard({ phase, index }: PhaseCardProps) {
  const navigate = useNavigate();
  const active = phase.enabled && phase.route !== null;

  const content = (
    <>
      <div className="pc-media">
        <picture>
          <source srcSet={phase.imageWebp} type="image/webp" />
          <img src={phase.imagePng} alt="" className="pc-img" loading="lazy" />
        </picture>
      </div>
      <div className="pc-body">
        <div className="pc-head">
          <span className="pc-code">{phase.code}</span>
          <span className="pc-name">{phase.name}</span>
          {!active && <span className="badge b-gray pc-badge">Próximamente</span>}
        </div>
        <p className="pc-desc">{phase.description}</p>
      </div>
    </>
  );

  const style = { animationDelay: `${index * 70}ms` } as const;

  if (!active) {
    return (
      <div
        className={`phase-card pc-accent-${phase.accent} disabled`}
        style={style}
        aria-disabled="true"
      >
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={`phase-card pc-accent-${phase.accent}`}
      style={style}
      onClick={() => navigate(phase.route!)}
    >
      {content}
    </button>
  );
}
