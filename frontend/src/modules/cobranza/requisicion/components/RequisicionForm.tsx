/** Alta de Requisicion de "Comisión agencia" (F3) — captura de CxP.
 *
 * ADR-282 (petición del usuario, con captura): el alta de los otros 3 tipos
 * (`pago_afiliado`, `pago_agencia`, `comision_vendedor`) se movió a un bloque embebido
 * en la propia pantalla de su factura (Facturas de afiliado/agencia/vendedor, F2) — ya
 * no se capturan aquí. Este formulario queda solo para `comision_agencia`, el único
 * tipo que no tiene una factura de origen (es un pago sobre una `OrdenCliente`
 * directamente), así que sigue viviendo en "Requisiciones de pago".
 *
 * `numero_requisicion` ya NO se captura: el backend lo genera siempre
 * (`RQ-AAAA-MM-consecutivo`).
 */

import { useState } from "react";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { fmtMoneda } from "../../format";
import { useAgenciasInfo, useOrdenesInfo } from "../../hooks";
import type { RequisicionCreate } from "../../types";

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: RequisicionCreate) => void;
  onCancel: () => void;
}

export function RequisicionForm({ submitting, submitError, onSubmit, onCancel }: Props) {
  const agencias = useAgenciasInfo();
  const ordenes = useOrdenesInfo();

  const [numeroOcSap, setNumeroOcSap] = useState("");
  const [montoRequisicion, setMontoRequisicion] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [agenciaId, setAgenciaId] = useState("");
  const [ordenId, setOrdenId] = useState("");
  const [pctAgencia, setPctAgencia] = useState("");
  const [error, setError] = useState<string | null>(null);

  const ordenOpciones = (ordenes.data ?? []).map((o) => ({
    value: o.orden_id,
    label: `${o.folio_orden} · ${fmtMoneda(o.total)}`,
  }));

  const confirmar = () => {
    if (!montoRequisicion || Number.isNaN(Number(montoRequisicion)) || Number(montoRequisicion) < 0) {
      setError("Captura el monto de la requisición.");
      return;
    }
    if (!agenciaId || !ordenId) {
      setError("Selecciona la agencia y la orden.");
      return;
    }
    setError(null);
    onSubmit({
      numero_oc_sap: numeroOcSap.trim() || null,
      tipo_requisicion: "comision_agencia",
      monto_requisicion: montoRequisicion,
      observaciones_cuentas_por_pagar: observaciones.trim() || null,
      afiliado_id: null,
      factura_afiliado_id: null,
      agencia_id: agenciaId,
      factura_agencia_id: null,
      vendedor_comision_id: null,
      factura_vendedor_id: null,
      orden_id: ordenId,
      porcentaje_comision_vendedor: null,
      porcentaje_comision_agencia_req: pctAgencia || null,
    });
  };

  return (
    <>
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">Nueva comisión de agencia</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl">Número de OC (SAP)</div>
          <input
            className="fi"
            style={{ fontFamily: "var(--mono)" }}
            placeholder="OC-SAP-XXXX"
            value={numeroOcSap}
            onChange={(e) => setNumeroOcSap(e.target.value)}
          />

          <div className="fl fl-required">
            Agencia <FieldTag origin="catalogo" />
          </div>
          <SearchableSelect
            value={agenciaId}
            onChange={(id) => {
              setAgenciaId(id);
              const a = (agencias.data ?? []).find((x) => x.agencia_id === id);
              setPctAgencia(a?.porcentaje_comision_agencia_default ?? "");
            }}
            options={(agencias.data ?? []).map((a) => ({ value: a.agencia_id, label: a.nombre_agencia }))}
          />
          <div className="fl fl-required">Orden de cliente</div>
          <SearchableSelect
            value={ordenId}
            onChange={setOrdenId}
            options={ordenOpciones}
            placeholder="Buscar por folio de orden…"
          />
          <div className="r2">
            <div>
              <div className="fl">
                % Comisión <FieldTag origin="catalogo" text="Sugerido, editable" />
              </div>
              <input
                className="fi"
                inputMode="decimal"
                value={pctAgencia}
                onChange={(e) => setPctAgencia(e.target.value)}
              />
            </div>
          </div>

          <div className="fl fl-required">Monto de la requisición</div>
          <input
            className="fi"
            inputMode="decimal"
            value={montoRequisicion}
            onChange={(e) => setMontoRequisicion(e.target.value)}
          />

          <div className="fl">Observaciones de CxP</div>
          <textarea
            className="ftxt"
            value={observaciones}
            onChange={(e) => setObservaciones(e.target.value)}
          />

          {error && <div className="fe">{error}</div>}
        </div>

        {submitError && <div className="state-msg error">{submitError}</div>}
      </div>

      <div className="df">
        <button type="button" className="btn btn-sm" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="button" className="btn btn-sm btn-phase" onClick={confirmar} disabled={submitting}>
          Guardar
        </button>
      </div>
    </>
  );
}
