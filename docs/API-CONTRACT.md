# API-CONTRACT — Sistema GRC-OIR

> Contrato de la API para humanos. La fuente TÉCNICA exacta es el OpenAPI que genera
> FastAPI (http://localhost:8000/docs); este documento agrega lo que el OpenAPI no
> cuenta: reglas de negocio, permisos requeridos, ejemplos y notas de uso.
> Documento VIVO: cada endpoint nuevo o modificado se registra aquí EN EL MISMO PR.

## Convenciones generales

- Base: `/api/v1`. Formato: JSON. OpenAPI en `/docs` y `/openapi.json`.
- **Autenticación (desde F5-00):** la API espera `Authorization: Bearer <token>`, donde el
  token lo emite `POST /api/v1/auth/login` y vive 8 h (configurable). El proveedor se elige
  con `AUTH_PROVIDER` (ADR-041):
  - `local` (**default**) — login con email + contraseña contra la tabla `usuario`.
  - `dev_headers` — modo desarrollo: el usuario se resuelve por los headers `X-Dev-User` /
    `X-Dev-Area` (área ∈ ventas │ facturacion │ tesoreria │ cxc │ cxp │ direccion │ nominas │
    admin; default admin desde `.env`). **Solo con `APP_ENV=development`**; fuera de ahí
    responde **401** (falla cerrada, ADR-008). Con este proveedor NO hay `/auth/login`.
  - `azure_ad` — interfaz preparada, implementación diferida: responde **500**
    `configuracion_invalida` con un mensaje claro.
  Sin token (o con token expirado/alterado) cualquier endpoint protegido responde **401**
  `no_autenticado`; `detalles.motivo` distingue `expirado` │ `invalido` │ `revocado`.
- **RBAC por área:** cada endpoint exige `requiere_permiso("<modulo>:<accion>")` con
  `accion ∈ leer|crear|editar`. La matriz área×módulo vive como datos en
  `core/security.py`. En catálogos (F0): solo **admin** escribe; las demás áreas leen.
- **Errores:** estructura uniforme `{ "error": { "codigo", "mensaje", "detalles" } }`.
  Códigos: `validacion` (422), `sin_permiso` (403), `no_autenticado` (401),
  `no_encontrado` (404), `transicion_invalida` (409), `conflicto` (409),
  `dependencias_activas` (409), `error_dominio` (400),
  `configuracion_invalida` (500 — el servidor está mal configurado, no el request).
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

### Autenticación (F5-00) — login, sesión y cierre

Base `/api/v1/auth`. Estos endpoints **no** pasan por la matriz RBAC: `login` es público
(es lo que otorga la sesión) y `me` solo exige una sesión válida, sin permiso de módulo.

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `POST /auth/login` | — (público) | Valida credenciales y emite el token de sesión |
| `GET /auth/me` | sesión válida | Identidad y área del usuario en sesión |
| `POST /auth/logout` | — | 204. El token es *stateless*: la sesión se cierra al descartarlo en el cliente |

#### `POST /api/v1/auth/login`
- **Módulo / Fase:** auth / F5-00 (adelanto de F5)
- **Permiso requerido:** ninguno (público)
- **Qué hace (negocio):** autentica con **email + contraseña** contra la tabla `usuario` y
  devuelve un JWT con la identidad y el área. Solo disponible con `AUTH_PROVIDER=local`;
  con otro proveedor responde 500 `configuracion_invalida`.
- **Validaciones clave:** email 3–160 caracteres (se normaliza a minúsculas y sin espacios);
  contraseña 1–200. El usuario debe estar `activo` y tener contraseña establecida.
- **Efectos secundarios:** ninguno (no persiste sesión: el token es *stateless*).
- **Request ejemplo:**
```json
{ "email": "dev.admin@grcoir.com", "password": "••••••••" }
```
- **Response ejemplo (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expira_en": "2026-08-12T20:00:00Z",
  "usuario": {
    "usuario_id": "00000000-0000-0000-0000-000000000001",
    "nombre_usuario": "dev.admin",
    "email": "dev.admin@grcoir.com",
    "area": "admin"
  }
}
```
- **Errores posibles:** **401** `no_autenticado` con el mensaje genérico
  `"Usuario o contraseña incorrectos."` — es **el mismo** para usuario inexistente,
  contraseña incorrecta, usuario inactivo y usuario sin contraseña (no se revela si un
  correo está dado de alta); 422 (validación); 500 `configuracion_invalida` (proveedor sin
  login local, o `SECRET_KEY` de ejemplo fuera de `development`).

#### `GET /api/v1/auth/me`
- **Permiso requerido:** sesión válida (`Authorization: Bearer <token>`)
- **Qué hace (negocio):** devuelve la identidad vigente. El área y el estado `activo` se
  **releen de la base en cada petición**, no del token: desactivar a un usuario o cambiarle
  el área invalida su sesión de inmediato, sin esperar a que expire.
- **Response ejemplo (200):**
```json
{ "usuario_id": "0000...0001", "nombre_usuario": "dev.admin",
  "email": "dev.admin@grcoir.com", "area": "admin" }
```
- **Errores posibles:** 401 `no_autenticado` con `detalles.motivo` ∈ `expirado` │
  `invalido` │ `revocado`. En modo `dev_headers`, `usuario_id` y `email` van en `null`
  (ese proveedor no consulta la tabla `usuario`).

### Gestión de usuarios (F5-00) — solo Admin

Base `/api/v1/usuarios`. Permiso base `usuarios`, que en la matriz RBAC existe **solo para
Admin, incluso en lectura**: el padrón de usuarios no es un catálogo consultable por las
demás áreas. Cualquier otra área recibe **403** `sin_permiso` en todos los verbos.

| Método y ruta | Permiso | Qué hace |
|---|---|---|
| `GET /usuarios` | `usuarios:leer` | Lista paginada (`?page&size&activo&q`) → `Page<UsuarioRead>` |
| `GET /usuarios/{id}` | `usuarios:leer` | Un usuario |
| `POST /usuarios` | `usuarios:crear` | Alta (contraseña opcional) |
| `PUT /usuarios/{id}` | `usuarios:editar` | Edita nombre, email, área, roles |
| `POST /usuarios/{id}/estado` | `usuarios:editar` | Activa / desactiva (baja lógica) |
| `POST /usuarios/{id}/password` | `usuarios:editar` | (Re)establece la contraseña |

**`UsuarioRead` nunca incluye `password_hash`.** En su lugar expone `tiene_password`
(booleano) para que la UI marque a los usuarios que aún no pueden iniciar sesión.

#### `POST /api/v1/usuarios`
- **Validaciones clave:** `email` único **case-insensitive** (se normaliza a minúsculas) →
  409 `conflicto`; `area` ∈ el ENUM de áreas → 422; `nombre_usuario` con espacios
  normalizados. `password` es **opcional**: sin ella el usuario queda dado de alta pero
  **no puede entrar** hasta que se le establezca una (fail-closed).
- **Política de contraseñas:** mínimo **10 caracteres** y máximo **72 bytes**. El máximo se
  cuenta en *bytes*, no en caracteres (cada acento o `ñ` cuenta 2 en UTF-8), porque bcrypt
  ignora lo que exceda: se **rechaza** con 422 en vez de recortar en silencio.
- **Request ejemplo:**
```json
{ "nombre_usuario": "Beto Cobranza", "email": "beto@grcoir.com",
  "area": "cxc", "password": "••••••••••" }
```
- **Response ejemplo (201):**
```json
{ "usuario_id": "3f2a...", "nombre_usuario": "Beto Cobranza",
  "email": "beto@grcoir.com", "area": "cxc", "roles_adicionales": null,
  "activo": true, "created_at": "2026-08-12T10:00:00", "tiene_password": true }
```

#### `PUT /api/v1/usuarios/{id}` y `POST /api/v1/usuarios/{id}/estado`
- **Efectos secundarios (auditoría):** cambiar `area` o `activo` escribe en
  **`LogCambioParametro`** (entidad `Usuario`, con valor anterior/nuevo, quién y cuándo).
  Son los dos campos que otorgan o quitan acceso al sistema. `activo` se audita en **ambos
  sentidos**, no solo la baja. Si el valor no cambia, no se registra nada.
- **Guardarraíl anti-auto-bloqueo:** un usuario **no puede desactivarse a sí mismo ni
  cambiarse su propia área** → 400 `error_dominio`. Sin esto, el último Admin puede dejar
  al sistema sin quien administre usuarios, y recuperarlo exigiría entrar a la base a mano.
  Sí puede hacerlo sobre *otro* Admin.
- **Efecto en las sesiones:** desactivar a un usuario **invalida su sesión en curso** de
  inmediato (el estado se relee de la base en cada petición, ver ADR-041) y le impide
  volver a iniciar sesión.

#### `POST /api/v1/usuarios/{id}/password`
- **Qué hace (negocio):** establece o reemplaza la contraseña. Endpoint separado de la
  edición del perfil a propósito: cambiar una contraseña es un acto explícito, no un efecto
  colateral de guardar un formulario.
- **Validaciones clave:** misma política que en el alta (10 caracteres / 72 bytes).
- **Efecto:** la contraseña anterior deja de funcionar de inmediato. Las **sesiones ya
  emitidas siguen vivas** hasta expirar, porque el token es *stateless* (limitación
  conocida documentada en ADR-041).
- **Efectos secundarios (traza):** el reseteo **no** va a `LogCambioParametro` (esa tabla
  guarda valor anterior/nuevo de parámetros de negocio; un reseteo no tiene valores que
  mostrar ahí). Queda registrado en el **log de seguridad** (`core/security_log.py`,
  logger `grcoir.seguridad`): quién reseteó, a quién, desde qué IP y cuándo — **nunca** la
  contraseña ni el hash. La bitácora de seguridad formal (tabla + pantalla) es de F5 pleno.
- **Request ejemplo:**
```json
{ "password": "••••••••••" }
```

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
- **Derivado (solo lectura):** `anunciantes_count` = nº de anunciantes de la agencia
  (**todos**), calculado por lote (JOIN + COUNT agrupado, sin N+1).
- Búsqueda `?q` sobre nombre y RFC.

**`GET /catalogos/agencias/{id}/historial`** (`catalogos:leer`) — historial de auditoría de
UNA agencia: lee `LogCambioParametro` filtrado por (`entidad="Agencia"`, `entidad_id=id`),
ordenado del **más reciente al más antiguo**. Devuelve una lista de
`{ log_cambio_parametro_id, entidad, entidad_id, campo, valor_anterior, valor_nuevo,
usuario, ip, motivo_cambio, fecha_cambio }`. 404 si la agencia no existe.
- **Alcance:** lectura acotada a una entidad para la sección "Historial de cambios" del
  panel; la **administración completa** de auditoría es de F5 (ver ADR-021).

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
- **`GET /catalogos/anunciantes/agencia/{agencia_id}`** (`catalogos:leer`): anunciantes de
  una agencia, paginado con los filtros `?page&size&activo&q`. Alimenta la sección
  "Anunciantes representados" del panel de detalle de Agencia.
- **`GET /catalogos/anunciantes/{id}/historial`** (`catalogos:leer`): historial de auditoría
  del anunciante (cambios de `dias_credito_default`), más reciente primero. Mismo formato y
  alcance acotado que el de Agencia (ver ADR-021).

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

**`/catalogos/contratos`** — campos: `contrato_id`, `anunciante_id` (req., FK),
`numero_contrato` (req.), `nombre_contrato` (req.), `fecha_inicio_contrato` (req.),
`fecha_fin_contrato` (req.), `monto_contrato` (Decimal, string), **`porcentaje_comision_contrato`
(PARÁMETRO SENSIBLE, Decimal string, nullable)**, `condiciones_comerciales`,
`estado_contrato` (ENUM, **solo lectura vía CRUD**), `archivo_contrato_path`,
`observaciones_contrato`, `activo`, `created_by`, timestamps.
- **Fechas:** `fecha_fin_contrato >= fecha_inicio_contrato` → 422 (schema) o 400
  `error_dominio` (servicio, en edición parcial con valores efectivos).
- **`porcentaje_comision_contrato`:** NUMERIC(5,2) nullable (CHECK `NULL o 0..100`).
  Sobreescribe el % default de la agencia cuando tiene valor. Es sensible: se audita en el
  **alta solo si se captura** un valor, y en la edición cuando cambia (motivo requerido,
  solo Admin). Viaja como **string**.
- **`created_by`:** username del capturista (texto, no FK; lo fija el servidor).
- **`estado_contrato`:** `vigente|suspendido|finalizado|cancelado`. **NO** se cambia por el
  `PUT` genérico (no está en Create/Update); se crea en `vigente` y se transiciona por el
  endpoint dedicado (abajo). Es una dimensión **independiente** de `activo` (baja lógica).
- **Adjuntos (PDF):** `archivo_contrato_path` = prefijo `contratos/<numero_contrato>/`
  (recalculado si cambia el número). La subida/descarga real está **implementada** (ADR-027);
  ver endpoints de adjuntos abajo. Backend de almacenamiento por `STORAGE_BACKEND` (local|s3).
- **Derivados (solo lectura):** `anunciante_nombre` (`nombre_comercial`) y `anunciante_rfc`
  (`rfc_anunciante`) del anunciante, calculados por lote (sin N+1).
- **Filtro por estado:** la lista acepta **`?estado=vigente|suspendido|finalizado|cancelado`**
  (además de `?activo` y `?q`). Alimenta las pills Todos/Vigentes/Finalizados de la pantalla.
- Búsqueda `?q` sobre número y nombre del contrato.
- **`GET /catalogos/contratos/{id}/historial`** (`catalogos:leer`): historial de auditoría
  del contrato (cambios de `porcentaje_comision_contrato`), más reciente primero. Mismo
  formato y alcance acotado que Agencia/Anunciante (ADR-021).

**`GET /catalogos/contratos/anunciante/{anunciante_id}`** (`catalogos:leer`) — contratos de
un anunciante, paginado con `?page&size&activo&q`. Alimenta la sección "Contratos" del panel
de detalle de Anunciante.

**`POST /catalogos/contratos/{id}/estado-contrato`** (`catalogos:editar`) — transiciona
`estado_contrato` validando la **máquina de estados**. Cuerpo: `{ "estado": "suspendido" }`.
- Transiciones permitidas: `vigente→{suspendido,finalizado,cancelado}`,
  `suspendido→{vigente,cancelado}`, `finalizado→{cancelado}`, `cancelado→∅` (terminal).
- Transición no permitida → **409 `transicion_invalida`** (`detalles` lista las permitidas).
  Transicionar al mismo estado es idempotente (no cambia nada). No afecta `activo`.

**Adjuntos (PDF) del contrato** (ADR-027) — bucket **privado**; los PDF se sirven SIEMPRE
por el backend (nunca URL pública). El cliente maneja solo el **nombre** de archivo; la clave
S3 la compone el servidor a partir del prefijo del propio contrato (bloquea *path traversal*).
El backend de almacenamiento (local o S3) se elige por `STORAGE_BACKEND`.

- **`GET /catalogos/contratos/{id}/adjuntos`** (`catalogos:leer`) — lista los PDF del
  contrato. Devuelve `[{ "nombre", "tamano_bytes", "modificado_en" }]`.
- **`POST /catalogos/contratos/{id}/adjuntos`** (`catalogos:editar`) — sube un PDF.
  `multipart/form-data` con el campo **`archivo`**. Valida tipo (extensión `.pdf` + *magic
  bytes* `%PDF-`) y tamaño (`S3_MAX_PDF_BYTES`, default 10 MB). Respuesta **201** con
  `{ "nombre", "tamano_bytes", "modificado_en" }`. Un nombre repetido **sobrescribe**.
  Errores: **400 `archivo_no_pdf`** (no es PDF), **413 `archivo_muy_grande`** (excede tamaño).
- **`GET /catalogos/contratos/{id}/adjuntos/{nombre}`** (`catalogos:leer`) — descarga/sirve el
  PDF (`application/pdf`, `Content-Disposition: inline`). El nombre se sanea.
- **`DELETE /catalogos/contratos/{id}/adjuntos/{nombre}`** (`catalogos:editar`) — elimina el
  PDF. Respuesta **204** (idempotente).
- Común: contrato inexistente → **404 `no_encontrado`**; almacenamiento no disponible →
  **502 `almacenamiento_no_disponible`**.

Ejemplo alta de contrato (sin `estado_contrato` ni `archivo_contrato_path`):
```json
{
  "anunciante_id": "3f...", "numero_contrato": "C-2026-001", "nombre_contrato": "Campaña anual",
  "fecha_inicio_contrato": "2026-01-01", "fecha_fin_contrato": "2026-12-31",
  "monto_contrato": "500000.00", "porcentaje_comision_contrato": "8.50"
}
```

### Catálogos de facturación/finanzas (F0-04) — EmpresaFacturadora · Vendedor · Categoria

Catálogos de apoyo (menú "Soporte") sobre el patrón CRUD estándar (escritura solo **admin**
en F0). `MetodoPago`/`CuentaContable` se difieren a F0-05 y `LayoutFactura` se omite (ADR-022).

**`/catalogos/empresas-facturadoras`** — campos: `empresa_facturadora_id`, `nombre_empresa`
(req.), `rfc_empresa` (req., **único**), `direccion_empresa` (texto largo, NVARCHAR(MAX)),
`activo`, `created_at`, `updated_at`.
- **RFC** formato MX 12-13 (reutiliza el regex de F0-01); único → RFC repetido = **409
  `conflicto`**. Búsqueda `?q` sobre nombre y RFC.

**`/catalogos/vendedores`** — campos: `vendedor_id`, `nombre_vendedor` (req.),
`email_vendedor`, **`porcentaje_comision_default` (PARÁMETRO SENSIBLE, string 0–100)**,
`activo`, `created_at`, `updated_at`.
- El % es sensible: **mismo mecanismo que F0-03** (permiso por campo → motivo requerido al
  cambiar → `LogCambioParametro`; alta audita con `anterior=null`). Viaja como string.
- **`GET /catalogos/vendedores/{id}/historial`** (`catalogos:leer`): historial de cambios
  del % (más reciente primero; alcance acotado, ADR-021).
- Búsqueda `?q` sobre nombre y correo.

**`/catalogos/categorias`** — campos: `categoria_id`, `nombre_categoria` (req., **único
case-insensitive**), `descripcion_categoria` (texto largo), `activo`, `created_at`,
`updated_at`. Nombre duplicado (ignorando mayúsculas/espacios) → **409 `conflicto`**.

**Usuario (modelo base, sin endpoints en F0-04):** la tabla `usuario` y su seed (1 admin
`dev.admin`) se crean para el RBAC; su **pantalla y endpoints** son de F5 (ADR-023).

### Constantes del sistema y cuenta contable (F0-05) — ConstantesSistema · CuentaContable

Último módulo de F0. Catálogos SAT/timbrador (menú **"Configuración"**) que F2 consume al
preparar el archivo plano del timbrador, y catálogo contable (menú **"Soporte"**). Escritura
solo **admin**; lectura para todas las áreas (para el operador son de solo lectura).

**`/catalogos/constantes`** — campos: `constante_sistema_id`, `grupo` (req., uno de los 9
grupos SAT), `clave` (req.), `descripcion` (req.), `valor` (opcional), `activo`, `created_at`,
`updated_at`. Grupos válidos: `TipoComprobante`, `Serie`, `RegimenFiscal`, `ClaveProdServ`,
`ClaveUnidad`, `UsoCFDI`, `FormaPago`, `MetodoPago`, `MonedaSAT` (grupo inválido → **422**).
- **Unicidad `(grupo, clave)`** case-insensitive: la misma clave puede repetirse entre grupos,
  pero no dentro de uno → duplicado en el mismo grupo = **409 `conflicto`**. `grupo`/`clave` no
  se editan (identidad natural): el `PUT` solo cambia `descripcion` y `valor`.
- **`GET /catalogos/constantes?grupo=<grupo>`**: además de `page/size/activo/q`, filtra por
  grupo. Búsqueda `?q` sobre clave, descripción y grupo.
- **`GET /catalogos/constantes/conteos?solo_activos=<bool>`** (`catalogos:leer`): conteo por
  grupo para las pills (devuelve los 9 grupos, con 0 si están vacíos).

**`POST /catalogos/constantes/importar`** (`catalogos:crear`, solo **admin**) — carga masiva
CSV. `multipart/form-data`: `archivo` (.csv), `commit` (bool, default `false`),
`modo_duplicados` (`actualizar` | `omitir` | `rechazar`, default `actualizar`).
- **Flujo dry-run → confirmar (stateless):** con `commit=false` devuelve el reporte de qué se
  haría **sin escribir**; el cliente re-sube el mismo archivo con `commit=true` para aplicar.
  El archivo se procesa en memoria y **no se persiste** en el servidor.
- **Columnas:** `grupo,clave,descripcion,valor,activo` (encabezado; UTF-8 con/ sin BOM;
  delimitador `,` o `;`). **Validación estructural** (columnas faltantes, vacío, no-UTF-8) →
  **400 `archivo_invalido`**; exceso de tamaño/filas (2 MB / 5 000 por defecto, configurables)
  → **413 `archivo_muy_grande`**; extensión ≠ `.csv` → **400 `archivo_invalido`**.
- **Import parcial:** las filas válidas entran; las inválidas se reportan con su motivo.
  Duplicados: `actualizar` (upsert, idempotente), `omitir` o `rechazar`; duplicado **dentro
  del archivo** → segunda fila rechazada. Las filas válidas se aplican en **una transacción**.
- **Reporte (200):** `{ commit, total_filas, creadas, actualizadas, omitidas, rechazadas,
  errores_estructura, filas: [ { numero, grupo, clave, estado, motivo } ] }` donde `estado` ∈
  `creada | actualizada | omitida | rechazada`.

**`/catalogos/cuentas-contables`** — campos: `cuenta_contable_id`, `codigo_cuenta` (req.,
**único case-insensitive**), `nombre_cuenta` (req.), `tipo_cuenta` (req., ENUM:
`ingreso | costo | gasto | activo | pasivo`; inválido → **422**), `activo`, `created_at`,
`updated_at`. Código duplicado → **409 `conflicto`**. Patrón CRUD estándar (sin carga CSV por
ahora; el helper de importación quedó reutilizable — ADR-025). Búsqueda `?q` sobre código y nombre.

## Órdenes (F1)

Permiso base `ordenes`. **Matriz RBAC** (propuesta §9, columna "Órdenes"): **Ventas**
captura (`ordenes:crear`/`editar`, implica `leer`); **Facturación, Tesorería, CxC, CxP,
Dirección/Finanzas** solo leen (`ordenes:leer`); **Nóminas** sin acceso (403 en
cualquier endpoint). **Admin es superusuario en TODOS los módulos** (desviación
explícita de la matriz de la propuesta, decisión del equipo — ver `app/core/security.py`,
`_nivel()`): tiene captura sobre Órdenes aunque la propuesta original solo le daba
lectura, además del canal de comisiones (ver abajo), que también puede usar Dirección.

Estas 4 entidades NO usan el patrón CRUD estándar de catálogos: no tienen `activo` (baja
lógica) — usan sus propias máquinas de estado (`estatus_orden`, `estatus`).

### Lectura (Tanda 3)

**`GET /ordenes/clientes`** (`ordenes:leer`) — lista paginada de `OrdenCliente`.
Filtros: `?q` (folio/número de orden), `?estatus_orden`, `?anunciante_id`, `?agencia_id`,
`?vendedor_principal_id`, `?contrato_id`. Campos: los 36 de la spec BD v2 + 3 extensiones
aditivas (comisiones snapshot ADR-029, campos de cierre ADR-034) — ver docstring de
`app/modules/ordenes/orden_cliente.py`. Montos/% como **string** (ADR-015).
- **`GET /ordenes/clientes/{id}`** — uno (404 si no existe).
- **`GET /ordenes/clientes/{id}/vobo`** — los 10 ítems fijos del checklist Vo.Bo.
  (ADR-033), con su `completado`/`usuario_id`/`fecha_completado`.
- **`GET /ordenes/clientes/{id}/historial-comisiones`** — historial de cambios a los % de
  comisión snapshot (más reciente primero; mismo mecanismo `LogCambioParametro` que los
  catálogos, `entidad="OrdenCliente"`).

**`GET /ordenes/estaciones`** (`ordenes:leer`) — lista paginada de `OrdenEstacion`.
Filtros: `?q`, `?orden_id` (OE de una OC — lo usa el panel de detalle de OrdenCliente),
`?estacion_id`, `?plaza_id`, `?anunciante_id`, `?estatus`. `estatus` es un ciclo de vida
**propio e independiente** del de la OC (ver ADR-030).
- **`GET /ordenes/estaciones/{id}`** — uno (404 si no existe).
- **`GET /ordenes/estaciones/{id}/dias`** — periodo de transmisión día a día
  (`OrdenEstacionDia`, ADR-030: `spots_solicitados`/`asignados`/`programados`), ordenado
  por `fecha_transmision`.

**`GET /ordenes/verificaciones`** (`ordenes:leer`) — lista **plana** (no solo anidada bajo
una OE) de `Verificacion`, una fila por día verificado — refleja la pantalla
"Verificaciones" del frontend. Filtros: `?orden_estacion_id` (JOIN vía
`orden_estacion_dia`), `?reconciliada`.
- **`GET /ordenes/verificaciones/{id}`** — una (404 si no existe).

**`GET /ordenes/incidencias`** (`ordenes:leer`) — lista **plana** de `Incidencia` —
refleja la pantalla "Incidencias" del frontend. Filtros: `?q` (descripción),
`?orden_estacion_id`, `?tipo_incidencia` (`faltante|excedente|cambio_horario|
cambio_fecha|spot_no_emitido`), `?resolucion` (`pendiente|aceptada|credito_cliente|
descuento_afiliado|sin_resolucion`).
- **`GET /ordenes/incidencias/{id}`** — una (404 si no existe).
- Sin alta manual ni edición de `resolucion` todavía (Tanda 5): el frontend no tiene
  pantalla para eso hoy (ver docstring de `incidencia.py`, ADR-031) — se difiere hasta
  que exista un consumidor real.

### Escritura (Tanda 5)

**`POST /ordenes/clientes`** (`ordenes:crear`) — alta de OrdenCliente. El servicio
calcula `anio_venta`/`mes_venta`/`total_dias_campania`/`subtotal`/`iva`/`total` y el
`folio_orden` (correlativo global `OC-{año}-####`, nunca se acepta del cliente); valida
que `contrato_id`/`marca_id` (si vienen) pertenezcan al `anunciante_id` de la orden.
Nace en `recibida`, con las 10 filas del checklist Vo.Bo. (`revision_checklist` opcional
en el body marca cuáles ya vienen `completado`). `dar_vobo: true` intenta la transición a
`capturada` en la MISMA alta (409 si el checklist no viene completo). Los 3 % de
comisión pueden capturarse aquí libremente (Ventas) — es alta, no auditoría con motivo.
- **`PUT /ordenes/clientes/{id}`** (`ordenes:editar`) — edición normal. **409** si la
  orden está en un estado congelado (`orden_cerrada`/`facturada`/`cobrada`). Recalcula
  totales si cambian `total_spots`/`precio_unitario` o las fechas de campaña. **No**
  acepta los 3 campos de comisión (`extra="forbid"` — 422 si se incluyen).
- **`PATCH /ordenes/clientes/{id}/comisiones`** (`ordenes:leer` — ver nota de permisos
  abajo) — ÚNICO canal para editar los 3 % de comisión DESPUÉS del alta (propuesta §9:
  *"el % de comisión de un vendedor puede editarse solo por Dirección, aunque Ventas
  tenga captura sobre el resto de la orden"*). **403** si el área no es Dirección/Admin;
  **400** si algún valor cambia sin `motivo_cambio`. Auditado en `LogCambioParametro`
  (`entidad="OrdenCliente"`).
- **`PATCH /ordenes/clientes/{id}/vobo/{item_clave}`** (`ordenes:editar`) — marca/
  desmarca UN ítem del checklist (`{"completado": bool}`). 422 si `item_clave` no es una
  de las 10 fijas.
- **`POST /ordenes/clientes/{id}/dar-vobo`** (`ordenes:editar`) — transición
  `recibida`→`capturada`. 409 si falta algún ítem o si la orden ya no está en `recibida`.
- **`POST /ordenes/clientes/{id}/cerrar`** (`ordenes:editar`) — transición a
  `orden_cerrada`. Body: `{odc_cerrada_ref, carta_conciliacion_ref}` (ambos opcionales).
  409 si la orden no está en `en_transmision`/`en_verificacion`, si no tiene ninguna
  OrdenEstacion, o si alguna no está `cerrada`. Rellena (backfill) cualquier % de
  comisión que siga `null` con el default vigente del catálogo (Vendedor/Agencia) —
  **no** se audita (completar un vacío, no una edición). Calcula
  `cierre_sin_odc_cerrada`/`cierre_sin_carta_conciliacion` de si los refs vinieron `null`.

**`POST /ordenes/estaciones`** (`ordenes:crear`) — asigna una estación a una
OrdenCliente. Hereda de la OC (`anunciante_id`, `vendedor_id`, `agencia_id`,
`categoria_id`, `producto`, `contrato_id`, `duracion_spot`) y de la `Estacion`
(`plaza_id`) — ninguno se acepta del cliente. Body: `orden_id`, `estacion_id`,
`precio_spot`, `observaciones_estacion`, `dias` (mín. 1: `fecha_transmision`,
`hora_inicio`, `hora_fin`, `spots_asignados`, `spots_solicitados` opcional). Calcula
`porcentaje_participacion_oir = (precio_unitario_OC − precio_spot) / precio_unitario_OC
× 100` (1 decimal) y los 7 importes/IVA/totales. **400** si `precio_spot` excede la
tarifa cliente de la OC, si el balance de spots (esta OE + hermanas) excede
`oc.total_spots`, o si algún día cae fuera del rango de campaña. Si la OC estaba en
`capturada`, la promueve a `en_transmision`.
- **`POST /ordenes/estaciones/{id}/programados`** (`ordenes:editar`) — 2.1→2.2. Body:
  `dias` (**solo excepciones** — los días no listados quedan `spots_programados =
  spots_asignados`), `reporte_programados_ref`. 409 si la OE no está en `asignada`.
- **`POST /ordenes/estaciones/{id}/reales`** (`ordenes:editar`) — 2.2→2.3. Body: `dias`
  (solo excepciones respecto al programado EFECTIVO), `testigos_url`,
  `testigos_ubicacion_alterna`, `notas_transmision`, `reporte_reales_ref`. Crea **una
  `Verificacion` por CADA día** de la OE (spec — no solo los listados); genera una
  `Incidencia` automática (`faltante`/`excedente`, `monto_ajuste = diferencia ×
  precio_spot`, `resolucion="pendiente"`) por cada día con diferencia. 409 si la OE no
  está en `en_transmision`. Si TODAS las OE de la OC quedan `cerrada`, la OC pasa de
  `en_transmision` a `en_verificacion` automáticamente.

**Adjuntos de Órdenes (ADR-042)** — antes "simulados" (solo se capturaba el nombre del
archivo). Un endpoint genérico para los 5 campos de documento
(`archivo_orden_original_path`, `odc_cerrada_ref`, `carta_conciliacion_ref`,
`reporte_programados_ref`, `reporte_reales_ref`):
- **`POST /ordenes/adjuntos?tipo={odc|cierre_odc|cierre_carta|reporte_reales|
  reporte_programados}`** (`ordenes:editar`, `multipart/form-data`, campo `archivo`) —
  valida extensión (lista blanca: `pdf, doc, docx, xls, xlsx, jpg, jpeg, png` — **sin**
  ejecutables/scripts), *magic bytes* acordes a la extensión, y tamaño máximo
  (`S3_MAX_PDF_BYTES`). Sube al mismo bucket que Contrato (`S3_BUCKET_CONTRATOS`) bajo un
  prefijo propio por `tipo`. Devuelve `{ref, nombre_archivo}` — `ref` es la clave real a
  guardar en el campo `_ref` correspondiente (vía el alta/edición normal de la orden, o el
  body de `/cerrar`, `/programados`, `/reales`, según el campo). **400**
  (`archivo_no_permitido`) si la extensión no está en la lista o el contenido no coincide
  con la extensión declarada; **413** si excede el tamaño.
- **`GET /ordenes/adjuntos?ref=...`** (`ordenes:leer`) — descarga/sirve el archivo a
  través del backend (bucket privado, nunca URL pública). **404** si `ref` no empieza con
  uno de los prefijos de Órdenes (guardarraíl: no sirve para leer `contratos/...`).

**PDFs de Orden interna (ADR-043)** — 3 documentos generados AL VUELO (no se guarda
ningún archivo; cada descarga refleja el estado más reciente), sin spec previa:
- **`GET /ordenes/estaciones/{id}/pdf/servicio`** (`ordenes:leer`) — "Orden de
  servicio": tarifa, periodo asignado (2.1), importe/IVA/total. Siempre disponible desde
  que la OE existe.
- **`GET /ordenes/estaciones/{id}/pdf/programados`** (`ordenes:leer`) — "Horarios
  programados": pedidos vs. confirmados por día (2.2). **400** (`error_dominio`) si la OE
  sigue en `asignada` (2.2 no capturado).
- **`GET /ordenes/estaciones/{id}/pdf/reales`** (`ordenes:leer`) — "Horarios reales de
  transmisión": lo verificado por día (2.3). **400** (`error_dominio`) si la OE no llegó
  a `cerrada` (2.3 no capturado).

Los 3 devuelven `application/pdf`. El nombre de empresa/domicilio del encabezado y pie
sale de `EmpresaFacturadora` (vía `OrdenCliente.empresa_facturadora_id`), no es un texto
fijo. El encabezado incluye los logos de OIR y Grupo Radio Centro, leídos de
`backend/app/assets/logos/` (sustituibles sin tocar código — ver ADR-044).

**Nota de permisos — `PATCH /clientes/{id}/comisiones`:** su permiso de ROUTER es
deliberadamente `ordenes:leer` (no `editar`): Dirección solo tiene lectura del módulo
"Órdenes" en la matriz, así que un permiso `editar` la dejaría fuera por completo. La
autorización REAL (solo Dirección o Admin) se valida DENTRO del servicio — separación
intencional entre "quién puede llegar al endpoint" (RBAC de módulo) y "quién puede
ejecutar la acción sensible" (chequeo de área específico de esta entidad).

**Errores posibles (todo el módulo):** 401 (sin auth), 403 (área sin permiso, o sin
autorización sensible en `/comisiones`), 404 (no encontrado), 409 (`transicion_invalida`
— máquina de estados), 422 (validación de payload/filtros), 400 (`error_dominio` —
reglas de negocio: balances, tarifas, pertenencia contrato/marca-anunciante).

## Facturación (F2)

Prefijo `/facturacion`. **Ojo con los permisos: NO son uniformes dentro del módulo.**
`_nivel()` de `core/security.py` resuelve el RBAC por MÓDULO, no por entidad, y la matriz
de F2 pide áreas de captura distintas por entidad — así que el módulo usa **dos claves de
permiso** (las mismas que el mapa del `CLAUDE.md` §4 predefine para F2; ver ADR-044):

| Sub-recurso | Permiso | Captura | Lectura |
|---|---|---|---|
| `/facturacion/clientes` | `facturacion:*` | Facturación | todas las demás áreas |
| `/facturacion/afiliados`, `/agencias`, `/costos` | `costos:*` | CxP | todas las demás áreas |

Admin no aparece en ninguna matriz: `_nivel()` le da WRITE en todo módulo (ADR-040).

### Lectura (Tanda 1)

Todas las listas devuelven el `Page<T>` estándar (`items`/`total`/`page`/`size`/`pages`) y
aceptan `page`, `size` y `q` (búsqueda de texto), más los filtros propios de cada una.

- **`GET /facturacion/clientes`** (`facturacion:leer`) — facturas al cliente. Filtros:
  `orden_id`, `anunciante_id`, `agencia_id`, `empresa_facturadora_id`,
  `estado_facturacion`. `q` busca en número de factura, razón social y folio fiscal.
- **`GET /facturacion/clientes/{id}`** (`facturacion:leer`) — 404 si no existe.
- **`GET /facturacion/afiliados`** (`costos:leer`) — facturas recibidas de afiliados.
  Filtros: `afiliado_id`, `estatus_factura_afiliado`. `q` busca en el folio de la emisora
  y la razón social.
- **`GET /facturacion/afiliados/{id}`** (`costos:leer`).
- **`GET /facturacion/afiliados/{id}/ordenes`** (`costos:leer`) — el reparto de esa
  factura entre las `OrdenEstacion` a las que se asignó (`FacturaAfiliadoOrden`). Devuelve
  una lista simple, no paginada: son pocas por factura.
- **`GET /facturacion/agencias`** (`costos:leer`) — facturas recibidas de agencias.
  Filtros: `agencia_id`, `orden_id`, `estatus_factura_agencia`. `q` busca en el folio
  externo.
- **`GET /facturacion/agencias/{id}`** (`costos:leer`).
- **`GET /facturacion/costos`** (`costos:leer`) — costos adicionales. Filtros:
  `tipo_costo` (`nomina`|`overhead`), `orden_id`, `periodo_contable` (`YYYY-MM`). `q`
  busca en la descripción.
- **`GET /facturacion/costos/{id}`** (`costos:leer`).

### Estados

`FacturaCliente.estado_facturacion`: `preparada → enviada_a_timbrado → timbrada →
entregada → cobrada`, con rama a `cancelada` desde los 4 primeros. El paso a `cobrada` lo
hará **F3**: F2 declara el estado pero no lo dispara.

`FacturaAfiliado.estatus_factura_afiliado` y `FacturaAgencia.estatus_factura_agencia`:
`recibida → en_revision → autorizada → pagada`. **`en_revision → autorizada` exige área
Dirección o Admin** (chequeo explícito en el servicio, no la matriz de módulo — mismo
patrón que `/ordenes/clientes/{id}/comisiones`): quien captura no autoriza.

`CostoAdicional` no tiene máquina de estados.

### Reglas de negocio del esquema

- **1:1 OC ↔ FacturaCliente** (`uq_factura_cliente_orden`): una `OrdenCliente` no puede
  tener dos facturas de cliente → 409 `conflicto`. `FacturaAgencia` **sí** es 1:N sobre la
  misma OC (no lleva esa restricción).
- **Una OE no se asigna dos veces a la misma factura de afiliado**
  (`uq_factura_afiliado_orden_factura_oe`); la misma OE sí puede repartirse entre facturas
  distintas (parcialidades de la emisora).
- **Montos**: `total_* = monto/subtotal + iva` con CHECK de igualdad envuelto en
  `ROUND(x, 2)` (ADR-039). En `FacturaCliente` además `iva_factura = subtotal * 0.16`,
  porque ahí el IVA es derivado; en las facturas de proveedor el IVA es **capturado**
  (la spec lo marca "Manual": pueden traer retenciones o exentos), así que no se les
  impone la tasa.
- **Dos desviaciones aditivas** respecto a la spec (catálogos que nunca se construyeron en
  F0): `layout_factura` es texto libre nullable (no FK a `LayoutFactura`) y
  `metodo_pago_clave` es texto sin FK (`MetodoPago` vive en `ConstantesSistema`, grupo
  `MetodoPago`; el frontend sugiere desde ahí, la base no valida la relación).

**Errores posibles (todo el módulo):** 401 (sin auth), 403 (área sin permiso, o sin
autorización sensible al autorizar una factura de proveedor), 404 (no encontrado), 409
(`transicion_invalida` / `conflicto`), 422 (validación de payload/filtros), 400
(`error_dominio` — reglas de negocio: OC no cerrada, OE no cerrada).

### Escritura y transiciones (Tanda 2)

#### FacturaCliente

- **`POST /facturacion/clientes`** (`facturacion:crear`) — alta. **400 `error_dominio`** si
  la `OrdenCliente` no está en `orden_cerrada`; **409 `conflicto`** si esa orden ya tiene
  factura (1:1). Hereda de la OC empresa/anunciante/agencia, razón social y RFC del
  receptor (anunciante o agencia según `facturacion_directa_cliente`), dirección, fechas de
  transmisión y `subtotal_factura`; calcula `iva_factura` y `total_factura`. Los campos
  derivados y calculados **no se aceptan del cliente** (`extra="forbid"` → 422).
- **`PUT /facturacion/clientes/{id}`** (`facturacion:editar`) — edición de los campos
  capturables. **409** una vez `timbrada`: el contenido ya salió al SAT.
- **`GET /facturacion/clientes/{id}/archivo-plano`** (`facturacion:leer`) — exporta la
  factura al **layout real del PAC (V40)** vía el puerto `TimbradoExportPort`. Texto plano
  con CRLF, codificado según `TIMBRADO_ENCODING` (hoy `cp1252`). **409** si la factura está
  cancelada.

  Devuelve la cabecera **`X-Campos-Faltantes`** (expuesta por CORS) con los campos que el
  PAC exige y que el modelo todavía no captura, separados por `;`. Vacía = archivo
  completo. Con contenido, el archivo se genera igual —para poder revisarlo— pero el PAC
  lo rechazaría, y la pantalla lo advierte. Ver ADR-048 y la ficha del módulo.
- **`POST /facturacion/clientes/{id}/enviar-a-timbrado`** (`facturacion:editar`).
- **`POST /facturacion/clientes/{id}/timbrar`** (`facturacion:editar`) — body:
  `folio_fiscal_sat`, `fecha_timbrado`, y opcionalmente `xml_path`/`pdf_path` (claves de
  almacenamiento devueltas por el endpoint de adjuntos). **Promueve la `OrdenCliente` a
  `facturada`** en la MISMA transacción (handoff con F1). Si la OC no admite esa
  transición, el 409 aborta también el timbrado: no queda factura timbrada con la orden
  desincronizada.
- **`POST /facturacion/clientes/{id}/entregar`** (`facturacion:editar`) — body opcional
  `fecha_entrega_factura` (default: hoy).
- **`POST /facturacion/clientes/{id}/cancelar`** (`facturacion:editar`) — desde los 4
  primeros estados. **Revierte el handoff** (ADR-047): si la `OrdenCliente` está en
  `facturada`, vuelve a `orden_cerrada` en la MISMA transacción y reaparece en la bandeja
  «Listas para facturar»; si está en `cobrada`, la cancelación se rechaza con **400
  `error_dominio`** (requeriría una nota de crédito, fuera del alcance de F2); en
  cualquier otro estado la orden no se toca. La factura cancelada **no se borra**: sigue
  listándose con estado `cancelada`, y la orden puede recibir una factura nueva porque el
  1:1 es un índice único FILTRADO que excluye las canceladas.

Todas las transiciones son **idempotentes** (repetir el destino actual devuelve 200 sin
efectos) y responden **409 `transicion_invalida`** ante un salto no permitido.

#### Bandeja "Listas para facturar"

- **`GET /facturacion/ordenes-por-facturar`** (`facturacion:leer`) — órdenes en
  `estatus_orden = orden_cerrada` que **todavía no tienen `FacturaCliente`**
  (`LEFT JOIN factura_cliente ... WHERE factura_id IS NULL`). Es el atajo operativo del
  día a día de Facturación. Acepta `page`, `size` y `q` (folio, número de orden y
  anunciante); el `total` de la respuesta es el contador que la pantalla pinta en el
  sidebar.

  Devuelve los NOMBRES ya resueltos (`anunciante`, `agencia`, `vendedor`) además de los
  datos de la orden, para que la vista no dispare tres consultas de catálogo por renglón.
  `agencia: null` significa trato directo con el anunciante.

  **Vive en F2, no en `ordenes`**, aunque la entidad principal sea `OrdenCliente`: la
  pregunta que responde es de Facturación y el criterio que la define (la ausencia de una
  fila en `factura_cliente`) es un concepto de F2. Solo LEE el modelo de F1; no toca su
  servicio ni su router. Cuelga de su propio prefijo y no de `/clientes/...` porque ahí
  `{item_id}` capturaría el segmento literal e intentaría leerlo como UUID (422).

  Las facturas **canceladas se ignoran** (el filtro va en la condición del `JOIN`), así que
  una orden cuya factura se canceló vuelve a aparecer aquí y puede facturarse de nuevo
  (ADR-047).

#### FacturaAfiliado / FacturaAgencia

- **`POST /facturacion/afiliados`**, **`POST /facturacion/agencias`** (`costos:crear`) —
  captura de CxP. `total_* = monto + iva` calculado. En afiliado, `razon_social_afiliada`
  se hereda del catálogo. En agencia, `comision_agencia = OrdenCliente.total * porcentaje
  / 100`, con el porcentaje sugerido del catálogo Agencia si no se captura, y persistido.
- **`PUT .../{id}`** (`costos:editar`) — **409** si ya está `autorizada` o `pagada`.
  Recalcula total y comisión si cambian sus insumos.
- **`POST .../{id}/estatus`** (`costos:editar`) — transiciones **operativas** de CxP:
  `recibida ↔ en_revision` y `autorizada → pagada`. Pedir `autorizada` por aquí da **403**
  y remite al canal dedicado.
- **`POST .../{id}/autorizar`** (`costos:leer`) — **canal dedicado** para
  `en_revision → autorizada`. El permiso del router es `leer` a propósito, porque Dirección
  **no** tiene captura sobre `costos`; la autorización real (solo **Dirección/Admin**) se
  valida dentro del servicio → **403** para cualquier otra área, incluida la CxP que
  capturó. Mismo diseño que `PATCH /ordenes/clientes/{id}/comisiones` en F1. Ver ADR-046.

#### FacturaAfiliadoOrden y CostoAdicional

- **`POST /facturacion/afiliados/{id}/ordenes`** (`costos:editar`) — reparte una porción
  del costo a una `OrdenEstacion`. **400** si la OE no está `cerrada`; **409** si esa OE ya
  está asignada a esta factura.
- **`POST /facturacion/costos`**, **`PUT /facturacion/costos/{id}`** (`costos:crear` /
  `costos:editar`). `periodo_contable` valida `YYYY-MM` con mes 01–12 en el schema
  (**422**): el CHECK de la tabla solo puede garantizar la forma, ver ADR-045. `orden_id`
  es opcional (NULL = costo general) y, si viene, debe existir (**400**).

#### Adjuntos de facturación

- **`POST /facturacion/adjuntos?tipo={cfdi_xml|cfdi_pdf|factura_afiliado|factura_agencia|
  respaldo_costo}`** (`costos:editar`) — sube el archivo y devuelve su `ref` (clave de
  almacenamiento). Lista blanca de extensiones + *magic bytes*; F2 acepta además **XML**
  (el CFDI), que F1 no acepta. La `ref` se guarda en la entidad por su propio endpoint.
- **`GET /facturacion/adjuntos?ref=...`** (`costos:leer`) — descarga. Solo sirve objetos
  de los prefijos de facturación: una `ref` de `contratos/` u `ordenes/` da 404.
