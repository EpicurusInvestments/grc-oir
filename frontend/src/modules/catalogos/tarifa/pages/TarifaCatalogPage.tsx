/** Pantalla del catálogo Tarifas por plaza: lista + panel de detalle (patrón F0).
 *
 * Filtros: Todas / Vigentes / Expiradas / Activas / Inactivas (selección única). Vigentes
 * y Expiradas son derivados en el servidor (vigencia_hasta vs hoy); Activas/Inactivas usan
 * `activo`. Alta/edición en el panel derecho; la `tarifa_neta` es calculada (solo lectura).
 * Los conflictos de negocio del backend (p.ej. solapamiento de vigencias, 409) se muestran
 * al usuario sin romper la pantalla.
 */

import { useState } from "react";

import { usePlazas } from "@/modules/catalogos/plaza/hooks";
import { ApiRequestError } from "@/shared/lib/apiClient";
import { currentUser } from "@/shared/lib/currentUser";
import {
  CatalogToolbar,
  DetailEmpty,
  FieldTag,
  ListDetailLayout,
  Paginator,
  StatusBadge,
} from "@/shared/ui";

import { TarifaForm } from "../components/TarifaForm";
import { esVigente, fmtFecha, fmtMoneda } from "../format";
import { useTarifas } from "../hooks";
import type { DuracionSpot, TarifaListParams, TarifaPlaza, TarifaPlazaCreate, TipoSenal } from "../types";
import { DURACION_SPOT_OPCIONES, TIPO_SENAL_OPCIONES } from "../types";

type Filtro = "todas" | "vigentes" | "expiradas" | "activas" | "inactivas";
type Modo = "view" | "new" | "edit";

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todas", label: "Todas" },
  { key: "vigentes", label: "Vigentes" },
  { key: "expiradas", label: "Expiradas" },
  { key: "activas", label: "Activas" },
  { key: "inactivas", label: "Inactivas" },
];

const paramsDeFiltro = (f: Filtro): Pick<TarifaListParams, "activo" | "vigencia"> => {
  switch (f) {
    case "activas":
      return { activo: true };
    case "inactivas":
      return { activo: false };
    case "vigentes":
      return { vigencia: "vigente" };
    case "expiradas":
      return { vigencia: "expirada" };
    default:
      return {};
  }
};

const senalLabel = (v: TipoSenal) => TIPO_SENAL_OPCIONES.find((o) => o.value === v)?.label ?? v;
const duracionLabel = (v: DuracionSpot) =>
  DURACION_SPOT_OPCIONES.find((o) => o.value === v)?.label ?? v;

function VigenciaBadge({ hasta }: { hasta: string }) {
  const vigente = esVigente(hasta);
  return (
    <span className={`badge ${vigente ? "b-green" : "b-amber"}`}>
      {vigente ? "Vigente" : "Expirada"}
    </span>
  );
}

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

  const params: TarifaListParams = {
    page,
    size,
    q: q || undefined,
    ...paramsDeFiltro(filtro),
  };
  const list = useList(params);
  const crear = useCreate();
  const actualizar = useUpdate();
  const setEstado = useSetEstado();

  // Plazas activas para el select del formulario.
  const plazasQuery = usePlazas().useList({ activo: true, size: 100 });
  const plazas = plazasQuery.data?.items ?? [];

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

  const onCrear = async (data: TarifaPlazaCreate) => {
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

  const onActualizar = async (data: TarifaPlazaCreate) => {
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
      // Reactivar puede chocar con otra tarifa que ya cubra ese rango (409 conflicto).
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
        plazas={plazas}
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
        plazas={plazas}
        defaultValues={{
          plaza_id: selected.plaza_id,
          tipo_senal: selected.tipo_senal,
          duracion_spot: selected.duracion_spot,
          tarifa_bruta: selected.tarifa_bruta,
          descuento_pct: selected.descuento_pct,
          vigencia_desde: selected.vigencia_desde,
          vigencia_hasta: selected.vigencia_hasta,
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
                {selected.plaza_nombre ?? "—"} · {senalLabel(selected.tipo_senal)}{" "}
                {duracionLabel(selected.duracion_spot)}
              </div>
              <div className="dh-sub">
                <StatusBadge activo={selected.activo} />
                <VigenciaBadge hasta={selected.vigencia_hasta} />
                {selected.plaza_estado && <span>{selected.plaza_estado}</span>}
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

          <div className="sec">Vigencia</div>
          <div className="r2">
            <div>
              <div className="fl">Desde</div>
              <div className="fv mono">{fmtFecha(selected.vigencia_desde)}</div>
            </div>
            <div>
              <div className="fl">Hasta</div>
              <div className="fv mono">{fmtFecha(selected.vigencia_hasta)}</div>
            </div>
          </div>

          {selected.notas && (
            <>
              <div className="sec">Notas</div>
              <div className="fv muted">{selected.notas}</div>
            </>
          )}
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
            <th>Plaza</th>
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
            <th style={{ width: 160 }}>Vigencia</th>
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
              <td className="td-main">{t.plaza_nombre ?? "—"}</td>
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
              <td className="td-2" style={{ fontSize: 11 }}>
                <span style={{ fontFamily: "var(--mono)" }}>
                  {fmtFecha(t.vigencia_desde)} → {fmtFecha(t.vigencia_hasta)}
                </span>
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
          <div className="cat-title">Tarifas por plaza</div>
          <div className="cat-sub">
            Tarifas de referencia por plaza, tipo de señal y duración. Se sugieren al capturar
            órdenes; el precio final por estación puede sobreescribirse.
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
        searchPlaceholder="Buscar por plaza, estado o notas…"
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
