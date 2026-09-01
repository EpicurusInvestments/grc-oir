/** Domicilio estructurado con autocompletado por código postal (SEPOMEX) — usado por
 * Anunciante y EmpresaFacturadora (ADR-059), mismos 10 campos que los grupos
 * ExEmisorDomFiscal/ExReceptorDomFiscal del layout del PAC.
 *
 * Calle/No. exterior/No. interior/Referencia SIEMPRE se capturan a mano: SEPOMEX no baja
 * a ese nivel de detalle. Colonia/Municipio/Estado/Localidad/País se autocompletan al
 * escribir un CP de 5 dígitos — si hay una sola colonia para ese CP se rellena sola; si
 * hay varias, se elige de una lista. TODOS los campos quedan editables después: si la
 * dirección autocompletada sale mal, se corrige a mano sin pelear con el componente.
 */

import { useEffect, useState } from "react";

import { useBuscarCodigoPostal } from "@/modules/catalogos/codigoPostal/hooks";
import type { AsentamientoPostal } from "@/modules/catalogos/codigoPostal/types";

export interface DomicilioPostalValues {
  calle: string;
  numero_exterior: string;
  numero_interior: string;
  colonia: string;
  localidad: string;
  referencia_domicilio: string;
  municipio: string;
  estado: string;
  pais: string;
  codigo_postal: string;
}

interface DomicilioPostalInputProps {
  values: DomicilioPostalValues;
  onChange: (patch: Partial<DomicilioPostalValues>) => void;
  disabled?: boolean;
}

export function DomicilioPostalInput({ values, onChange, disabled }: DomicilioPostalInputProps) {
  const [listaCerrada, setListaCerrada] = useState(false);
  const cpQuery = useBuscarCodigoPostal(values.codigo_postal);
  const opciones = cpQuery.data ?? [];
  const cpCompleto = values.codigo_postal.trim().length === 5;
  const sinResultados = cpCompleto && cpQuery.isSuccess && opciones.length === 0;
  const mostrarLista = cpCompleto && opciones.length > 1 && !listaCerrada;

  // Un CP con una sola colonia no tiene nada que elegir: se autocompleta directo.
  useEffect(() => {
    if (opciones.length === 1) {
      elegirAsentamiento(opciones[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo cuando cambian las opciones
  }, [opciones.length === 1 ? opciones[0]?.codigo_postal : null]);

  const elegirAsentamiento = (a: AsentamientoPostal) => {
    onChange({
      colonia: a.asentamiento,
      municipio: a.municipio,
      estado: a.estado,
      localidad: a.ciudad ?? "",
      pais: a.pais,
    });
    setListaCerrada(true);
  };

  const campo =
    (nombre: keyof DomicilioPostalValues) => (e: React.ChangeEvent<HTMLInputElement>) => {
      const valor = e.target.value;
      if (nombre === "codigo_postal") {
        setListaCerrada(false);
        if (valor.trim() === "") {
          // Se borró el CP: lo que se autocompletó a partir de él ya no aplica.
          // Calle/No. exterior/No. interior/Referencia son siempre manuales, no se tocan.
          onChange({
            codigo_postal: valor,
            colonia: "",
            municipio: "",
            estado: "",
            localidad: "",
            pais: "",
          });
          return;
        }
      }
      onChange({ [nombre]: valor } as Partial<DomicilioPostalValues>);
    };

  return (
    <div>
      <div className="r2">
        <div style={{ position: "relative" }}>
          <div className="fl">Código postal</div>
          <input
            className="fi"
            inputMode="numeric"
            maxLength={5}
            disabled={disabled}
            value={values.codigo_postal}
            onChange={campo("codigo_postal")}
            placeholder="00000"
          />
          {cpQuery.isFetching && <div className="derivado-hint">Buscando…</div>}
          {sinResultados && (
            <div className="derivado-hint">
              No encontramos ese CP en el catálogo — captura la dirección manualmente.
            </div>
          )}
          {mostrarLista && (
            <div className="ssel-list">
              {opciones.map((a) => (
                <div
                  key={a.asentamiento}
                  className="ssel-item"
                  onMouseDown={() => elegirAsentamiento(a)}
                >
                  {a.asentamiento}{" "}
                  <span style={{ color: "var(--text3)" }}>
                    — {a.municipio}, {a.estado}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div>
          <div className="fl">Colonia</div>
          <input
            className="fi"
            disabled={disabled}
            value={values.colonia}
            onChange={campo("colonia")}
          />
        </div>
      </div>

      <div className="r2">
        <div>
          <div className="fl">Calle</div>
          <input
            className="fi"
            disabled={disabled}
            value={values.calle}
            onChange={campo("calle")}
          />
        </div>
        <div className="r2">
          <div>
            <div className="fl">No. exterior</div>
            <input
              className="fi"
              disabled={disabled}
              value={values.numero_exterior}
              onChange={campo("numero_exterior")}
            />
          </div>
          <div>
            <div className="fl">No. interior</div>
            <input
              className="fi"
              disabled={disabled}
              value={values.numero_interior}
              onChange={campo("numero_interior")}
            />
          </div>
        </div>
      </div>

      <div className="r2">
        <div>
          <div className="fl">Municipio / Alcaldía</div>
          <input
            className="fi"
            disabled={disabled}
            value={values.municipio}
            onChange={campo("municipio")}
          />
        </div>
        <div>
          <div className="fl">Estado</div>
          <input
            className="fi"
            disabled={disabled}
            value={values.estado}
            onChange={campo("estado")}
          />
        </div>
      </div>

      <div className="r2">
        <div>
          <div className="fl">Localidad / Ciudad</div>
          <input
            className="fi"
            disabled={disabled}
            value={values.localidad}
            onChange={campo("localidad")}
          />
        </div>
        <div>
          <div className="fl">País</div>
          <input className="fi" disabled={disabled} value={values.pais} onChange={campo("pais")} />
        </div>
      </div>

      <div className="fl">Referencia</div>
      <input
        className="fi"
        disabled={disabled}
        value={values.referencia_domicilio}
        onChange={campo("referencia_domicilio")}
        placeholder="Entre calles, puntos de referencia…"
      />
    </div>
  );
}
