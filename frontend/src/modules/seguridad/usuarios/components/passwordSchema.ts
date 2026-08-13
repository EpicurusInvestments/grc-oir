/** Política de contraseñas del cliente — espejo de `app/modules/usuarios/schemas.py`.
 *
 * El backend es quien manda (valida siempre); esto solo evita un viaje al servidor y da
 * el mensaje en el momento. Los dos límites vienen de allá:
 *   - mínimo 10 caracteres (longitud sobre complejidad, recomendación NIST);
 *   - máximo 72 BYTES, que es lo que bcrypt considera. Se cuenta en bytes y no en
 *     caracteres porque cada acento o 'ñ' ocupa 2 en UTF-8: "ñ"×40 son 40 caracteres pero
 *     80 bytes. Se rechaza en vez de recortar, para no dar una falsa sensación de
 *     contraseña más larga de la que realmente protege.
 */

import { z } from "zod";

export const MIN_CARACTERES = 10;
export const MAX_BYTES = 72;

export const bytesDe = (valor: string): number => new TextEncoder().encode(valor).length;

export const passwordSchema = z
  .string()
  .min(MIN_CARACTERES, `La contraseña debe tener al menos ${MIN_CARACTERES} caracteres.`)
  .refine(
    (valor) => bytesDe(valor) <= MAX_BYTES,
    `La contraseña no puede exceder ${MAX_BYTES} bytes (los acentos y la 'ñ' cuentan como 2).`,
  );
