# API-CONTRACT — Sistema GRC-OIR

> Contrato de la API para humanos. La fuente TÉCNICA exacta es el OpenAPI que genera
> FastAPI (http://localhost:8000/docs); este documento agrega lo que el OpenAPI no
> cuenta: reglas de negocio, permisos requeridos, ejemplos y notas de uso.
> Documento VIVO: cada endpoint nuevo o modificado se registra aquí EN EL MISMO PR.

## Convenciones generales

- Base: `/api/v1`. Formato: JSON. Autenticación: [[POR LLENAR: esquema de token SSO]].
- Errores: estructura uniforme `{ "error": { "codigo", "mensaje", "detalles" } }`.
- Paginación de listas: [[POR LLENAR: ?page/?size o cursor]]. Filtros por query params.
- Los campos de origen "Calculado" (spec BD v2) NUNCA se aceptan en el request:
  los calcula el servidor. Los estados solo cambian por las transiciones permitidas.

## Plantilla para documentar un endpoint

### `MÉTODO /api/v1/<ruta>`
- **Módulo / Fase:** ...
- **Permiso requerido:** `<modulo>:<accion>` (áreas autorizadas según matriz RBAC)
- **Qué hace (negocio):** ...
- **Validaciones clave:** ...
- **Efectos secundarios:** (auditoría, cambios de estado, archivos generados)
- **Request ejemplo:**
```json
{ }
```
- **Response ejemplo:**
```json
{ }
```
- **Errores posibles:** 400 (validación), 403 (sin permiso), 409 (transición inválida)...

---

## Endpoints

[[Esta sección se llena conforme se desarrollan los módulos. Mantener agrupado por
módulo: Catálogos, Usuarios, Órdenes, Facturación, Cobranza, Pagos, Reportes, Seguridad.]]
