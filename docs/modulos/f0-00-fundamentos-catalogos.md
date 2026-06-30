# Módulo F0-00 — Fundamentos de catálogos · Fase: F0

> Módulo transversal: la base técnica que comparten TODOS los catálogos de F0. No tiene
> una entidad de negocio propia; entrega la infraestructura reutilizable para que los
> módulos siguientes (F0-01..F0-05) solo agreguen su entidad y sus reglas.
> Referencia visual: `docs/referencias/pantallas/Fase_0_-_Catalogos.html`.

## Propósito

Construir una sola vez el "explorador de catálogos" y el CRUD genérico, de modo que cada
catálogo nuevo se reduzca a definir su entidad, su formulario y sus reglas.

## Qué entrega

### Frontend (`src/modules/catalogos/` + `src/shared/ui/`)
- **Layout del explorador**: sidebar izquierdo con la lista de catálogos (con contador
  por catálogo, clase `side-count`) y área principal a la derecha.
- **Patrón lista + detalle**: `split` con `list-pane` (tabla) y `detail-pane` (~480px).
  Al seleccionar un renglón se abre su detalle/edición sin perder el contexto.
- **Toolbar** reutilizable: búsqueda (`search`), filtros rápidos en pills
  (Todos / Activos / Inactivos y variantes), contador de resultados (`tb-count`).
- **Paginación por página** en todas las listas (no scroll infinito). El control de
  paginación es un componente compartido; el backend devuelve total + página.
- **Componentes compartidos**: badges de estado (`b-green`/`b-gray` → Activo/Inactivo),
  tags de campo («Catálogo», «Audit log», «Calc»), botón `+ Nuevo…`, modal de
  confirmación para cambio de estado.
- Tema con **color por fase** (F0 morado) y tipografía IBM Plex Sans/Mono.

### Backend (`backend/app/modules/catalogos/` + `app/core/`)
- **CRUD genérico** reutilizable (clase base de repository/service) para catálogos
  simples: list con filtros (activo, búsqueda) **y paginación por página**, get, create,
  update, **cambio de estado activo/inactivo** (los catálogos usan baja lógica `activo`,
  no borrado físico).
- **RBAC de catálogos**: por ahora **solo Admin (IT)** puede crear/editar/cambiar estado
  en todos los catálogos de F0; las demás áreas solo lectura. (Decisión confirmada;
  revisable cuando Ventas entre a afiliados/estaciones — ver F0-01.)
- Hooks transversales ya disponibles para los módulos siguientes: `requiere_permiso`,
  `field_permissions.verificar`, `audit.log_cambio_parametro` (en `app/core/`).

## Reglas y convenciones

- Todos los catálogos: PK `UNIQUEIDENTIFIER`, `activo BIT`, `created_at`, `updated_at`.
- Baja lógica vía `activo` (botón "Activar/Desactivar"), nunca DELETE físico.
- Origen de campos según la spec; los catálogos con valor sugerido a órdenes usan el
  patrón **Cat/Manual** (sugerir del catálogo, permitir manual, ofrecer alta).
- Búsqueda, filtros y paginación se resuelven en backend (no traer todo y filtrar en el front).

## Pantallas

- Una sola pantalla contenedora (explorador) que hospeda a todos los catálogos.
  Cada módulo posterior registra su catálogo en el sidebar.

## Roles / permisos (matriz RBAC)

- **Captura/edición: solo Admin (IT)** (confirmado, aplica a todos los catálogos de F0).
- Lectura: Ventas, Facturación, Tesorería, CxC, CxP, Dirección/Finanzas.

## Integraciones
- Ninguna en este módulo.

## Dependencias
- Ninguna (es la base). Debe completarse antes que F0-01..F0-05.

## Estado de implementación

### Backend — ENTREGADO (tanda 1)
Inicializado el proyecto FastAPI con **uv** (Python 3.12; `pyproject.toml`, `uv.lock`) y
la base reutilizable:
- `app/core/`: `config` (lee `.env`; arma la URL ODBC con el guion de `GRC-OIR`),
  `db` (engine **perezoso** + sesión síncrona pyodbc), `errors` (sobre uniforme),
  `security` (matriz RBAC como datos + `requiere_permiso` + auth dev-only fail-closed),
  `field_permissions.verificar` y `audit.log_cambio_parametro` (hooks con firma estable
  para F0-03/F5).
