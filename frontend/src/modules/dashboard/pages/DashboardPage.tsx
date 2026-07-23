/** Dashboard (Home real del sistema GRC-OIR).
 *
 * Malla de 6 tarjetas (una por fase, desde `phaseRegistry`). Reutiliza `AppHeader` (con su
 * hamburguesa + drawer global) para verse parte del mismo producto que Catálogos. Hoy solo
 * F0 (Catálogos) está activa; el resto se muestran "Próximamente".
 */

import { PhaseCard } from "@/modules/dashboard/components/PhaseCard";
import { currentUser } from "@/shared/lib/currentUser";
import { phaseRegistry } from "@/shared/phases/phaseRegistry";
import { AppHeader } from "@/shared/ui";

export function DashboardPage() {
  return (
    <div className="app-shell">
      <AppHeader faseLabel="INICIO" user={currentUser} />
      <main className="dashboard-main">
        <div className="dashboard-inner">
          <header className="dashboard-hero">
            <h1 className="dashboard-title">Sistema GRC-OIR</h1>
            <p className="dashboard-sub">
              Plataforma del área OIR de Grupo Radio Centro. Elige una fase para comenzar.
            </p>
          </header>
          <div className="phase-grid">
            {phaseRegistry.map((phase, i) => (
              <PhaseCard key={phase.key} phase={phase} index={i} />
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
