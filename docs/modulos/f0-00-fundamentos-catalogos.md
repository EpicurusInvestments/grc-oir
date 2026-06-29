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

## Pendientes / dudas
- (Resuelto) Quién edita los catálogos → por ahora solo Admin (IT).
- (Resuelto) Paginación → por página.
