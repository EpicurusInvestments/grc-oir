/** Alta de Requisicion (F3) — captura de CxP.
 *
 * Las FKs obligatorias dependen de `tipo_requisicion` (el backend las valida con 400 si
 * falta la que corresponde): `pago_afiliado`→afiliado; `pago_agencia`→agencia;
 * `comision_vendedor`→vendedor+orden; `comision_agencia`→agencia+orden. Validación manual
 * en vez de un resolver Zod condicional: 4 ramas con reglas cruzadas son más claras así.
 *
 * `monto_requisicion` es SIEMPRE captura manual (spec): nunca se sustituye por la
 * comisión calculada, que es informativa. Los % de comisión se SUGIEREN del catálogo al
 * elegir vendedor/agencia (editable) — mismo criterio que `FacturaAgencia` en F2.
 */

import { useMemo, useState } from "react";

import { FieldTag, SavingOverlay, SearchableSelect } from "@/shared/ui";

import { fmtMoneda } from "../../format";
import {
  useAfiliadosInfo,
  useAgenciasInfo,
  useFacturasAfiliadoPagables,
  useFacturasAgenciaPagables,
  useFacturasVendedorPagables,
  useOrdenesInfo,
  useVendedoresInfo,
} from "../../hooks";
import { TIPO_REQUISICION_LABEL, TIPOS_REQUISICION, type RequisicionCreate, type TipoRequisicion } from "../../types";

interface Props {
  submitting?: boolean;
  submitError?: string | null;
  onSubmit: (data: RequisicionCreate) => void;
  onCancel: () => void;
}

