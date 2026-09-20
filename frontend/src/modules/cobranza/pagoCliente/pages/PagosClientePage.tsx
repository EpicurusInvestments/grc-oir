/** Pagos recibidos (F3) — historial de `PagoCliente` a través de todas las cobranzas.
 *
 * Solo lectura: el alta/baja de un pago vive en el detalle de "Cobranza de facturas"
 * (`CobranzaFacturasPage`), asociada siempre a UNA `CobranzaFactura` — esta pantalla es
 * el espejo cronológico que pide el mockup, no un segundo punto de captura.
 *
 * El backend no tiene un `GET` de "todos los pagos" (ver `historialPagosCliente` en
 * `api.ts`): esta vista se arma agregando por cobranza, con el límite de 100 ya conocido
 * en el resto del módulo.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { DetailEmpty, ListDetailLayout } from "@/shared/ui";

import { fmtFecha, fmtMoneda, oGuion } from "../../format";
import { useHistorialPagosCliente } from "../../hooks";
import type { PagoClienteConCobranza } from "../../types";

export function PagosClientePage() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<PagoClienteConCobranza | null>(null);

  const historial = useHistorialPagosCliente();
  const items = useMemo(() => {
    const todos = historial.data ?? [];
    const qq = q.trim().toLowerCase();
    return qq ? todos.filter((p) => (p.referencia_pago ?? "").toLowerCase().includes(qq)) : todos;
  }, [historial.data, q]);

  const hoyMes = new Date().toISOString().slice(0, 7);
  const delMes = (historial.data ?? []).filter((p) => p.fecha_pago_cliente.slice(0, 7) === hoyMes);
  const totalMes = delMes.reduce((s, p) => s + Number(p.monto_aplicado), 0);
  const totalHistorico = (historial.data ?? []).reduce((s, p) => s + Number(p.monto_aplicado), 0);

  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Factura</th>
            <th className="td-right">Monto</th>
            <th>Método</th>
            <th>Referencia</th>
          </tr>
        </thead>
        <tbody>
          {items.map((p) => (
            <tr
              key={p.pago_cliente_id}
              className={selected?.pago_cliente_id === p.pago_cliente_id ? "sel" : ""}
              onClick={() => setSelected(p)}
            >
              <td className="mono" style={{ fontSize: 11 }}>{fmtFecha(p.fecha_pago_cliente)}</td>
              <td className="td-main mono">{p.cobranza.numero_factura ?? "—"}</td>
              <td className="td-right mono" style={{ color: "var(--green-text)", fontWeight: 600 }}>
                +{fmtMoneda(p.monto_aplicado)}
              </td>
              <td className="td-2">{p.metodo_pago_clave}</td>
              <td className="mono" style={{ fontSize: 11 }}>{oGuion(p.referencia_pago)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {historial.isLoading && <div className="state-msg">Cargando pagos…</div>}
      {historial.isError && <div className="state-msg error">No se pudo cargar el historial.</div>}
      {!historial.isLoading && !historial.isError && items.length === 0 && (
        <div className="state-msg">Sin pagos registrados.</div>
      )}
    </>
  );

  const detail = selected ? (
    <>
      <div className="dh">
        <div className="dh-name mono" style={{ color: "var(--green-text)" }}>
          +{fmtMoneda(selected.monto_aplicado)}
        </div>
        <div className="dh-sub">
          <span className="badge b-green">Aplicado</span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text3)" }}>
            {fmtFecha(selected.fecha_pago_cliente)}
          </span>
        </div>
      </div>
      <div className="db">
        <div className="sec">Factura aplicada</div>
        <div
          style={{ border: "1px solid var(--border)", borderRadius: "var(--r)", padding: "11px 13px", cursor: "pointer" }}
          onClick={() => navigate(`/cobranza?factura_id=${selected.cobranza.factura_id}`)}
        >
          <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 600, marginBottom: 3 }}>
            <span className="mono">{selected.cobranza.numero_factura ?? "—"}</span>
            <span className="mono">
              {fmtMoneda(
                String(
                  Number(selected.cobranza.importe_cobrado) + Number(selected.cobranza.importe_pendiente_cobro),
                ),
              )}
            </span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text3)" }}>Ver en Cobranza de facturas →</div>
        </div>

        <div className="sec">Datos del pago</div>
        <div className="fl">Fecha</div>
        <div className="fv mono">{fmtFecha(selected.fecha_pago_cliente)}</div>
        <div className="fl">Monto aplicado</div>
        <div className="fv mono big" style={{ color: "var(--green-text)" }}>
          {fmtMoneda(selected.monto_aplicado)}
        </div>
        <div className="fl">Método</div>
        <div className="fv">{selected.metodo_pago_clave}</div>
        <div className="fl">Referencia</div>
        <div className="fv mono">{oGuion(selected.referencia_pago)}</div>
        {selected.archivo_nombre && (
          <>
            <div className="fl">Comprobante</div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 11px",
                border: "1px solid var(--border)",
                borderRadius: "var(--r)",
                fontSize: 12,
              }}
            >
              {selected.archivo_nombre}
            </div>
          </>
        )}
      </div>
    </>
  ) : (
    <DetailEmpty message="Selecciona un pago para ver el detalle." />
  );

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Pagos recibidos</div>
          <div className="cat-sub">
            Historial de pagos del cliente. Cada pago se aplica a una cobranza específica;
            se captura desde el detalle de "Cobranza de facturas".
          </div>
        </div>
      </div>

      <div className="kpi-strip">
        <div className="kpi-box success">
          <div className="kpi-lbl" style={{ color: "var(--green-text)" }}>Cobrado este mes</div>
          <div className="kpi-val" style={{ color: "var(--green-text)" }}>{fmtMoneda(String(totalMes))}</div>
          <div className="kpi-sub">{delMes.length} pagos</div>
        </div>
        <div className="kpi-box">
          <div className="kpi-lbl">Total histórico</div>
          <div className="kpi-val">{fmtMoneda(String(totalHistorico))}</div>
          <div className="kpi-sub">{(historial.data ?? []).length} pagos registrados</div>
        </div>
      </div>

      <div className="toolbar">
        <input
          className="search"
          placeholder="Buscar referencia…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="tb-spacer" />
        <span className="tb-count">{items.length} pagos</span>
      </div>

      <ListDetailLayout list={listNode} detail={detail} />
    </>
  );
}
