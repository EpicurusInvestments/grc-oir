/** Usuario actual (placeholder de desarrollo).
 *
 * Mientras el SSO corporativo está [[POR LLENAR]], se toma de las vars de entorno de Vite
 * (VITE_DEV_USER / VITE_DEV_AREA) con admin por defecto. El RBAC real lo valida SIEMPRE
 * el backend; esto es solo para la UX (mostrar usuario, decidir qué acciones ofrecer).
 * # TODO(SSO): reemplazar por la sesión real del proveedor corporativo.
 */
export const currentUser = {
  username: import.meta.env.VITE_DEV_USER ?? "dev.admin",
  area: import.meta.env.VITE_DEV_AREA ?? "admin",
};
