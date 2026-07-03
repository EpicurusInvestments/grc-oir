# Plan — F0-01 Catálogos operativos (Plaza · Afiliado · Estación)

> Documento de **revisión** (no es documentación viva ni se commitea). Sistema GRC-OIR.
> Reutiliza la base de F0-00 ya mergeada a `main`. **No se escribe código de negocio
> hasta aprobación de este plan.**

## Micro-paso ya aplicado (config, no negocio)

- `.env.example` → `DB_USER=TESTGRCOIRDB` (antes `TESTGRCOIR`). `DB_PASSWORD` sigue `[[POR LLENAR]]`.

---

## Cómo lo leí (base F0-00 que reutilizo tal cual)

- **Back:** `BaseRepository` (list/get/create/update/set_activo, filtro `activo`+`q`),
  `BaseService` (devuelve siempre `XxxRead`, hooks `_pre_create`/`_pre_update`),
  `build_crud_router` (5 endpoints con `requiere_permiso` cableado), matriz RBAC
  `catalogos` (Admin escribe, resto lee — ya es exactamente lo que pide F0-01).
- **Front:** `createCatalogApi` + `useCatalog` + `catalogRegistry` (ya trae entradas
  `plaza` y `afiliado` en grupo "Operación", sin `render`), y los componentes compartidos
  `ExplorerLayout`/`ListDetailLayout`/`CatalogToolbar`/`StatusBadge`/`FieldTag`/`Paginator`/`ConfirmDialog`
  con `theme.css`.
- **Pantalla aprobada:** confirma que **Estación NO es una entrada de sidebar propia**: se
  administra **anidada dentro del detalle de "Afiliados y estaciones"** (lista de estaciones
  + botón "+ Agregar", form inline). Plaza es entrada aparte. Se respeta ese patrón.

---

## A) Archivos a crear/tocar

### Backend

| Archivo | Acción | Por qué |
|---|---|---|
| `backend/app/modules/catalogos/plaza.py` | crear | Modelo `Plaza` + schemas (Create/Update/Read) + `PlazaService(BaseService)` con validación de baja con dependientes + factory `get_plaza_service` + `build_crud_router`. |
| `backend/app/modules/catalogos/afiliado.py` | crear | Modelo `Afiliado` + schemas + `AfiliadoRepository` (add `get_by_rfc`) + `AfiliadoService` (unicidad RFC en `_pre_create`/`_pre_update`, baja con estaciones activas) + router. |
| `backend/app/modules/catalogos/estacion.py` | crear | Modelo `Estacion` + enum `TipoSenal` + schemas (Create/Update **sin** `plaza_id`) + `EstacionService` (herencia de plaza desde afiliado) + router CRUD **+ 1 ruta adicional** `GET /estaciones/afiliado/{afiliado_id}`. |
| `backend/app/modules/catalogos/router.py` | tocar | `include_router` de los 3 sub-routers (hoy está vacío con el TODO). |
| `backend/migrations/env.py` | tocar | Importar los 3 módulos para que `Base.metadata` conozca las tablas (el TODO(F0-01+) ya está señalado). |
| `backend/migrations/versions/<ts>_f0_01_operativos.py` | crear | 1ª migración real (autogenerada + revisada a mano). |
| `backend/app/tests/test_f0_01_operativos.py` | crear | Pruebas SQLite de reglas (ver D). |
| `backend/app/tests/conftest.py` | tocar (mínimo) | Añadir fixture/app que monte los routers reales sobre SQLite (sin tocar lo del demo). |

### Extensiones **mínimas y aditivas** a la base F0-00 (señaladas para OK; no se reescribe la base)

1. `catalogos/schemas.py` → `CambioEstadoIn` gana `forzar: bool = False` (compatible hacia atrás).
2. `catalogos/base_service.py` → `cambiar_estado(..., forzar: bool = False)` + nuevo hook vacío `_pre_desactivar(obj, forzar, usuario)` que las subclases sobreescriben.
3. `catalogos/crud_router.py` → el endpoint de estado pasa `payload.forzar` al service (1 línea).
4. `core/errors.py` → nueva `DependenciasActivasError` (HTTP 409, `codigo="dependencias_activas"`, `detalles` con el conteo) para la baja bloqueada.

> Ninguna de estas rompe el demo ni las pruebas existentes; son extensiones necesarias
> para la regla de "baja con dependientes". Si se prefiere resolver la baja de otra forma
> (p.ej. endpoint aparte), se ajusta.

### Frontend

