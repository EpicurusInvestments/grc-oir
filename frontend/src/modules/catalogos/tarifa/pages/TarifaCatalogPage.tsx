/** Pantalla del catálogo Tarifas: lista + panel de detalle (patrón F0).
 *
 * ADR-097 (petición del usuario): ya no filtra por vigencia (eliminada por completo);
 * filtros Activas/Inactivas/Todas. Alta/edición en el panel derecho; la `tarifa_neta` es
 * calculada (solo lectura). Los conflictos de negocio del backend (p.ej. tarifa activa
 * duplicada para la misma estación/señal/duración/producto, 409) se muestran al usuario
 * sin romper la pantalla.
 */

import { useState } from "react";

import { useEstaciones } from "@/modules/catalogos/estacion/hooks";
import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import type { ListParams } from "@/shared/types";
import {
  CatalogToolbar,
  DetailEmpty,
  FieldTag,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { TarifaForm, type TarifaFormOutput } from "../components/TarifaForm";
import { fmtMoneda } from "../format";
import { useHistorialTarifa, useTarifas } from "../hooks";
import type { DuracionSpot, ProductoTarifa, TarifaPlaza, TipoSenal } from "../types";
import { DURACION_SPOT_OPCIONES, PRODUCTO_OPCIONES, TIPO_SENAL_OPCIONES } from "../types";

type Filtro = "todas" | "activas" | "inactivas";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "activas", label: "Activas" },
  { key: "inactivas", label: "Inactivas" },
];

const activoDeFiltro = (f: Filtro): boolean | undefined =>
  f === "activas" ? true : f === "inactivas" ? false : undefined;

const senalLabel = (v: TipoSenal) => TIPO_SENAL_OPCIONES.find((o) => o.value === v)?.label ?? v;
const duracionLabel = (v: DuracionSpot) =>
  DURACION_SPOT_OPCIONES.find((o) => o.value === v)?.label ?? v;
const productoLabel = (v: ProductoTarifa) =>
  PRODUCTO_OPCIONES.find((o) => o.value === v)?.label ?? v;

const oGuion = (v: string | null): string => (v && v.trim() ? v : "—");
const fmtFechaHora = (iso: string): string =>
  new Date(iso).toLocaleString("es-MX", { dateStyle: "short", timeStyle: "short" });
const CAMPO_LABEL: Record<string, string> = {
  tarifa_bruta: "Tarifa bruta",
  descuento_pct: "Descuento",
};
const labelCampo = (c: string) => CAMPO_LABEL[c] ?? c;

