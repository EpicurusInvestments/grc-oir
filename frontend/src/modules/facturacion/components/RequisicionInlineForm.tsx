/** ADR-282 (petición del usuario, con captura): bloque embebido para generar la
 * Requisicion de pago de una Factura (afiliado/agencia/vendedor) ya `autorizada`,
 * directo desde su propia pantalla de detalle — ya no hace falta ir a "Requisiciones
 * de pago" para darla de alta ahí. Lo usan las 3 páginas (`FacturasAfiliadoPage`,
 * `FacturasAgenciaPage`, `FacturasVendedorPage`), cada una pasando SU propio tipo y FKs.
 *
 * El backend (`RequisicionService._validar_factura_disponible`) es quien realmente
 * manda: rechaza con 409 si esa factura ya tiene una requisición, o 400 si no está
 * `autorizada` — este componente solo evita el viaje redondo cuando el llamador ya sabe
 * que no aplica (no se muestra si `estatus !== "autorizada"`, decisión de cada página).
 *
 * Tras generarla con éxito, el bloque se reemplaza por un aviso con el número generado
 * — no hay forma de "refrescar" si la factura ya tenía una (eso se descubre al 409 si
 * se reintenta), es una limitación aceptada: no se agregó un campo nuevo a
 * `FacturaAfiliadoRead`/`FacturaAgenciaRead`/`FacturaVendedorRead` para esto porque
 * Facturación no debe conocer a Cobranza (mismo criterio de capas que el backend).
 *
 * ADR-283 (petición del usuario, con captura): el backend genera esta requisición
 * directo en "autorizada" (la factura de origen ya pasó por Dirección, re-autorizar
 * sería redundante) — el aviso de éxito lo dice explícitamente para que quede claro que
 * ya no falta ese paso en "Requisiciones de pago", solo "Marcar pagada".
 */

import { useState } from "react";

import { ApiRequestError } from "@/shared/lib/apiClient";

import { useCrearRequisicionDesdeFactura } from "../hooks";
import type { TipoRequisicionDesdeFactura } from "../types";

interface Props {
  tipo: TipoRequisicionDesdeFactura;
  montoSugerido: string;
  afiliadoId?: string | null;
  facturaAfiliadoId?: string | null;
  agenciaId?: string | null;
  facturaAgenciaId?: string | null;
  vendedorComisionId?: string | null;
  facturaVendedorId?: string | null;
}

const mensajeDeError = (e: unknown): string =>
  e instanceof ApiRequestError ? e.message : "Ocurrió un error inesperado.";

export function RequisicionInlineForm({
  tipo,
  montoSugerido,
  afiliadoId,
  facturaAfiliadoId,
  agenciaId,
  facturaAgenciaId,
  vendedorComisionId,
  facturaVendedorId,
}: Props) {
  const [numeroOcSap, setNumeroOcSap] = useState("");
  const [monto, setMonto] = useState(montoSugerido);
  const [observaciones, setObservaciones] = useState("");
  const [generada, setGenerada] = useState<string | null>(null);
  const crear = useCrearRequisicionDesdeFactura();

  if (generada) {
    return (
      <div className="state-msg success" style={{ textAlign: "left", margin: 0 }}>
        Requisición <span className="mono">{generada}</span> generada y autorizada — solo
        falta marcarla como pagada en Requisiciones de pago.
      </div>
    );
  }

  const confirmar = () => {
    crear.mutate(
      {
        tipo_requisicion: tipo,
        numero_oc_sap: numeroOcSap.trim() || null,
        monto_requisicion: monto,
        observaciones_cuentas_por_pagar: observaciones.trim() || null,
        afiliado_id: afiliadoId ?? null,
        factura_afiliado_id: facturaAfiliadoId ?? null,
        agencia_id: agenciaId ?? null,
        factura_agencia_id: facturaAgenciaId ?? null,
        vendedor_comision_id: vendedorComisionId ?? null,
        factura_vendedor_id: facturaVendedorId ?? null,
      },
      { onSuccess: (r) => setGenerada(r.numero_requisicion) },
    );
  };

  return (
    <>
      <div className="sec">Generar requisición de pago</div>
      <div className="r2">
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
        <div>
          <div className="fl fl-required">Monto de la requisición</div>
          <input className="fi" inputMode="decimal" value={monto} onChange={(e) => setMonto(e.target.value)} />
        </div>
      </div>
      <div className="fl">Observaciones de CxP</div>
      <textarea className="ftxt" value={observaciones} onChange={(e) => setObservaciones(e.target.value)} />
      {crear.isError && <div className="fe">{mensajeDeError(crear.error)}</div>}
      <div className="df" style={{ justifyContent: "flex-start", padding: 0 }}>
        <button type="button" className="btn btn-sm btn-phase" onClick={confirmar} disabled={crear.isPending}>
          {crear.isPending ? "Generando…" : "Generar requisición"}
        </button>
      </div>
    </>
  );
}
