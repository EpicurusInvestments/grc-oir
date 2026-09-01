import { useQuery } from "@tanstack/react-query";

import { buscarCodigoPostal } from "./api";

/** Colonias de un CP de 5 dígitos — inactiva mientras no se completen los 5 (evita
 * disparar la búsqueda a medio escribir). El catálogo es estático dentro de la sesión:
 * `staleTime` largo para no repetir la misma búsqueda dos veces. */
export function useBuscarCodigoPostal(codigoPostal: string) {
  const cp = codigoPostal.trim();
  return useQuery({
    queryKey: ["codigo-postal", cp],
    queryFn: () => buscarCodigoPostal(cp),
    enabled: cp.length === 5,
    staleTime: 5 * 60_000,
  });
}