export function TarifaCatalogPage() {
  const canWrite = currentUser.area === "admin";
  const { useList, useCreate, useUpdate, useSetEstado } = useTarifas();

  const [filtro, setFiltro] = useState<Filtro>("todas");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(20);
  const [selected, setSelected] = useState<TarifaPlaza | null>(null);
  const [modo, setModo] = useState<Modo>("view");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const params: ListParams = { page, size, q: q || undefined, activo: activoDeFiltro(filtro) };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  // Estaciones activas para el select del formulario.
  const estacionesQuery = useEstaciones().useList({ activo: true, size: 100 });
  const estaciones = estacionesQuery.data?.items ?? [];

  // Historial de auditoría de tarifa_bruta/descuento_pct (parámetros sensibles, ADR-099).
  const historial = useHistorialTarifa(selected?.tarifa_plaza_id ?? null);
  const histItems = historial.data ?? [];

  const reset = () => {
    setSelected(null);
    setModo("view");
    setErrorMsg(null);
  };

  const seleccionar = (t: TarifaPlaza) => {
    setSelected(t);
    setModo("view");
    setErrorMsg(null);
  };

  const onCrear = async (data: TarifaFormOutput) => {
    setErrorMsg(null);
    try {
      const nueva = await crear.mutateAsync(data);
      setSelected(nueva);
      setModo("view");
    } catch (e) {
      if (e instanceof ApiRequestError) setErrorMsg(e.message);
      else throw e;
    }
  };

  const onActualizar = async (data: TarifaFormOutput) => {
    if (!selected) return;
    setErrorMsg(null);
    try {
      const upd = await actualizar.mutateAsync({ id: selected.tarifa_plaza_id, data });
      setSelected(upd);
      setModo("view");
    } catch (e) {
      if (e instanceof ApiRequestError) setErrorMsg(e.message);
      else throw e;
    }
  };

  const cambiarEstado = async (t: TarifaPlaza, activo: boolean) => {
    setErrorMsg(null);
    try {
      const upd = await setEstado.mutateAsync({ id: t.tarifa_plaza_id, activo });
      setSelected(upd);
    } catch (e) {
      // Reactivar puede chocar con otra tarifa activa de la misma combinación (409 conflicto).
      if (e instanceof ApiRequestError) setErrorMsg(e.message);
      else throw e;
    }
  };

  // ── panel de detalle ──────────────────────────────────────────────────────
  let detail;
  if (modo === "new") {
    detail = (
      <TarifaForm
        title="Nueva tarifa"
        estaciones={estaciones}
        submitting={crear.isPending}
        submitError={errorMsg}
        onSubmit={onCrear}
        onCancel={reset}
      />
    );
  } else if (modo === "edit" && selected) {
    detail = (
      <TarifaForm
        title="Editar tarifa"
        estaciones={estaciones}
        isEdit
        defaultValues={{
          estacion_id: selected.estacion_id,
          tipo_senal: selected.tipo_senal,
          duracion_spot: selected.duracion_spot,
          producto: selected.producto,
          tarifa_bruta: selected.tarifa_bruta,
          descuento_pct: selected.descuento_pct,
          notas: selected.notas ?? "",
        }}
        submitting={actualizar.isPending}
        submitError={errorMsg}
        onSubmit={onActualizar}
        onCancel={() => {
          setModo("view");
          setErrorMsg(null);
        }}
      />
    );
  } else if (selected) {
    detail = (
      <>
        <div className="dh">
          <div className="dh-row">
            <div>
              <div className="dh-name">
                {selected.estacion_nombre ?? "—"} · {senalLabel(selected.tipo_senal)}{" "}
                {duracionLabel(selected.duracion_spot)}
              </div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <span className="badge b-blue">{productoLabel(selected.producto)}</span>
              </div>
            </div>
            {canWrite && (
              <button type="button" className="btn btn-sm" onClick={() => setModo("edit")}>
                Editar
              </button>
            )}
          </div>
        </div>
        <div className="db">
          <div className="sec">Tarifa</div>
          <div className="r2">
            <div>
              <div className="fl">Tarifa bruta</div>
              <div className="fv mono" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtMoneda(selected.tarifa_bruta)}
              </div>
            </div>
            <div>
              <div className="fl">Descuento</div>
              <div className="fv mono">{selected.descuento_pct}%</div>
            </div>
          </div>
          <div className="fl">
            Tarifa neta <FieldTag origin="calculado" />
          </div>
          <div
            className="fv mono"
            style={{ fontSize: 20, fontWeight: 600, color: "var(--purple-text)" }}
          >
            {fmtMoneda(selected.tarifa_neta)}
          </div>

          {selected.notas && (
            <>
              <div className="sec">Notas</div>
              <div className="fv muted">{selected.notas}</div>
            </>
          )}

          <div className="sec">Historial de cambios</div>
          {historial.isLoading && <div className="state-msg">Cargando historial…</div>}
          {historial.isError && (
            <div className="state-msg error">No se pudo cargar el historial.</div>
          )}
          {!historial.isLoading && !historial.isError && histItems.length === 0 && (
            <div className="fv muted">Sin cambios registrados.</div>
          )}
          {histItems.map((h) => (
            <div className="rel-item" key={h.log_cambio_parametro_id}>
              <div>
                <div className="rel-name">
                  {labelCampo(h.campo)}: <span className="mono">{oGuion(h.valor_anterior)}</span>{" "}
                  → <span className="mono">{oGuion(h.valor_nuevo)}</span>
                </div>
                <div className="rel-sub">
                  {fmtFechaHora(h.fecha_cambio)} · {h.usuario}
                  {h.motivo_cambio ? ` · ${h.motivo_cambio}` : ""}
                </div>
              </div>
            </div>
          ))}
        </div>
        {errorMsg && (
          <div className="state-msg error" style={{ textAlign: "left" }}>
            {errorMsg}
          </div>
        )}
        {canWrite && (
          <div className="df">
            <button
              type="button"
              className={`btn btn-sm ${selected.activo ? "btn-danger" : ""}`}
              disabled={setEstado.isPending}
              onClick={() => cambiarEstado(selected, !selected.activo)}
            >
              {selected.activo ? "Desactivar" : "Activar"}
            </button>
          </div>
        )}
      </>
    );
  } else {
    detail = <DetailEmpty message="Selecciona una tarifa para ver el detalle." />;
  }

  // ── lista ───────────────────────────────────────────────────────────────────
  const items = list.data?.items ?? [];
  const listNode = (
    <>
      <table className="cat-table">
        <thead>
          <tr>
            <th>Emisora</th>
            <th style={{ width: 110 }}>Producto</th>
            <th style={{ width: 70 }}>Señal</th>
            <th style={{ width: 90 }}>Duración</th>
            <th className="td-right" style={{ width: 120 }}>
              Tarifa bruta
            </th>
            <th className="td-center" style={{ width: 70 }}>
              Desc
            </th>
            <th className="td-right" style={{ width: 120 }}>
              Tarifa neta
            </th>
            <th className="td-center" style={{ width: 90 }}>
              Estatus
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr
              key={t.tarifa_plaza_id}
              className={selected?.tarifa_plaza_id === t.tarifa_plaza_id ? "sel" : ""}
              onClick={() => seleccionar(t)}
            >
              <td className="td-main">{t.estacion_nombre ?? "—"}</td>
              <td className="td-2">{productoLabel(t.producto)}</td>
              <td className="td-2">{senalLabel(t.tipo_senal)}</td>
              <td className="td-2">{t.duracion_spot}</td>
              <td className="td-right td-mono">{fmtMoneda(t.tarifa_bruta)}</td>
              <td className="td-center td-mono">{t.descuento_pct}%</td>
              <td
                className="td-right td-mono"
                style={{ color: "var(--purple-text)", fontWeight: 500 }}
              >
                {fmtMoneda(t.tarifa_neta)}
              </td>
              <td className="td-center">
                <StatusBadge activo={t.activo} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {list.isLoading && <div className="state-msg">Cargando tarifas…</div>}
      {list.isError && <div className="state-msg error">No se pudieron cargar las tarifas.</div>}
      {!list.isLoading && !list.isError && items.length === 0 && (
        <div className="state-msg">No hay tarifas para el filtro seleccionado.</div>
      )}
      {list.data && list.data.total > 0 && (
        <Paginator
          page={page}
          size={size}
          total={list.data.total}
          onChange={(np, ns) => {
            setPage(np);
            setSize(ns);
          }}
        />
      )}
    </>
  );

  return (
    <>
      <div className="cat-header">
        <div>
          <div className="cat-title">Tarifas</div>
          <div className="cat-sub">
            Tarifas de referencia por emisora, producto, tipo de señal y duración. Se
            sugieren al capturar órdenes; el precio final puede sobreescribirse.
          </div>
        </div>
        {canWrite && (
          <button
            type="button"
            className="btn btn-phase"
            onClick={() => {
              setSelected(null);
              setModo("new");
              setErrorMsg(null);
            }}
          >
            + Nueva tarifa
          </button>
        )}
      </div>
      <CatalogToolbar
        search={q}
        onSearch={(v) => {
          setQ(v);
          setPage(1);
        }}
        searchPlaceholder="Buscar por emisora o notas…"
        filters={FILTROS}
        activeFilter={filtro}
        onFilter={(k) => {
          setFiltro(k as Filtro);
          setPage(1);
          reset();
        }}
        count={list.data ? `${items.length} de ${list.data.total}` : undefined}
      />
      <ListDetailLayout list={listNode} detail={detail} />
    </>
  );
}