- `app/modules/catalogos/`: `BaseRepository`, `BaseService`, `schemas` (`Page`,
  `ListParams`, `CatalogoReadBase`, `CambioEstadoIn`) y `build_crud_router` (factory de
  los 5 endpoints estándar). Router agregador vacío (F0-01 le cuelga cada catálogo).
- `app/main.py`: `/api/v1`, OpenAPI activo (`/docs`), `/health` y `/health/db`.
- **Alembic** configurado (`alembic.ini`, `migrations/env.py` cableado a `Base.metadata`)
  **sin revisiones** todavía (no hay tablas; la primera migración es de F0-01).
- **Pruebas:** 12 pasando (SQLite en memoria con entidad de juguete): CRUD genérico,
  paginación, filtro `activo`, búsqueda, baja lógica, RBAC y fail-closed. `ruff` y `mypy`
  (strict) limpios.

Decisiones registradas: **ADR-007** (CRUD genérico + registry), **ADR-008** (auth
dev-only fail-closed), **ADR-009** (pyodbc síncrono + engine perezoso).

> Nota de verificación: localmente `GET /health/db` no conecta porque (a) este host tiene
> ODBC Driver 17, no el 18 (la imagen Docker sí instala el 18), y (b) la contraseña de
> prueba de RDS parece rotada (login 18456). La cadena de conexión y el endpoint son
> correctos: se alcanzó el servidor SQL. Pendiente del equipo: confirmar credencial dev.

### Frontend — ENTREGADO (tanda 2)
Inicializado **Vite + React + TypeScript (strict)** con PrimeReact, TanStack Query y
React Hook Form + Zod (deps listas para los formularios de F0-01+).
- `src/shared/ui/`: patrón de pantalla reutilizable — `theme.css` (tokens del HTML
  aprobado, **color por fase F0 morado**, IBM Plex Sans/Mono, `--detail-width: 420px`),
  `ExplorerLayout` (header + sidebar con contador `side-count` + área principal),
  `ListDetailLayout` (split lista + detalle ~420px) + `DetailEmpty`, `CatalogToolbar`
  (búsqueda + filtros en pills + contador), `StatusBadge` (Activo/Inactivo), `FieldTag`
  (Catálogo/Heredado/Calculado/Derivado/Audit log/Timbrado), `Paginator` (por página,
  envuelve PrimeReact) y `ConfirmDialog` (cambio de estado).
- `src/shared/lib/`: `apiClient` (axios contra `VITE_API_URL`, headers de auth dev en
  development, normaliza el sobre de error), `createCatalogApi` (CRUD tipado contra
  `/catalogos/<recurso>`, gemelo de `build_crud_router`), `useCatalog` (queries/mutations
  TanStack con invalidación). `shared/types.ts`: `Page<T>`, `ListParams`, etc.
- `src/modules/catalogos/`: `catalogRegistry` (grupos y entradas del sidebar según la
  pantalla aprobada; cada catálogo de F0-01+ registra su `render`) y
  `CatalogosExplorerPage` (arma el explorador desde el registry; placeholder "no
  implementado" hasta que cada módulo registre su pantalla).
- `src/app/`: `providers` (QueryClient + PrimeReact), `router`, `main.tsx`.
- **Calidad:** `tsc --noEmit`, `eslint` y `vitest` (prueba de `StatusBadge`) en verde;
  `vite build` y el dev server arrancan correctamente.

Pasos manuales pendientes para F0-01: registrar la entrada del catálogo (con su `render`)
en `catalogRegistry`, definir `types.ts`/`api.ts`/`hooks.ts` del módulo y su pantalla
lista+detalle usando los componentes de `shared/ui`.

## Pendientes / dudas
- (Resuelto) Quién edita los catálogos → por ahora solo Admin (IT).
- (Resuelto) Paginación → por página (`?page&size`).
- (Abierto) SSO corporativo `[[POR LLENAR]]`: reemplazar `get_current_user` (ADR-008).
- (Abierto) Credencial/endpoint de RDS de desarrollo: validar contra `/health/db`.
