# Módulo F0-01 — Catálogos operativos (Plaza · Afiliado · Estación) · Fase: F0

> Núcleo operativo de la transmisión. Tres entidades, cada una con su propia pantalla
> desde ADR-094 (antes Estación vivía anidada en Afiliado con plaza heredada — ver nota
> abajo). Desde ADR-096, la plaza es propiedad EXCLUSIVA de la Estación — el Afiliado ya
> no tiene `plaza_id`. Referencias: spec BD v2 y `Fase_0_-_Catalogos.html` (grupos
> "plaza", "afiliado", "estación").

## Propósito

Gestionar dónde y a través de quién se transmite: plazas geográficas, afiliados
(empresas que operan estaciones) y estaciones. Es prerrequisito de Tarifas (F0-02) y de
Órdenes (F1).

## Entidades (spec BD v2)

> **Estado: IMPLEMENTADO** (backend + migración aplicada a RDS + frontend). Migración
> Alembic `7300e6f940a3` (Plaza/Afiliado/Estación) + `3d82c1b995f2` (`estacion.siglas` +
> tabla `contacto_afiliado`, ADR-094) + `a12fc26a6504` (elimina `afiliado.plaza_id`,
> ADR-096). Ver `docs/API-CONTRACT.md` para los endpoints.

> **Nota de unificación (E-3):** aunque la spec lista `created_at` como único timestamp de
> Plaza y Estación, se agregó `updated_at` a **las tres** entidades para cumplir la
> convención "updated_at en toda entidad" de `CLAUDE.md §6`. Desviación consciente y
> uniforme respecto a la enumeración de la spec.

### Plaza
`plaza_id` (PK, `UNIQUEIDENTIFIER`), `nombre_plaza` (NOT NULL), `estado`, `activo`,
`created_at`, `updated_at`.

### Afiliado (sin `plaza_id` — ADR-096)
`afiliado_id` (PK), `nombre_afiliado` (NOT NULL), `razon_social_afiliado` (NOT NULL),
`rfc_afiliado` (NOT NULL, **único**), `contacto_nombre`, `contacto_email`,
`contacto_telefono`, `activo`, `created_at`, `updated_at`. No accede al sistema.
- **Sin plaza propia (ADR-096, petición del usuario):** el Afiliado tenía `plaza_id`
  (FK NOT NULL, decisión histórica E-1) hasta 2026-09-21. Se eliminó por completo — la
  plaza es una propiedad de la **Estación**, no del Afiliado, que puede operar estaciones
  en varias plazas distintas. Ver Estación abajo y ADR-096 en `docs/arquitectura.md`.
- **RFC:** se valida el formato oficial mexicano de **12-13 caracteres** (12 = persona
  moral, que es el caso típico de un afiliado; 13 = física), no exactamente 13. Se
  normaliza a mayúsculas. La columna es `NVARCHAR(13)` con índice UNIQUE.
- `contacto_nombre`/`contacto_email`/`contacto_telefono` quedan como **LEGADO** desde
  ADR-094: ya no se capturan en el formulario, se muestran de solo lectura en el
  detalle solo si una fila vieja los trae. El reemplazo es `ContactoAfiliado` (abajo).

### ContactoAfiliado (entidad NUEVA, fuera de la spec BD v2 — ADR-094)
`contacto_afiliado_id` (PK), `afiliado_id` (FK NOT NULL), `nombre_contacto` (NOT NULL),
`puesto_contacto`, `telefono_contacto`, `email_contacto`, `activo`, `created_at`,
`updated_at`.
- **Sin pantalla propia:** anidada dentro de Afiliado (sub-lista en alta/edición/detalle:
  agregar/editar/desactivar ahí mismo) — mismo patrón dual-modo que
  `ContactoAnunciante`/`ContactoAgencia` (ADR-091/092, ver F0-03): en alta se capturan en
  memoria y se crean junto con el afiliado; en edición/detalle pegan directo al backend.

### Estacion (1 campo de la spec omitido — ver nota; `siglas` nuevo — ADR-094)
`estacion_id` (PK), `afiliado_id` (FK NOT NULL), `plaza_id` (FK NOT NULL, **captura libre
e independiente** desde ADR-094 — ver nota abajo), `nombre_estacion` (NOT NULL), `siglas`
(NVARCHAR 20, opcional, **campo nuevo**), `frecuencia`, `tipo_senal` (ENUM `fm│am│tv`,
como `VARCHAR` + CHECK `ck_estacion_tipo_senal`), `activo`, `created_at`, `updated_at`.
- **Campo omitido:** `venta_directa_carmen_aristegui_cdmx` (BIT) de la spec se **omite
  deliberadamente** (decisión del equipo). Registrado como desviación en
  `docs/arquitectura.md` (ADR-006) para que no se reincorpore por error.
- El detalle/lista de Estación muestra `afiliado_nombre` y `plaza_nombre` como
  **derivados** (resueltos en batch por el backend, sin N+1).

## Regla de plaza de la estación — selección libre e independiente (ADR-094, revierte ADR-005)

Hasta 2026-09-20 la estación heredaba la plaza de su afiliado (Opción A, ADR-005). Al
separar Estaciones en su propia pantalla, el usuario confirmó que Plaza y Afiliado son
selects **independientes**: un afiliado y sus estaciones pueden estar en plazas distintas
(caso real: estación reasignada, cobertura cruzada). Reglas vigentes:
- `plaza_id` es **obligatorio** en alta y capturable en edición, validado contra el
  catálogo de Plazas (409/404 si no existe).