| Archivo | Acción | Por qué |
|---|---|---|
| `frontend/src/modules/catalogos/plaza/{types,api,hooks}.ts` | crear | Tipos `Plaza*`, `createCatalogApi("plazas")`, `useCatalog`. |
| `frontend/src/modules/catalogos/plaza/pages/PlazaCatalogPage.tsx` + `components/` | crear | Lista+detalle+form (RHF+Zod) de Plaza. |
| `frontend/src/modules/catalogos/afiliado/{types,api,hooks}.ts` | crear | Tipos `Afiliado*` **y** `Estacion*` (estación vive dentro de afiliado); api de afiliados + estaciones + `listPorAfiliado`. |
| `frontend/src/modules/catalogos/afiliado/pages/AfiliadoCatalogPage.tsx` + `components/` | crear | Lista de afiliados + detalle con **estaciones anidadas** (lista + form inline con autocompletado de plaza/razón social). |
| `frontend/src/modules/catalogos/catalogRegistry.ts` | tocar | Añadir `render` a las entradas `plaza` y `afiliado` (estructura intacta). |

**Decisión de UI:** se sigue el patrón plano de `theme.css` de F0-00 y la pantalla aprobada
(tabla + panel), con **RHF+Zod** en formularios (como pide `frontend/CLAUDE.md`). PrimeReact
está instalado pero F0-00 no lo usó en estos componentes; se mantiene consistencia. Si se
quiere migrar la tabla a PrimeReact DataTable, se hace como tarea aparte.

---

## B) Contenido de la 1ª migración (para revisión ANTES de aplicar)

Tablas SQL Server (tipos: `UNIQUEIDENTIFIER` vía `sqlalchemy.Uuid` → nativo en mssql;
`NVARCHAR`; `BIT`; `DATETIME2`). PK generada en app con `uuid4`. Baja lógica (nunca DELETE).

### `plaza`
- `plaza_id` UNIQUEIDENTIFIER PK
- `nombre_plaza` NVARCHAR(120) NOT NULL
- `estado` NVARCHAR(120) NULL
- `activo` BIT NOT NULL (default 1)
- `created_at` DATETIME2 NOT NULL
- Índice: `ix_plaza_nombre_plaza` (búsqueda)

### `afiliado`
- `afiliado_id` UNIQUEIDENTIFIER PK
- `nombre_afiliado` NVARCHAR(160) NOT NULL
- `razon_social_afiliado` NVARCHAR(200) NOT NULL
- `rfc_afiliado` NVARCHAR(13) NOT NULL
- `plaza_id` UNIQUEIDENTIFIER **NOT NULL** FK→`plaza.plaza_id`  ⟵ *ver decisión E-1*
- `contacto_nombre` NVARCHAR(160) NULL · `contacto_email` NVARCHAR(160) NULL · `contacto_telefono` NVARCHAR(40) NULL
- `activo` BIT NOT NULL (default 1)
- `created_at` DATETIME2 NOT NULL · `updated_at` DATETIME2 NULL
- Índices: `ux_afiliado_rfc` (UNIQUE), `ix_afiliado_plaza_id` (FK), `ix_afiliado_nombre_afiliado` (búsqueda)

### `estacion`
- `estacion_id` UNIQUEIDENTIFIER PK
- `afiliado_id` UNIQUEIDENTIFIER NOT NULL FK→`afiliado.afiliado_id`
- `plaza_id` UNIQUEIDENTIFIER NOT NULL FK→`plaza.plaza_id` (derivada del afiliado en servicio)
- `nombre_estacion` NVARCHAR(120) NOT NULL
- `frecuencia` NVARCHAR(40) NULL
- `tipo_senal` NVARCHAR(4) NOT NULL, `CONSTRAINT ck_estacion_tipo_senal CHECK (tipo_senal IN ('fm','am','tv'))`
- `activo` BIT NOT NULL (default 1)
- `created_at` DATETIME2 NOT NULL
- Índices: `ix_estacion_afiliado_id`, `ix_estacion_plaza_id`, `ix_estacion_nombre_estacion`
- **Omitido:** `venta_directa_carmen_aristegui_cdmx` (ADR-006).

**Proceso:** se genera con `alembic revision --autogenerate`, se **revisa/edita a mano**
(nombres explícitos de CHECK/índices, orden de creación plaza→afiliado→estacion), se
**muestra** para revisión, y solo entonces se corre `alembic upgrade head` contra GRC-OIR.

---

## C) Reglas de negocio — capa y mecanismo

Todo en la **capa service** (routers y componentes sin lógica):

1. **Herencia de plaza (ADR-005)** — `EstacionService._pre_create` y `_pre_update`: carga
   el `Afiliado` (via repo inyectado); si no existe → `NotFoundError`. Fuerza
   `payload["plaza_id"] = afiliado.plaza_id` **descartando** cualquier `plaza_id` del
   cliente. Los schemas `EstacionCreate/Update` **no exponen** `plaza_id`, así que nunca
   llega del front.