export function RequisicionForm({ submitting, submitError, onSubmit, onCancel }: Props) {
  const afiliados = useAfiliadosInfo();
  const agencias = useAgenciasInfo();
  const vendedores = useVendedoresInfo();
  const facturasAfiliado = useFacturasAfiliadoPagables();
  const facturasAgencia = useFacturasAgenciaPagables();
  const facturasVendedor = useFacturasVendedorPagables();
  const ordenes = useOrdenesInfo();

  const [tipo, setTipo] = useState<TipoRequisicion>("pago_afiliado");
  const [numeroRequisicion, setNumeroRequisicion] = useState("");
  const [numeroOcSap, setNumeroOcSap] = useState("");
  const [montoRequisicion, setMontoRequisicion] = useState("");
  const [observaciones, setObservaciones] = useState("");
  const [afiliadoId, setAfiliadoId] = useState("");
  const [facturaAfiliadoId, setFacturaAfiliadoId] = useState("");
  const [agenciaId, setAgenciaId] = useState("");
  const [facturaAgenciaId, setFacturaAgenciaId] = useState("");
  const [facturaVendedorId, setFacturaVendedorId] = useState("");
  const [vendedorId, setVendedorId] = useState("");
  const [ordenId, setOrdenId] = useState("");
  const [pctVendedor, setPctVendedor] = useState("");
  const [pctAgencia, setPctAgencia] = useState("");
  const [error, setError] = useState<string | null>(null);

  const facturasAfiliadoDelSeleccionado = useMemo(
    () => (facturasAfiliado.data ?? []).filter((f) => f.afiliado_id === afiliadoId),
    [facturasAfiliado.data, afiliadoId],
  );
  const facturasAgenciaDelSeleccionado = useMemo(
    () => (facturasAgencia.data ?? []).filter((f) => f.agencia_id === agenciaId),
    [facturasAgencia.data, agenciaId],
  );
  const facturasVendedorDelSeleccionado = useMemo(
    () => (facturasVendedor.data ?? []).filter((f) => f.vendedor_id === vendedorId),
    [facturasVendedor.data, vendedorId],
  );
  const ordenOpciones = useMemo(
    () => (ordenes.data ?? []).map((o) => ({ value: o.orden_id, label: `${o.folio_orden} · ${fmtMoneda(o.total)}` })),
    [ordenes.data],
  );

  const confirmar = () => {
    if (!numeroRequisicion.trim()) {
      setError("El número de requisición es obligatorio.");
      return;
    }
    if (!montoRequisicion || Number.isNaN(Number(montoRequisicion)) || Number(montoRequisicion) < 0) {
      setError("Captura el monto de la requisición.");
      return;
    }
    if (tipo === "pago_afiliado" && !afiliadoId) {
      setError("Selecciona el afiliado.");
      return;
    }
    if (tipo === "pago_agencia" && !agenciaId) {
      setError("Selecciona la agencia.");
      return;
    }
    if (tipo === "comision_vendedor" && (!vendedorId || !ordenId)) {
      setError("Selecciona el vendedor y la orden.");
      return;
    }
    if (tipo === "comision_agencia" && (!agenciaId || !ordenId)) {
      setError("Selecciona la agencia y la orden.");
      return;
    }
    setError(null);
    onSubmit({
      numero_requisicion: numeroRequisicion.trim(),
      numero_oc_sap: numeroOcSap.trim() || null,
      tipo_requisicion: tipo,
      monto_requisicion: montoRequisicion,
      observaciones_cuentas_por_pagar: observaciones.trim() || null,
      afiliado_id: tipo === "pago_afiliado" ? afiliadoId : null,
      factura_afiliado_id: tipo === "pago_afiliado" ? facturaAfiliadoId || null : null,
      agencia_id: tipo === "pago_agencia" || tipo === "comision_agencia" ? agenciaId : null,
      factura_agencia_id: tipo === "pago_agencia" ? facturaAgenciaId || null : null,
      vendedor_comision_id: tipo === "comision_vendedor" ? vendedorId : null,
      factura_vendedor_id: tipo === "comision_vendedor" ? facturaVendedorId || null : null,
      orden_id: tipo === "comision_vendedor" || tipo === "comision_agencia" ? ordenId : null,
      porcentaje_comision_vendedor: tipo === "comision_vendedor" && pctVendedor ? pctVendedor : null,
      porcentaje_comision_agencia_req: tipo === "comision_agencia" && pctAgencia ? pctAgencia : null,
    });
  };

  return (
    <>
      <SavingOverlay visible={!!submitting} />
      <div className="dh">
        <div className="dh-name">Nueva requisición</div>
      </div>

      <div className="db">
        <div className="form-card">
          <div className="fl fl-required">Tipo de requisición</div>
          <select
            className="fsel"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoRequisicion)}
          >
            {TIPOS_REQUISICION.map((t) => (
              <option key={t} value={t}>
                {TIPO_REQUISICION_LABEL[t]}
              </option>
            ))}
          </select>

          <div className="r2">
            <div>
              <div className="fl fl-required">Número de requisición</div>
              <input
                className="fi"
                style={{ fontFamily: "var(--mono)" }}
                value={numeroRequisicion}
                onChange={(e) => setNumeroRequisicion(e.target.value)}
              />
            </div>
            <div>
              <div className="fl">Número de OC (SAP)</div>
              <input
                className="fi"
                style={{ fontFamily: "var(--mono)" }}
                placeholder="OC-SAP-XXXX"
                value={numeroOcSap}
                onChange={(e) => setNumeroOcSap(e.target.value)}
              />
            </div>
          </div>

          {tipo === "pago_afiliado" && (
            <>
              <div className="fl fl-required">
                Afiliado <FieldTag origin="catalogo" />
              </div>
              <select
                className="fsel"
                value={afiliadoId}
                onChange={(e) => {
                  setAfiliadoId(e.target.value);
                  setFacturaAfiliadoId("");
                }}
              >
                <option value="">— Selecciona —</option>
                {(afiliados.data ?? []).map((a) => (
                  <option key={a.afiliado_id} value={a.afiliado_id}>
                    {a.nombre_afiliado}
                  </option>
                ))}
              </select>
              <div className="fl">Factura de la emisora (opcional)</div>
              <select
                className="fsel"
                value={facturaAfiliadoId}
                onChange={(e) => {
                  const id = e.target.value;
                  setFacturaAfiliadoId(id);
                  const f = facturasAfiliadoDelSeleccionado.find((x) => x.factura_afiliado_id === id);
                  if (f) setMontoRequisicion(f.total_factura_afiliado);
                }}
                disabled={!afiliadoId}
              >
                <option value="">— Ninguna —</option>
                {facturasAfiliadoDelSeleccionado.map((f) => (
                  <option key={f.factura_afiliado_id} value={f.factura_afiliado_id}>
                    {f.factura_emisora} · {fmtMoneda(f.total_factura_afiliado)}
                  </option>
                ))}
              </select>
            </>
          )}

          {tipo === "pago_agencia" && (
            <>
              <div className="fl fl-required">
                Agencia <FieldTag origin="catalogo" />
              </div>
              <select
                className="fsel"
                value={agenciaId}
                onChange={(e) => {
                  setAgenciaId(e.target.value);
                  setFacturaAgenciaId("");
                }}
              >
                <option value="">— Selecciona —</option>
                {(agencias.data ?? []).map((a) => (
                  <option key={a.agencia_id} value={a.agencia_id}>
                    {a.nombre_agencia}
                  </option>
                ))}
              </select>
              <div className="fl">Factura de la agencia (opcional)</div>
              <select
                className="fsel"
                value={facturaAgenciaId}
                onChange={(e) => {
                  const id = e.target.value;
                  setFacturaAgenciaId(id);
                  const f = facturasAgenciaDelSeleccionado.find((x) => x.factura_agencia_id === id);
                  if (f) setMontoRequisicion(f.total_factura_agencia);
                }}
                disabled={!agenciaId}
              >
                <option value="">— Ninguna —</option>
                {facturasAgenciaDelSeleccionado.map((f) => (
                  <option key={f.factura_agencia_id} value={f.factura_agencia_id}>
                    {f.folio_factura_agencia ?? "(sin folio)"} · {fmtMoneda(f.total_factura_agencia)}
                  </option>
                ))}
              </select>
            </>
          )}

          {tipo === "comision_vendedor" && (
            <>
              <div className="fl fl-required">
                Vendedor <FieldTag origin="catalogo" />
              </div>
              <select
                className="fsel"
                value={vendedorId}
                onChange={(e) => {
                  const id = e.target.value;
                  setVendedorId(id);
                  setFacturaVendedorId("");
                  const v = (vendedores.data ?? []).find((x) => x.vendedor_id === id);
                  if (v && !pctVendedor) setPctVendedor(v.porcentaje_comision_default ?? "");
                }}
              >
                <option value="">— Selecciona —</option>
                {(vendedores.data ?? []).map((v) => (
                  <option key={v.vendedor_id} value={v.vendedor_id}>
                    {v.nombre_vendedor}
                  </option>
                ))}
              </select>
              {/* Petición del usuario: al pagar la requisición, esta factura (si se
                  elige) pasa a "pagada" también. */}
              <div className="fl">Factura del vendedor (opcional)</div>
              <select
                className="fsel"
                value={facturaVendedorId}
                onChange={(e) => {
                  const id = e.target.value;
                  setFacturaVendedorId(id);
                  const f = facturasVendedorDelSeleccionado.find((x) => x.factura_vendedor_id === id);
                  if (f) setMontoRequisicion(f.total_factura_vendedor);
                }}
                disabled={!vendedorId}
              >
                <option value="">— Ninguna —</option>
                {facturasVendedorDelSeleccionado.map((f) => (
                  <option key={f.factura_vendedor_id} value={f.factura_vendedor_id}>
                    {f.folio_factura_vendedor ?? "(sin folio)"} · {fmtMoneda(f.total_factura_vendedor)}
                  </option>
                ))}
              </select>
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
                    value={pctVendedor}
                    onChange={(e) => setPctVendedor(e.target.value)}
                  />
                </div>
              </div>
            </>
          )}

          {tipo === "comision_agencia" && (
            <>
              <div className="fl fl-required">
                Agencia <FieldTag origin="catalogo" />
              </div>
              <select
                className="fsel"
                value={agenciaId}
                onChange={(e) => {
                  const id = e.target.value;
                  setAgenciaId(id);
                  const a = (agencias.data ?? []).find((x) => x.agencia_id === id);
                  if (a && !pctAgencia) setPctAgencia(a.porcentaje_comision_agencia_default ?? "");
                }}
              >
                <option value="">— Selecciona —</option>
                {(agencias.data ?? []).map((a) => (
                  <option key={a.agencia_id} value={a.agencia_id}>
                    {a.nombre_agencia}
                  </option>
                ))}
              </select>
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
            </>
          )}

          <div className="fl fl-required">
            Monto de la requisición
            {tipo !== "comision_agencia" && <FieldTag origin="catalogo" text="Sugerido, editable" />}
          </div>
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