- El servicio YA NO deriva `plaza_id` desde `Afiliado.plaza_id`; lo que envía el
  formulario es lo que se guarda.
- Ver ADR-094 en `docs/arquitectura.md` para el detalle completo de la decisión y las dos
  preguntas de confirmación que se hicieron antes de implementarla.

## Estados y transiciones
- Estos catálogos solo manejan `activo` (alta lógica/baja lógica). Sin máquina de estados.

## Pantallas (implementadas, patrón lista + detalle)
- **Plaza** (`plaza`), **Afiliados** (`afiliado`) y **Estaciones** (`estacion`) son TRES
  entradas independientes del grupo "Operación" del explorador desde ADR-094 (antes,
  Estación vivía anidada en el detalle de Afiliado, sin pantalla propia).
- Las tres con filtros Activos/Inactivos/Todos, búsqueda y paginación por página.
- **Columnas de lista (1:1 con la pantalla aprobada):**
  - Plazas: Plaza · Estado · Estaciones · Estatus.
  - Afiliados: Afiliado (nombre + razón social) · RFC · Estaciones · Estatus. (Ya sin
    columna de plaza — ADR-096.)
  - Estaciones: Estación · Siglas · Tipo · Frecuencia · Plaza · Afiliado · Estatus.
  - `Estaciones` (conteo) en Plaza/Afiliado, y `afiliado_nombre`/`plaza_nombre` en
    Estación, son **datos derivados** que el backend calcula por lote (sin N+1). El
    conteo incluye estaciones inactivas.
- Formularios con React Hook Form + Zod (validaciones espejo del backend).
- **Estación (pantalla propia, ADR-094):** alta/edición captura Nombre, Siglas
  (opcional), Frecuencia, Tipo de señal (FM/AM/TV) y DOS selects **independientes**:
  Plaza y Afiliado (este último filtrado a `activo:true`, con la leyenda "Solo se listan
  afiliados activos.").
- **Afiliado — Contactos (ADR-094):** sección anidada `ContactosSection`, mismo
  componente/patrón dual-modo de ADR-091/092 (F0-03) — en alta se capturan en memoria y
  se crean junto con el afiliado; en edición/detalle, en vivo contra el backend
  (agregar/editar/desactivar). El detalle del afiliado conserva una sección "Estaciones"
  de **solo lectura** (sin alta/edición/baja) con la nota "Alta, edición y baja de
  estaciones: pantalla 'Estaciones'."
- Baja con dependientes: cuando el backend responde 409, la UI muestra un diálogo de
  confirmación y reintenta con `forzar`.
- Botones `+ Nueva plaza`, `+ Nuevo afiliado`, `+ Nueva estación`, `Editar`,
  `Activar/Desactivar`. Acciones de escritura visibles solo para admin (el backend valida).

## Roles / permisos
- **Captura: solo Admin (IT)** por ahora. En una **versión posterior**, Ventas también
  podrá capturar y editar afiliados/estaciones (cuando se habilite, ajustar RBAC).
- Lectura: demás áreas.

## Reglas de negocio clave (implementadas en la capa de servicio)
- `rfc_afiliado`: formato RFC MX de 12-13 caracteres (ver nota arriba), único (índice
  UNIQUE + verificación en servicio → 409 `conflicto` con mensaje claro).
- Estación obliga `afiliado_id` y `plaza_id`, cada uno validado por separado contra su
  catálogo (`_verificar_afiliado`/`_verificar_plaza`, → 404 si no existe). Desde ADR-094
  son independientes; desde ADR-096 el Afiliado ni siquiera tiene un `plaza_id` del que
  derivar nada.
- Baja lógica con confirmación (E-2, ajustada por ADR-096): **no se puede desactivar**
  - una **plaza** con estaciones activas (antes también con afiliados activos — ya no
    aplica, el Afiliado no referencia una plaza), ni
  - un **afiliado** con estaciones activas,
  sin confirmar. El servicio responde 409 `dependencias_activas` (con el conteo en
  `detalles`) y el cliente reintenta con `forzar=true`. Mecanismo aditivo en la base
  (`CambioEstadoIn.forzar`, hook `_pre_desactivar`). La estación y `ContactoAfiliado` no
  tienen dependientes, su baja es directa.

## Integraciones
- Ninguna.

## Dependencias
- F0-00 (fundamentos). Plaza antes que Afiliado antes que Estación.

## Pendientes / dudas
- (Resuelto) Plaza de la estación → Opción A: hereda del afiliado (ADR-005),
  **revertida** en 2026-09-20: selección libre e independiente (ADR-094).
- (Resuelto) Campo `venta_directa_carmen_aristegui_cdmx` → omitido (ADR-006).
- (Resuelto) Desactivar con dependientes → advertir antes de proceder (E-2; alcance de
  Plaza ajustado por ADR-096 a solo estaciones activas — ya no cuenta afiliados).
- (Resuelto) `afiliado.plaza_id` → NOT NULL (E-1) hasta 2026-09-21; **eliminado por
  completo** (ADR-096, petición del usuario): la plaza es propiedad de la Estación, no
  del Afiliado.
- (Resuelto) `updated_at` → agregado a las tres entidades (E-3, ver nota arriba).
- (Resuelto) Estación sin pantalla propia → pantalla independiente desde ADR-094.
- (Resuelto) Afiliado con un solo contacto plano → `ContactoAfiliado` (varios, ADR-094).
- (Aclaración) `rfc_afiliado` → 12-13 caracteres (no exactamente 13): 12 para personas
  morales, que es el caso de los afiliados. Confirmar con el equipo si algún afiliado
  pudiera ser persona física (13).
