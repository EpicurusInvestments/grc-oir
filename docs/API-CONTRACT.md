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
  `no_encontrado` (404), `transicion_invalida` (409), `conflicto` (409),
  `dependencias_activas` (409), `error_dominio` (400).
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
| `POST /catalogos/<recurso>/{id}/estado` | `catalogos:editar` | Baja/alta lógica `{ "activo": bool, "forzar": bool }`. Nunca borra físico |

- **Response de lista (`Page`):**
```json
{ "items": [ { "...": "..." } ], "total": 42, "page": 1, "size": 20, "pages": 3 }
```
- **`forzar` en el cambio de estado:** por defecto `false`. Si una baja (`activo:false`)
  tiene dependientes activos, el servicio responde **409 `dependencias_activas`** con el
  conteo en `detalles`; el cliente confirma con el usuario y reintenta con `forzar:true`.
- **Errores posibles:** 401 (sin auth / fuera de development sin SSO), 403 (área sin
  permiso), 404 (no encontrado), 422 (validación), 409 (`conflicto`/`dependencias_activas`).

### Catálogos operativos (F0-01) — Plaza · Afiliado · Estación

Tres catálogos encadenados (Plaza ← Afiliado ← Estación) sobre el patrón CRUD estándar.
PKs `UNIQUEIDENTIFIER`; textos `NVARCHAR`; `created_at`/`updated_at` en las tres
entidades (`DATETIME2`). Escritura solo **admin** en F0.

**`/catalogos/plazas`** — campos: `plaza_id`, `nombre_plaza` (req.), `estado`, `activo`,
`created_at`, `updated_at`. Búsqueda `?q` sobre nombre y estado.
- **Derivado (solo lectura):** `estaciones_count` = nº de estaciones en la plaza (**todas**,
  activas e inactivas). No se acepta en Create/Update; se calcula en el servicio con una
  consulta agregada por lote (sin N+1).
- **Baja con dependientes:** no se puede desactivar una plaza con **afiliados activos o
  estaciones activas** sin `forzar:true` (→ 409 `dependencias_activas`,
  `detalles: { afiliados_activos, estaciones_activas }`).

**`/catalogos/afiliados`** — campos: `afiliado_id`, `nombre_afiliado` (req.),
`razon_social_afiliado` (req.), `rfc_afiliado` (req., **único**), `plaza_id` (req., FK),
`contacto_nombre`, `contacto_email`, `contacto_telefono`, `activo`, timestamps.
- **Derivados (solo lectura):** `plaza_nombre` = `nombre_plaza` de la plaza referenciada
  por `plaza_id`; `estaciones_count` = nº de estaciones del afiliado (**todas**, mismo
  criterio que Plaza). No se aceptan en Create/Update; se calculan en el servicio por lote
  (sin N+1).
- **RFC:** formato oficial mexicano de **12-13 caracteres** (12 = persona moral, 13 =
  física); se normaliza a mayúsculas. Único: RFC repetido → **409 `conflicto`**.
- **Baja con dependientes:** afiliado con **estaciones activas** → 409 `dependencias_activas`
  (`detalles: { estaciones_activas }`) salvo `forzar:true`.
- Búsqueda `?q` sobre nombre, razón social y RFC.

**`/catalogos/estaciones`** — campos: `estacion_id`, `afiliado_id` (req., FK),
`plaza_id` (**derivada**, FK), `nombre_estacion` (req.), `frecuencia`,
`tipo_senal` (`fm|am|tv`, CHECK), `activo`, timestamps.
- **Herencia de plaza (ADR-005):** `plaza_id` NO se envía en `POST`/`PUT`; el servicio la
  asigna = `Afiliado.plaza_id` (si cambia el afiliado en un `PUT`, se recalcula). Si el
  `afiliado_id` no existe → 404.
- **`GET /catalogos/estaciones/afiliado/{afiliado_id}`** (`catalogos:leer`): estaciones de
  un afiliado, paginado con los mismos filtros `?page&size&activo&q`. Alimenta el panel
  anidado de la pantalla de afiliados.

Ejemplo alta de estación (sin `plaza_id`):
```json
{ "afiliado_id": "3f...", "nombre_estacion": "XHMT-FM", "frecuencia": "90.1 FM", "tipo_senal": "fm" }
```

### Tarifas por plaza (F0-02) — TarifaPlaza

Catálogo de tarifas de referencia por **plaza + tipo de señal + duración de spot**, con
vigencia, sobre el patrón CRUD estándar (escritura solo **admin** en F0). Depende de Plaza.

