/** Constructor/editor de `periodo_transmision`: filas de fecha + hora inicio + hora término
 * + spots del día, con día de la semana visible, agregar/quitar fila, y validación de que
 * la fecha cae dentro del rango de la campaña. Se reutiliza en el alta de OrdenEstacion
 * (Tanda 3) y, en modo de solo lectura, en el detalle.
 */

import { diaDeSemana } from "../format";
import type { PeriodoTransmisionRow } from "../types";

export function problemasDeFila(row: PeriodoTransmisionRow, rango: { inicio: string; fin: string }): string[] {
  const problemas: string[] = [];
  if (!row.fecha) {
    problemas.push("Falta la fecha.");
  } else if (rango.inicio && rango.fin && (row.fecha < rango.inicio || row.fecha > rango.fin)) {
    problemas.push("La fecha cae fuera del rango de la campaña.");
  }
  if (!row.hora_inicio || !row.hora_termino) {
    problemas.push("Falta hora de inicio o de término.");
  } else if (row.hora_inicio >= row.hora_termino) {
    problemas.push("La hora de inicio debe ser antes que la de término.");
  }
  if (!row.spots_diarios || row.spots_diarios <= 0) {
    problemas.push("Los spots del día deben ser mayores a 0.");
  }
  return problemas;
}

interface PeriodoTransmisionGridProps {
  rows: PeriodoTransmisionRow[];
  onChange: (rows: PeriodoTransmisionRow[]) => void;
  rangoCampania: { inicio: string; fin: string };
  disabled?: boolean;
}

export function PeriodoTransmisionGrid({ rows, onChange, rangoCampania, disabled }: PeriodoTransmisionGridProps) {
  const totalSpots = rows.reduce((s, r) => s + (r.spots_diarios || 0), 0);

  const actualizarFila = (idx: number, patch: Partial<PeriodoTransmisionRow>) => {
    onChange(rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };
  const quitarFila = (idx: number) => onChange(rows.filter((_, i) => i !== idx));
  const agregarFila = () => {
    const ultima = rows[rows.length - 1];
    let siguienteFecha = rangoCampania.inicio;
    if (ultima?.fecha) {
      const d = new Date(ultima.fecha);
      d.setDate(d.getDate() + 1);
      siguienteFecha = d.toISOString().slice(0, 10);
      if (rangoCampania.fin && siguienteFecha > rangoCampania.fin) siguienteFecha = rangoCampania.fin;
    }
    onChange([
      ...rows,
      {
        fecha: siguienteFecha,
        hora_inicio: ultima?.hora_inicio ?? "07:00",
        hora_termino: ultima?.hora_termino ?? "09:00",
        spots_diarios: ultima?.spots_diarios ?? 0,
      },
    ]);
  };

  return (
    <div>
      <table className="cat-table" style={{ fontSize: 12 }}>
        <thead>
          <tr>
            <th>Día</th>
            <th>Fecha</th>
            <th>Hora inicio</th>
            <th>Hora término</th>
            <th className="td-center">Spots</th>
            <th style={{ width: 36 }} />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const problemas = problemasDeFila(row, rangoCampania);
            return (
              <tr key={idx}>
                <td className="td-2" style={{ fontSize: 11 }}>
                  {diaDeSemana(row.fecha)}
                </td>
                <td>
                  <input
                    type="date"
                    className="fi"
                    style={{ marginBottom: 0, borderColor: problemas.length ? "var(--red-text)" : undefined }}
                    value={row.fecha}
                    disabled={disabled}
                    onChange={(e) => actualizarFila(idx, { fecha: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="time"
                    className="fi"
                    style={{ marginBottom: 0 }}
                    value={row.hora_inicio}
                    disabled={disabled}
                    onChange={(e) => actualizarFila(idx, { hora_inicio: e.target.value })}
                  />
                </td>
                <td>
                  <input
                    type="time"
                    className="fi"
                    style={{ marginBottom: 0 }}
                    value={row.hora_termino}
                    disabled={disabled}
                    onChange={(e) => actualizarFila(idx, { hora_termino: e.target.value })}
                  />
                </td>
                <td className="td-center">
                  <input
                    type="number"
                    className="fi"
                    style={{ marginBottom: 0, textAlign: "center", fontFamily: "var(--mono)" }}
                    value={row.spots_diarios}
                    disabled={disabled}
                    onChange={(e) => actualizarFila(idx, { spots_diarios: Number.parseInt(e.target.value, 10) || 0 })}
                  />
                </td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    {!disabled && (
                      <button type="button" className="btn btn-xs btn-danger" onClick={() => quitarFila(idx)} aria-label="Quitar día">
                        ✕
                      </button>
                    )}
                    {problemas.length > 0 && (
                      <span style={{ fontSize: 11, color: "var(--red-text)" }} title={problemas.join(" ")}>
                        ⚠
                      </span>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
        {rows.length > 0 && (
          <tfoot>
            <tr>
              <td colSpan={4} style={{ textAlign: "right", fontWeight: 600, fontSize: 11, padding: "8px 16px" }}>
                Total
              </td>
              <td className="td-center" style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                {totalSpots}
              </td>
              <td />
            </tr>
          </tfoot>
        )}
      </table>
      {!disabled && (
        <button type="button" className="btn btn-xs" style={{ marginTop: 8 }} onClick={agregarFila}>
          + Agregar día
        </button>
      )}
      {rows.length === 0 && (
        <div className="fv muted" style={{ fontSize: 12, marginTop: 8 }}>
          Captura al menos un día de transmisión.
        </div>
      )}
    </div>
  );
}
