/** Providers globales: TanStack Query + PrimeReact + sesión (F5-00).
 *
 * `SessionProvider` envuelve al router (ver `main.tsx`) porque la sesión debe estar
 * resuelta antes de que cualquier ruta —incluida /login— decida qué mostrar.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PrimeReactProvider } from "primereact/api";
import type { ReactNode } from "react";

import { SessionProvider } from "@/modules/auth/session";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <PrimeReactProvider>
        <SessionProvider>{children}</SessionProvider>
      </PrimeReactProvider>
    </QueryClientProvider>
  );
}
