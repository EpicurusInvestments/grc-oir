/** Puebla los catálogos de referencia de F1 (`state/catalogosCache.ts`) con datos REALES
 * del backend F0.
 *
 * Decisión de diseño: en vez de tocar los ~12 archivos que hacen
 * `import { findAgencia, ... } from "../state/catalogosCache"` (componentes, formularios,
 * selectores), MUTAMOS EN SITIO los arreglos que ya exporta ese módulo
 * (`agencias`, `anunciantes`, …). Como son `const` de BINDING pero arreglos MUTABLES,
 * y los `find*`/lookups ya operan sobre esas mismas referencias, esto deja a TODO el
 * resto del módulo sin cambios — ni un import, ni una llamada.
 *
 * 3 campos de los `*Ref` NO existen en el modelo real (hallazgos ya documentados en
 * `backend/scripts/seed_dev.py`, Tanda 2) y no los lee ningún componente: se rellenan
 * con un placeholder inerte, nunca se muestran.
 */

import { afiliadoApi, estacionApi } from "@/modules/catalogos/afiliado/api";
import { agenciaApi } from "@/modules/catalogos/agencia/api";
import { anuncianteApi, marcaApi } from "@/modules/catalogos/anunciante/api";
import { categoriaApi } from "@/modules/catalogos/categoria/api";
import type { EstadoContrato } from "@/modules/catalogos/contrato/types";
import { contratoApi } from "@/modules/catalogos/contrato/api";
import { empresaFacturadoraApi } from "@/modules/catalogos/empresaFacturadora/api";
import { plazaApi } from "@/modules/catalogos/plaza/api";
import { tarifaApi } from "@/modules/catalogos/tarifa/api";
import { vendedorApi } from "@/modules/catalogos/vendedor/api";
import { fetchAllPages } from "@/shared/lib/fetchAllPages";

import {
  afiliados,
  agencias,
  anunciantes,
  categorias,
  contratos,
  empresasFacturadoras,
  estaciones,
  marcas,
  plazas,
  tarifas,
  vendedores,
} from "../state/catalogosCache";

/** `estado_contrato` real (4 valores) → el `EstadoContratoRef` de la demo (solo 2: el
 * único consumidor, `contratosVigentesDeAnunciante`, únicamente distingue "vigente" de
 * "todo lo demás") — suspendido/cancelado se tratan como no-vigentes. */
function estadoContratoRef(estado: EstadoContrato): "vigente" | "finalizado" {
  return estado === "vigente" ? "vigente" : "finalizado";
}

/** Reemplaza el CONTENIDO de un arreglo mock en sitio (misma referencia, se conserva
 * para quien ya la tenga importada — p.ej. `find*` cerrado sobre el arreglo). */
function reemplazar<T>(arr: T[], nuevos: T[]): void {
  arr.length = 0;
  arr.push(...nuevos);
}

