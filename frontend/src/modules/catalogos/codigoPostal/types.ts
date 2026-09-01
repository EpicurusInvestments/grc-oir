/** Un asentamiento (colonia) para un código postal — alineado al backend
 * (app/modules/catalogos/codigo_postal.py). Un mismo CP suele tener varias. */
export interface AsentamientoPostal {
  codigo_postal: string;
  asentamiento: string;
  tipo_asentamiento: string | null;
  municipio: string;
  estado: string;
  ciudad: string | null;
  pais: string;
}