2. **Unicidad + formato RFC** — `AfiliadoCreate/Update` validan formato con Zod (front) y
   regex Pydantic (back, 13 chars, patrón RFC MX). `AfiliadoService._pre_create/_pre_update`
   consultan `AfiliadoRepository.get_by_rfc(rfc, excluir_id=...)`; si choca → `DomainError`
   409 (`codigo="rfc_duplicado"`) con mensaje claro. Respaldo duro: índice UNIQUE
   `ux_afiliado_rfc`.

3. **Baja con dependientes** — `PlazaService._pre_desactivar` y
   `AfiliadoService._pre_desactivar`: al desactivar (`activo=False`) cuentan estaciones
   **activas** dependientes (Plaza→por `plaza_id`; Afiliado→por `afiliado_id`). Si hay y
   `forzar=False` → `DependenciasActivasError` 409 con `detalles={"estaciones_activas": n}`.
   El front muestra `ConfirmDialog` y reintenta con `forzar=true`. (Activar nunca se
   bloquea.)

Hooks de core disponibles pero **no requeridos** aquí: estos catálogos no tienen
parámetros sensibles → sin `field_permissions`/`audit` (esos entran en F0-03). RBAC ya
cubierto por `requiere_permiso("catalogos:...")`.

---

## D) Verificación (RDS) y pruebas (SQLite vs RDS)

### Conexión + migración (RDS, esta sesión)
1. `GET /health/db` → `reachable` (valida `.env` con `TESTGRCOIRDB`).
2. `alembic revision --autogenerate` → se revisa el archivo → se muestra.
3. Tras OK: `alembic upgrade head` contra GRC-OIR.
4. Smoke manual: verificar que existen las 3 tablas + el CHECK (consulta
   `INFORMATION_SCHEMA`), y opcionalmente crear 1 plaza vía `/docs` para confirmar el
   ciclo (se consulta antes de escribir en RDS).

### Pruebas automáticas SQLite (mecánica y reglas, sin red — `sqlalchemy.Uuid` y `CHECK` funcionan en SQLite)
- **Plaza:** CRUD + paginación + filtro activo + baja lógica (heredado del base, más un caso propio).
- **Afiliado:** RFC duplicado → 409; RFC mal formado → 422; baja bloqueada con estación activa; baja con `forzar=true` procede.
- **Estación:** `plaza_id` = plaza del afiliado aunque el cliente mande otra; `tipo_senal` inválido → rechazado (enum/CHECK); `GET /estaciones/afiliado/{id}` filtra bien.

### Requiere RDS (no en SQLite)
Que el DDL real aplique con tipos nativos (`UNIQUEIDENTIFIER`, `DATETIME2`, CHECK con
nombre) y la conectividad ODBC. Se valida con `alembic upgrade` + smoke, no con pytest.

---

## E) Dudas / decisiones abiertas

1. **`afiliado.plaza_id` NOT NULL** — El prompt lo lista como "FK" sin `NOT NULL`, pero
   ADR-005 (la estación hereda la plaza del afiliado, y `estacion.plaza_id` es NOT NULL)
   **exige** que el afiliado siempre tenga plaza. Propuesta: **NOT NULL**. ¿De acuerdo?
   (Si se deja nullable, la herencia necesitaría un fallback y rompería el invariante.)

2. **Alcance del bloqueo de baja de Plaza** — La ficha dice "estaciones activas
   dependientes". Con Opción A, una plaza podría tener un **afiliado activo sin
   estaciones**. ¿Bloqueo la baja de Plaza solo por **estaciones activas** (literal de la
   ficha) o también por **afiliados activos**? Propuesta: **estaciones activas** (fiel a la
   ficha) y se deja anotado.

3. **`updated_at`** — Se sigue la enumeración explícita del prompt: Afiliado **sí**,
   Plaza/Estación **no**. Esto se desvía del "updated_at en toda entidad" de CLAUDE.md §6.
   Se confirma que manda la enumeración del prompt (spec) sobre la convención general.
   ¿OK? (Si se prefiere uniformidad, se agrega `updated_at` a las 3 y se registra como
   nota.)

4. **UI: plano vs PrimeReact** — Propuesta: patrón plano de `theme.css` de F0-00
   (consistente con lo ya mergeado y la pantalla aprobada). ¿OK, o se quiere DataTable de
   PrimeReact ya?

---

## Tandas propuestas

- **Tanda 1 — Backend + migración:** modelos, schemas, servicios, routers, extensiones
  base, tests SQLite verdes. Se genera la migración, se **muestra**, se revisa, y se corre
  `alembic upgrade` contra RDS. **Pausa para validar.**
- **Tanda 2 — Frontend:** tipos/api/hooks/páginas de Plaza y Afiliado(+Estación anidada),
  registro en `catalogRegistry`.
- **Cierre:** `documentacion-proyecto` (ficha f0-01 a estado real, `API-CONTRACT` con
  endpoints de plaza/afiliado/estacion, ADR si surge algo nuevo) + `revision-modulo`.
  Commits y PR los hace el equipo.
</content>
</invoke>