**`/catalogos/tarifas`** — campos: `tarifa_plaza_id`, `plaza_id` (req., FK),
`tipo_senal` (`fm|am|tv`, CHECK), `duracion_spot` (`20s|30s|60s|mencion`, CHECK),
`tarifa_bruta` (req., ≥0), `descuento_pct` (req., 0–100), **`tarifa_neta` (Calculado)**,
`vigencia_desde` (req.), `vigencia_hasta` (req.), `notas`, `activo`, `created_at`,
`created_by`, `updated_at`.
- **Montos como string:** `tarifa_bruta`, `descuento_pct` y `tarifa_neta` viajan como
  **string** en el JSON (entrada y salida) para preservar la precisión `Decimal` (E-4). El
  servidor acepta también número, pero devuelve string.
- **Campo calculado `tarifa_neta`:** `tarifa_bruta * (1 - descuento_pct/100)`, redondeado a
  2 decimales. **NO se acepta en Create/Update** (no está en el request); lo calcula y
  persiste el servidor, y lo recalcula en cada edición.
- **Derivados (solo lectura):** `plaza_nombre` y `plaza_estado` (nombre y estado geográfico
  de la plaza referenciada), calculados por lote (sin N+1). No se aceptan en Create/Update.
- **`created_by`:** username del capturista (texto, no FK; la entidad Usuario llega en
  F0-04). Lo fija el servidor desde el usuario autenticado, no el cliente.
- **Vigencia:** `vigencia_hasta >= vigencia_desde` (ambas obligatorias). Violarla → **422**
  en el request (validación de schema) o **400 `error_dominio`** si se detecta en el
  servicio con valores efectivos (edición parcial que solo cambia una fecha).
- **Sin solapamiento (409 `conflicto`):** al crear, editar o **reactivar** una tarifa
  activa, no puede existir OTRA tarifa activa con la misma combinación (plaza + tipo_senal +
  duracion_spot) cuyo rango `[vigencia_desde, vigencia_hasta]` se solape (bordes
  **inclusivos**: tocarse un día ya es solape). `detalles` incluye la tarifa en conflicto y
  su vigencia.
- **Filtros de lista:** además de `?activo` y `?q` (busca en notas), acepta:
  - **`?vigencia=todas|vigente|expirada`** (derivado de `vigencia_hasta` vs la fecha del
    servidor: `vigente` = no vencida, `expirada` = vencida). Dimensión independiente de
    `activo`. La fecha "hoy" la fija el servidor, no el cliente.
  - **`?plaza_id`** (UUID): acota a una plaza. Combinado con `activo=true&vigencia=vigente`
    alimenta la sección "Tarifas vigentes" del panel de detalle de Plaza.
- **Búsqueda `?q`:** coincidencia parcial case-insensitive sobre **nombre de la plaza,
  estado de la plaza y notas** (coincide en cualquiera). Resuelta con un JOIN a `plaza` en
  el repositorio (sin N+1); `ilike` portable a SQL Server.

Ejemplo alta de tarifa (sin `tarifa_neta`):
```json
{
  "plaza_id": "1a...", "tipo_senal": "fm", "duracion_spot": "30s",
  "tarifa_bruta": "9000.00", "descuento_pct": "10",
  "vigencia_desde": "2025-01-01", "vigencia_hasta": "2025-12-31",
  "notas": "Tarifa general FM CDMX"
}
```
Fragmento de la respuesta (montos como string; `tarifa_neta` calculada + derivados):
```json
{
  "tarifa_plaza_id": "9c...", "tarifa_bruta": "9000.00", "descuento_pct": "10",
  "tarifa_neta": "8100.00", "plaza_nombre": "CDMX", "plaza_estado": "Ciudad de México",
  "created_by": "admin", "activo": true
}
```

### Parámetros sensibles y auditoría (F0-03) — mecanismo transversal

Algunos campos de la spec están marcados como **PARÁMETRO SENSIBLE** (p.ej.
`porcentaje_comision_agencia_default`, `dias_credito_default`,
`porcentaje_comision_contrato`). Al **crear o modificar** uno de ellos, el servicio aplica
—una sola vez, en `core/`— el mecanismo de campo sensible (ver ADR-016):

1. **Permiso por campo:** `field_permissions.verificar(...)`. Por ahora **solo `admin`**
   puede escribir estos campos; cualquier otra área → **403 `sin_permiso`** aunque tuviera
   permiso de escritura del catálogo.
2. **Motivo del cambio:** en **edición**, si el valor cambia, el request DEBE incluir
   `motivo_cambio` (string no vacío); su ausencia → **400 `error_dominio`**. En el **alta**
   NO se exige motivo (es la captura inicial).
3. **Bitácora:** se registra una fila en `LogCambioParametro` (entidad, entidad_id, campo,
   valor anterior/nuevo, usuario, ip, fecha, motivo) en la **misma transacción** que el
   cambio. Editar un campo NO sensible, o "cambiarlo" al mismo valor, **no** genera bitácora.

Notas de request: `motivo_cambio` es un campo **transitorio** del cuerpo de edición (no es
columna ni se devuelve en el `Read`). Los porcentajes viajan como **string** (precisión
`Decimal`, criterio E-4). `LogCambioParametro` se administra desde una pantalla en F5, pero
la tabla y el registro operan desde F0-03.

