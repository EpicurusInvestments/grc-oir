/** Header del patrón: logo · tag de fase · usuario activo. */

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
  return (
    <header className="app-header">
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
  );
}
