# API-CONTRACT — Sistema GRC-OIR

> Contrato de la API para humanos. La fuente TÉCNICA exacta es el OpenAPI que genera
> FastAPI (http://localhost:8000/docs); este documento agrega lo que el OpenAPI no
> cuenta: reglas de negocio, permisos requeridos, ejemplos y notas de uso.
> Documento VIVO: cada endpoint nuevo o modificado se registra aquí EN EL MISMO PR.

## Convenciones generales

- Base: `/api/v1`. Formato: JSON. OpenAPI en `/docs` y `/openapi.json`.
- **Autenticación:** el SSO corporativo está `[[POR LLENAR]]`. Mientras tanto, en
  `APP_ENV=development` el usuario se resuelve por headers de desarrollo
  `X-Dev-User` y `X-Dev-Area` (área ∈ ventas │ facturacion │ tesoreria │ cxc │ cxp │
  direccion │ nominas │ admin; default admin desde `.env`). Fuera de `development` sin
  SSO, la API responde **401** (falla cerrada). Ver ADR-008.
- **RBAC por área:** cada endpoint exige `requiere_permiso("<modulo>:<accion>")` con
  `accion ∈ leer|crear|editar`. La matriz área×módulo vive como datos en
  `core/security.py`. En catálogos (F0): solo **admin** escribe; las demás áreas leen.
- **Errores:** estructura uniforme `{ "error": { "codigo", "mensaje", "detalles" } }`.
  Códigos: `validacion` (422), `sin_permiso` (403), `no_autenticado` (401),
  `no_encontrado` (404), `transicion_invalida` (409), `error_dominio` (400).
- **Paginación de listas (catálogos):** por página con `?page` (≥1, default 1) y `?size`
  (1–100, default 20). Respuesta: `{ items, total, page, size, pages }`. Filtros:
  `?activo` (true|false|omitir=todos) y `?q` (búsqueda de texto).
- Los campos de origen "Calculado" (spec BD v2) NUNCA se aceptan en el request:
  los calcula el servidor. Los estados solo cambian por las transiciones permitidas.

## Salud (sin /api/v1)

- `GET /health` → `{ "status": "ok" }` (no toca BD; para liveness).
- `GET /health/db` → prueba la conexión a SQL Server (RDS) bajo demanda; útil para
  validar `.env` y red. Devuelve `{ "status": "ok", "db": "reachable" }` o
  `{ "status": "error", "db": "unreachable", ... }` (200 en ambos: es diagnóstico).

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

### Catálogos — patrón CRUD estándar (F0-00)

F0-00 no expone todavía ninguna entidad (no hay tablas; la primera llega en F0-01). Pero
deja la factory `build_crud_router(...)`: **cada catálogo de F0-01+ expondrá estos 5
endpoints** bajo `/api/v1/catalogos/<recurso>` (p.ej. `/catalogos/plazas`). Permiso base
`catalogos`; el patrón es idéntico para todos:

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /catalogos/<recurso>` | `catalogos:leer` | Lista paginada (`?page&size&activo&q`) → `Page` |
| `GET /catalogos/<recurso>/{id}` | `catalogos:leer` | Obtiene uno (404 si no existe) |
| `POST /catalogos/<recurso>` | `catalogos:crear` | Crea (201). Solo admin en F0 |
| `PUT /catalogos/<recurso>/{id}` | `catalogos:editar` | Edita. Solo admin en F0 |
| `POST /catalogos/<recurso>/{id}/estado` | `catalogos:editar` | Baja/alta lógica `{ "activo": bool }`. Nunca borra físico |

- **Response de lista (`Page`):**
```json
{ "items": [ { "...": "..." } ], "total": 42, "page": 1, "size": 20, "pages": 3 }
```
- **Errores posibles:** 401 (sin auth / fuera de development sin SSO), 403 (área sin
  permiso), 404 (no encontrado), 422 (validación). El detalle exacto de campos de cada
  catálogo se documentará en su propio bloque al implementarlo (F0-01+).