### Catálogos comerciales (F0-03) — Agencia · Anunciante · Marca · Contrato

Cadena comercial (Agencia ← Anunciante ← Marca/Contrato) sobre el patrón CRUD estándar
(escritura solo **admin** en F0). *Tanda 1: Agencia (Anunciante, Marca y Contrato llegan en
las siguientes tandas).*

**`/catalogos/agencias`** — campos: `agencia_id`, `nombre_agencia` (req., **único**),
`rfc_agencia` (req.), `contacto_nombre`, `contacto_email`, `contacto_telefono`,
**`porcentaje_comision_agencia_default` (PARÁMETRO SENSIBLE)**, `activo`, `created_at`,
`updated_at`.
- **`nombre_agencia` único (case-insensitive):** los nombres se normalizan colapsando
  espacios; la unicidad ignora mayúsculas/minúsculas (la BD `GRC-OIR` usa collation
  `SQL_Latin1_General_CP1_CI_AS`, case-insensitive; el servicio además compara con `LOWER()`
  para responder **409 `conflicto`** antes del insert).
- **RFC:** mismo formato oficial mexicano de **12-13 caracteres** que F0-01 (se reutiliza el
  regex); se normaliza a mayúsculas.
- **`porcentaje_comision_agencia_default`:** `NUMERIC(5,2)`, rango 0–100 (CHECK
  `ck_agencia_comision`), viaja como **string**. Es sensible: alta y edición pasan por el
  mecanismo de auditoría descrito arriba (`motivo_cambio` requerido al modificarlo).
- **Baja con dependientes:** no se puede desactivar una agencia con **anunciantes activos**
  sin `forzar:true` (→ 409 `dependencias_activas`, `detalles: { anunciantes_activos }`).
- Búsqueda `?q` sobre nombre y RFC.

Ejemplo alta de agencia:
```json
{
  "nombre_agencia": "Publicidad Total", "rfc_agencia": "PTO950101ABC",
  "contacto_nombre": "Ana López", "contacto_email": "ana@ejemplo.mx",
  "porcentaje_comision_agencia_default": "15.00"
}
```
Ejemplo edición del % sensible (motivo requerido):
```json
{ "porcentaje_comision_agencia_default": "12.50", "motivo_cambio": "Renegociación anual" }
```

**`/catalogos/anunciantes`** — campos: `anunciante_id`, **`agencia_id` (FK NULL = directo)**,
`nombre_comercial` (req.), `nombre_fiscal` (req., el que va en la factura),
`rfc_anunciante` (req.), `localizacion`, `referencia_anunciante`, `contacto_*`,
**`dias_credito_default` (PARÁMETRO SENSIBLE, entero ≥0)**, `activo`, timestamps.
- **Vía agencia / Directo:** `agencia_id` NULL ⇒ el anunciante es directo (sin agencia). Si
  se envía, debe existir (→ 404 si no). Filtro de lista **`?relacion=todas|via_agencia|directo`**
  (dimensión independiente de `?activo`).
- **`dias_credito_default`:** entero ≥0 (CHECK `ck_anunciante_dias_credito`). Es sensible:
  alta y edición pasan por el mecanismo de auditoría (motivo requerido al modificarlo).
- **RFC:** mismo formato 12-13 que Agencia/Afiliado (no único).
- **Derivados (solo lectura):** `agencia_nombre` (`nombre_agencia` de la agencia, o `null`
  si es directo) y `marcas_count` (nº de marcas del anunciante, **todas**). Calculados por
  lote (sin N+1); no se aceptan en Create/Update.
- **Baja con dependientes:** anunciante con **marcas activas** → 409 `dependencias_activas`
  (`detalles: { marcas_activas }`) salvo `forzar:true`. *(La validación por contratos
  activos se añade en la tanda 3.)*
- Búsqueda `?q` sobre nombre comercial, nombre fiscal y RFC.

Ejemplo alta directo (sin agencia) con días de crédito:
```json
{
  "nombre_comercial": "Refrescos del Valle", "nombre_fiscal": "Refrescos del Valle SA de CV",
  "rfc_anunciante": "RVA950101AB1", "dias_credito_default": 30
}
```

**`/catalogos/marcas`** — campos: `marca_id`, `anunciante_id` (req., FK), `nombre_marca`
(req.), `activo`, `created_at`, `updated_at`. **Se administra anidada dentro del Anunciante**
(no tiene entrada de sidebar propia), igual que Estación dentro de Afiliado.
- CRUD estándar + **`GET /catalogos/marcas/anunciante/{anunciante_id}`** (`catalogos:leer`):
  marcas de un anunciante, paginado con los filtros `?page&size&activo&q`. Alimenta el panel
  anidado de la pantalla de anunciantes.
- El `anunciante_id` debe existir (→ 404 si no). Sin campos sensibles.
