/** Badge de estado activo/inactivo (b-green / b-gray) del patrón aprobado. */

interface StatusBadgeProps {
  activo: boolean;
  labelActivo?: string;
  labelInactivo?: string;
}

export function StatusBadge({
  activo,
  labelActivo = "Activo",
  labelInactivo = "Inactivo",
}: StatusBadgeProps) {
  return (
    <span className={`badge ${activo ? "b-green" : "b-gray"}`}>
      {activo ? labelActivo : labelInactivo}
    </span>
  );
}
