/** Tabla de los 3 % de comisión SNAPSHOT de una OrdenCliente (vendedor principal,
 * secundario, agencia): valor congelado vs. default del catálogo, con el override
 * resaltado. Solo lectura (la edición llega en la Tanda 2, dentro del formulario).
 */

import { FieldTag } from "@/shared/ui";

import { FROZEN_STATES } from "../constants";
import { fmtMonto, fmtPct } from "../format";
import { findAgencia, findVendedor } from "../state/catalogosCache";
import { esComisionOverride } from "../state/selectors";
import type { OrdenCliente } from "../types";

interface FilaComision {
  etiqueta: string;
  snap: number | null;
  defaultCatalogo: number;
  monto: number | null;
}

export function CommissionSnapshotBlock({ oc, total }: { oc: OrdenCliente; total: number }) {
  const filas: FilaComision[] = [];

  const vp = findVendedor(oc.vendedor_principal_id);
  if (vp) {
    filas.push({
      etiqueta: "Vendedor principal",
      snap: oc.porcentaje_comision_vendedor_principal_snap,
      defaultCatalogo: vp.porcentaje_comision_default,
      monto: oc.porcentaje_comision_vendedor_principal_snap != null ? (total * oc.porcentaje_comision_vendedor_principal_snap) / 100 : null,
    });
  }
  const vs = findVendedor(oc.vendedor_secundario_id);
  if (vs) {
    filas.push({
      etiqueta: "Vendedor secundario",
      snap: oc.porcentaje_comision_vendedor_secundario_snap,
      defaultCatalogo: vs.porcentaje_comision_default,
      monto: oc.porcentaje_comision_vendedor_secundario_snap != null ? (total * oc.porcentaje_comision_vendedor_secundario_snap) / 100 : null,
    });
  }
  const ag = findAgencia(oc.agencia_id);
  if (ag) {
    filas.push({
      etiqueta: "Agencia",
      snap: oc.porcentaje_comision_agencia_snap,
      defaultCatalogo: ag.porcentaje_comision_agencia_default,
      monto: oc.porcentaje_comision_agencia_snap != null ? (total * oc.porcentaje_comision_agencia_snap) / 100 : null,
    });
  }

  if (filas.length === 0) return null;

  const congelado = FROZEN_STATES.includes(oc.estatus_orden);

  return (
    <>
      <div className="sec">
        % Comisiones (snapshot) <FieldTag origin="audit" />
        <span style={{ fontSize: 10, color: congelado ? "var(--amber-text)" : "var(--text3)", fontWeight: congelado ? 500 : 400 }}>
          {congelado ? "🔒 Congelado" : "Editable hasta el cierre"}
        </span>
      </div>
      <div
        style={{
          background: congelado ? "var(--amber-bg)" : "var(--surface2)",
          border: `1px solid ${congelado ? "var(--amber-border, #FAC775)" : "var(--border)"}`,
          borderRadius: "var(--r)",
          padding: "9px 11px",
          marginBottom: 11,
        }}
      >
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ color: "var(--text3)", fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              <th style={{ textAlign: "left", padding: "2px 0", fontWeight: 600 }}>Beneficiario</th>
              <th style={{ textAlign: "right", padding: "2px 0", fontWeight: 600 }}>% Snap</th>
              <th style={{ textAlign: "right", padding: "2px 0", fontWeight: 600 }}>Default cat.</th>
              <th style={{ textAlign: "right", padding: "2px 0", fontWeight: 600 }}>Monto</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => {
              const overriden = esComisionOverride(f.snap, f.defaultCatalogo);
              return (
                <tr key={f.etiqueta}>
                  <td style={{ padding: "3px 0", color: "var(--text)" }}>{f.etiqueta}</td>
                  <td
                    style={{
                      padding: "3px 0",
                      textAlign: "right",
                      fontFamily: "var(--mono)",
                      fontWeight: 600,
                      color: overriden ? "var(--amber-text)" : "var(--text)",
                    }}
                  >
                    {fmtPct(f.snap)}
                    {overriden ? " *" : ""}
                  </td>
                  <td style={{ padding: "3px 0", textAlign: "right", fontFamily: "var(--mono)", color: "var(--text3)" }}>
                    {fmtPct(f.defaultCatalogo)}
                  </td>
                  <td style={{ padding: "3px 0", textAlign: "right", fontFamily: "var(--mono)", color: "var(--purple-text)" }}>
                    {f.monto != null ? fmtMonto(f.monto) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filas.some((f) => esComisionOverride(f.snap, f.defaultCatalogo)) && (
          <div style={{ fontSize: 10, color: "var(--text3)", marginTop: 6 }}>* sobrescribe el % por defecto del catálogo.</div>
        )}
      </div>
    </>
  );
}
