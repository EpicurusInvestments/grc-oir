/** Caché en memoria de los catálogos de referencia de F1 (subconjunto de F0).
 *
 * No son los tipos reales de `modules/catalogos/*` (esos vienen del backend vía API) — son
 * un espejo simplificado, solo con los campos que las pantallas de F1 necesitan leer.
 *
 * Los arreglos nacen VACÍOS: `adapters/catalogosApi.ts::cargarCatalogosReales()` los llena
 * con datos reales del backend antes de que `OrdenesProvider` se monte (`OrdenesExplorerPage`
 * no renderiza ningún componente que lea de aquí hasta que esa carga resuelve) — así que
 * nunca hay nada que mostrar antes de que lleguen los datos reales.
 */

export interface AgenciaRef {
  id: string;
  nombre_agencia: string;
  rfc_agencia: string;
  porcentaje_comision_agencia_default: number;
}

export interface AnuncianteRef {
  id: string;
  agencia_id: string | null;
  nombre_comercial: string;
  nombre_fiscal: string;
  rfc_anunciante: string;
  dias_credito_default: number;
  categoria_id: string;
}

export interface MarcaRef {
  id: string;
  anunciante_id: string;
  nombre_marca: string;
}

export type EstadoContratoRef = "vigente" | "finalizado";

export interface ContratoRef {
  id: string;
  anunciante_id: string;
  numero_contrato: string;
  nombre_contrato: string;
  estado_contrato: EstadoContratoRef;
}

export interface VendedorRef {
  id: string;
  nombre_vendedor: string;
  porcentaje_comision_default: number;
}

export interface CategoriaRef {
  id: string;
  nombre_categoria: string;
}

export interface EmpresaFacturadoraRef {
  id: string;
  nombre_empresa: string;
  razon_social_empresa: string;
  rfc_empresa: string;
}

export interface PlazaRef {
  id: string;
  nombre_plaza: string;
  estado: string;
}

export interface AfiliadoRef {
  id: string;
  nombre_afiliado: string;
  plaza_id: string;
  porcentaje_participacion_oir_default: number;
}

export type TipoSenal = "fm" | "am" | "tv";

export interface EstacionRef {
  id: string;
  afiliado_id: string;
  plaza_id: string;
  nombre_estacion: string;
  frecuencia: string;
  tipo_senal: TipoSenal;
}

export interface TarifaRef {
  id: string;
  plaza_id: string;
  tipo_senal: TipoSenal;
  duracion_spot: string;
  tarifa_bruta: number;
  descuento_pct: number;
}

export const agencias: AgenciaRef[] = [];
export const categorias: CategoriaRef[] = [];
export const anunciantes: AnuncianteRef[] = [];
export const marcas: MarcaRef[] = [];
export const contratos: ContratoRef[] = [];
export const vendedores: VendedorRef[] = [];
export const empresasFacturadoras: EmpresaFacturadoraRef[] = [];
export const plazas: PlazaRef[] = [];
export const afiliados: AfiliadoRef[] = [];
export const estaciones: EstacionRef[] = [];
export const tarifas: TarifaRef[] = [];

export function findAgencia(id: string | null): AgenciaRef | null {
  return id ? (agencias.find((a) => a.id === id) ?? null) : null;
}
export function findAnunciante(id: string): AnuncianteRef | undefined {
  return anunciantes.find((a) => a.id === id);
}
export function marcasDeAnunciante(anuncianteId: string): MarcaRef[] {
  return marcas.filter((m) => m.anunciante_id === anuncianteId);
}
export function contratosVigentesDeAnunciante(anuncianteId: string): ContratoRef[] {
  return contratos.filter((c) => c.anunciante_id === anuncianteId && c.estado_contrato === "vigente");
}
export function findVendedor(id: string | null): VendedorRef | null {
  return id ? (vendedores.find((v) => v.id === id) ?? null) : null;
}
export function findEstacion(id: string): EstacionRef | undefined {
  return estaciones.find((e) => e.id === id);
}
export function findAfiliado(id: string): AfiliadoRef | undefined {
  return afiliados.find((a) => a.id === id);
}
export function findPlaza(id: string): PlazaRef | undefined {
  return plazas.find((p) => p.id === id);
}
export function tarifaReferencia(plazaId: string, tipoSenal: TipoSenal, duracionSpot: string): TarifaRef | undefined {
  return tarifas.find(
    (t) => t.plaza_id === plazaId && t.tipo_senal === tipoSenal && t.duracion_spot === duracionSpot,
  );
}
