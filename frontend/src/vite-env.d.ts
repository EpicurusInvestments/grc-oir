/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  /** Solo desarrollo: simula usuario/área para el RBAC mientras el SSO está pendiente. */
  readonly VITE_DEV_USER?: string;
  readonly VITE_DEV_AREA?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
