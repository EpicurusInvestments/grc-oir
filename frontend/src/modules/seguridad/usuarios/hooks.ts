/** Hooks de Usuario: CRUD genérico + la mutación propia de F5-00 (contraseña). */

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useCatalog } from "@/shared/lib/useCatalog";

import { establecerPassword, usuarioApi } from "./api";

const KEY = "usuarios";

export function useUsuarios() {
  const crud = useCatalog(KEY, usuarioApi);
  const qc = useQueryClient();

  const useEstablecerPassword = () =>
    useMutation({
      mutationFn: ({ id, password }: { id: string; password: string }) =>
        establecerPassword(id, password),
      // Invalida la lista para refrescar `tiene_password`.
      onSuccess: () => qc.invalidateQueries({ queryKey: [KEY] }),
    });

  return { ...crud, useEstablecerPassword };
}