export async function cargarCatalogosReales(): Promise<void> {
  const [
    agenciasReales,
    anunciantesReales,
    marcasReales,
    contratosReales,
    vendedoresReales,
    categoriasReales,
    empresasReales,
    plazasReales,
    afiliadosReales,
    estacionesReales,
    tarifasReales,
  ] = await Promise.all([
    fetchAllPages((p) => agenciaApi.list(p)),
    fetchAllPages((p) => anuncianteApi.list(p)),
    fetchAllPages((p) => marcaApi.list(p)),
    fetchAllPages((p) => contratoApi.list(p)),
    fetchAllPages((p) => vendedorApi.list(p)),
    fetchAllPages((p) => categoriaApi.list(p)),
    fetchAllPages((p) => empresaFacturadoraApi.list(p)),
    fetchAllPages((p) => plazaApi.list(p)),
    fetchAllPages((p) => afiliadoApi.list(p)),
    fetchAllPages((p) => estacionApi.list(p)),
    fetchAllPages((p) => tarifaApi.list(p)),
  ]);

  reemplazar(
    agencias,
    agenciasReales.map((a) => ({
      id: a.agencia_id,
      nombre_agencia: a.nombre_agencia,
      rfc_agencia: a.rfc_agencia,
      porcentaje_comision_agencia_default: Number(a.porcentaje_comision_agencia_default),
      activo: a.activo,
    })),
  );

  reemplazar(
    anunciantes,
    anunciantesReales.map((a) => ({
      id: a.anunciante_id,
      agencia_id: a.agencia_id,
      nombre_comercial: a.nombre_comercial,
      nombre_fiscal: a.nombre_fiscal,
      rfc_anunciante: a.rfc_anunciante,
      dias_credito_default: a.dias_credito_default,
      // `categoria_id` no existe en el Anunciante real (vive en OrdenCliente, por venta) y
      // ningún componente de esta demo lo lee desde AnuncianteRef — placeholder inerte.
      categoria_id: "",
      activo: a.activo,
    })),
  );

  reemplazar(
    marcas,
    marcasReales.map((m) => ({
      id: m.marca_id,
      anunciante_id: m.anunciante_id,
      nombre_marca: m.nombre_marca,
      activo: m.activo,
    })),
  );

  reemplazar(
    contratos,
    contratosReales.map((c) => ({
      id: c.contrato_id,
      anunciante_id: c.anunciante_id,
      numero_contrato: c.numero_contrato,
      nombre_contrato: c.nombre_contrato,
      estado_contrato: estadoContratoRef(c.estado_contrato),
      activo: c.activo,
    })),
  );

  reemplazar(
    vendedores,
    vendedoresReales.map((v) => ({
      id: v.vendedor_id,
      nombre_vendedor: v.nombre_vendedor,
      porcentaje_comision_default: Number(v.porcentaje_comision_default),
      activo: v.activo,
    })),
  );

  reemplazar(
    categorias,
    categoriasReales.map((c) => ({ id: c.categoria_id, nombre_categoria: c.nombre_categoria, activo: c.activo })),
  );

  reemplazar(
    empresasFacturadoras,
    empresasReales.map((e) => ({
      id: e.empresa_facturadora_id,
      nombre_empresa: e.nombre_empresa,
      // `razon_social_empresa` no existe en el modelo real (el mock lo trae, el backend
      // tiene `direccion_empresa` — campo DISTINTO, hallazgo de la Tanda 2); nadie lo lee
      // desde EmpresaFacturadoraRef — placeholder de mejor esfuerzo, nunca se muestra.
      razon_social_empresa: e.direccion_empresa ?? e.nombre_empresa,
      rfc_empresa: e.rfc_empresa,
      activo: e.activo,
    })),
  );

  reemplazar(
    plazas,
    plazasReales.map((p) => ({ id: p.plaza_id, nombre_plaza: p.nombre_plaza, estado: p.estado ?? "" })),
  );

  reemplazar(
    afiliados,
    afiliadosReales.map((a) => ({
      id: a.afiliado_id,
      nombre_afiliado: a.nombre_afiliado,
      plaza_id: a.plaza_id,
      // La spec no tiene un % de participación OIR por AFILIADO (es por OrdenEstacion,
      // por venta); nadie lo lee desde AfiliadoRef — placeholder inerte.
      porcentaje_participacion_oir_default: 0,
    })),
  );

  reemplazar(
    estaciones,
    estacionesReales.map((e) => ({
      id: e.estacion_id,
      afiliado_id: e.afiliado_id,
      plaza_id: e.plaza_id,
      nombre_estacion: e.nombre_estacion,
      frecuencia: e.frecuencia ?? "",
      tipo_senal: e.tipo_senal,
      activo: e.activo,
    })),
  );

  reemplazar(
    tarifas,
    tarifasReales.map((t) => ({
      id: t.tarifa_plaza_id,
      plaza_id: t.plaza_id,
      tipo_senal: t.tipo_senal,
      duracion_spot: t.duracion_spot,
      tarifa_bruta: Number(t.tarifa_bruta),
      descuento_pct: Number(t.descuento_pct),
    })),
  );
}
