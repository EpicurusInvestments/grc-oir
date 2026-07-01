# Arquitectura — Sistema GRC-OIR

> Documento VIVO: se actualiza cada vez que se toma o cambia una decisión de
> arquitectura (ver skill `documentacion-proyecto`). Las decisiones se registran como
> ADRs ligeros (Architecture Decision Records): contexto → decisión → consecuencias.
> Así cualquier integrante entiende POR QUÉ el sistema es como es, no solo cómo es.

## Visión general

Aplicación web por capas: Presentación (React+TS) → API (FastAPI, /api/v1) →
Negocio (servicios con máquina de estados y fórmulas) → Integración (adaptadores:
timbrador, NOI, bancos, facturas proveedor) → Datos (SQL Server en AWS RDS).
Los actores externos (clientes, agencias, afiliados) no acceden al sistema.

[[POR LLENAR: insertar/enlazar diagrama de arquitectura actualizado]]

## Decisiones de arquitectura (ADRs)

### ADR-001 — Stack: React+TS / FastAPI / SQL Server en AWS RDS
- **Estado:** aceptada · **Fecha:** [[POR LLENAR]]
- **Contexto:** requerimientos de GRC (multicapa, API First, BD relacional) y equipo.
- **Decisión:** frontend React+TypeScript; backend Python/FastAPI; BD Microsoft SQL
  Server gestionada en AWS RDS; desarrollo local con Docker.
- **Consecuencias:** OpenAPI automático; necesidad de driver ODBC en imágenes; ENUMs
  como CHECK constraints; tipos generables hacia el front.

### ADR-002 — Preparación de facturas, no timbrado
- **Estado:** aceptada (propuesta Pointwise, principio de diseño)
- **Decisión:** el sistema prepara la información del CFDI y exporta archivo plano al
  timbrador externo; recibe folio fiscal y datos de timbrado. No se integra un PAC.
- **Consecuencias:** la integración fiscal se reduce a exportar/importar archivos con
  validación; el ciclo se modela con `enviada_a_timbrado → timbrada`.

### ADR-003 — SAP como referencia capturada
- **Estado:** aceptada (alcance inicial)
- **Decisión:** las requisiciones capturan el número de OC de SAP; sin integración
  directa. Un alcance ampliado podría agregar consulta a SAP (a evaluar).

### ADR-004 — Monolito modular
- **Estado:** propuesta · [[POR LLENAR: confirmar]]
- **Decisión:** un solo despliegue de backend organizado por módulos que espejan las
  fases; sin microservicios en esta etapa.

### ADR-005 — Plaza de la Estación: herencia desde el Afiliado (Opción A)
- **Estado:** aceptada · **Fecha:** (F0-01)
- **Contexto:** tanto `Estacion` como `Afiliado` tienen `plaza_id`; podían divergir.
- **Decisión:** la estación HEREDA la plaza de su afiliado. `Estacion.plaza_id` se asigna
  en el servicio = `Afiliado.plaza_id` y no se captura en el formulario. Se asume que un
  afiliado opera en una sola plaza.
- **Consecuencias:** UI más simple (inferencia automática, como en la pantalla aprobada);
  consistencia garantizada por diseño. Si a futuro un afiliado opera en varias plazas, se
  revisará para pasar a captura libre.

### ADR-006 — Omisión del campo `venta_directa_carmen_aristegui_cdmx`
- **Estado:** aceptada · **Fecha:** (F0-01)
- **Contexto:** la especificación BD v2 incluye en `Estacion` un BIT
  `venta_directa_carmen_aristegui_cdmx` (bandera muy específica).
- **Decisión:** se OMITE deliberadamente en el modelo y la UI.
- **Consecuencias:** desviación consciente respecto a la spec v2. Se documenta aquí para
  que no se reincorpore por error pensando que fue un olvido. Si el negocio lo requiere
  después, se reintroducirá como una bandera/atributo más general.

### ADR-007 — CRUD genérico de catálogos + registry (F0-00)
- **Estado:** aceptada · **Fecha:** 2026-06 (F0-00)
- **Contexto:** los 15 catálogos de F0 comparten la misma mecánica (lista paginada con
  filtros, alta/edición, baja lógica) y la misma pantalla "explorador". Reimplementarla
  por catálogo sería repetitivo y propenso a inconsistencias.
- **Decisión:** una base reutilizable en `app/modules/catalogos/`:
  `BaseRepository` (datos), `BaseService` (negocio, devuelve siempre `XxxRead`) y la
  factory `build_crud_router(...)` que arma los 5 endpoints estándar con `requiere_permiso`
  ya cableado. Cada catálogo (F0-01+) es un submódulo/archivo que aporta su modelo +
  schemas + (opcional) subclase de servicio. En el front, un `catalogRegistry` cumple el
  papel gemelo (cada catálogo registra label/grupo/columnas/detalle).
- **Consecuencias:** dar de alta un catálogo ≈ definir entidad + 1 llamada a la factory.
  Los puntos de extensión `_pre_create`/`_pre_update` del servicio son donde F0-03
  enchufará `field_permissions.verificar` y `audit.log_cambio_parametro` para los % de
  comisión sin re-cablear. `crud_router.py` usa anotaciones dinámicas (no PEP 563) para
  que FastAPI reconozca los modelos; mypy las ignora solo en ese archivo.

### ADR-008 — Autenticación de desarrollo: dev-only y fail-closed (F0-00)
- **Estado:** aceptada (provisional) · **Fecha:** 2026-06 (F0-00)
- **Contexto:** el SSO corporativo sigue `[[POR LLENAR]]`, pero el RBAC por área
  (`requiere_permiso`) debe poder probarse desde la Entrega 1.
- **Decisión:** `get_current_user` (en `core/security.py`) resuelve el usuario por headers
  de desarrollo `X-Dev-User`/`X-Dev-Area` (con admin por defecto en `.env`), pero **solo
  si `APP_ENV=development`**. En cualquier otro entorno sin SSO, la autenticación **falla
  cerrada** (401): nunca asume admin. Es una sola función, marcada `# TODO(SSO)`.
- **Consecuencias:** se prueban todas las áreas en local sin SSO, sin riesgo de dejar una
  puerta abierta en qa/producción. Al integrar el SSO se reemplaza únicamente esa función.

### ADR-009 — Acceso a datos síncrono (pyodbc) + engine perezoso (F0-00)
- **Estado:** aceptada · **Fecha:** 2026-06 (F0-00)
- **Contexto:** SQL Server en RDS con ODBC Driver 18; había que elegir sync vs async y
  evitar que un RDS inalcanzable impida arrancar la app en local/CI.
- **Decisión:** backend **síncrono** (pyodbc, endpoints `def` que FastAPI corre en
  threadpool), consistente en toda la capa de datos. El engine se crea de forma
  **perezosa** (no al importar): la app arranca aunque RDS no responda, y la conexión se
  prueba bajo demanda en `GET /health/db`.
- **Consecuencias:** arranque robusto sin red; `/health/db` distingue problemas de driver
  (la imagen Docker instala el Driver 18; algunos hosts solo tienen el 17) de problemas de
  red/credenciales. La cadena de conexión usa `odbc_connect=` URL-encodeado para soportar
  el guion del nombre `GRC-OIR`.

### ADR-010 — Vulnerabilidades de esbuild/Vite en desarrollo: aceptadas temporalmente
- **Estado:** aceptada · **Fecha:** (F0-00)
- **Contexto:** `npm audit` reporta 5 vulnerabilidades (3 moderate, 1 high, 1 critical)
  que se originan todas en `esbuild` y se propagan en cascada a `vite`, `vitest`,
  `@vitest/mocker` y `vite-node`. El aviso (GHSA-67mh-4wv8-2f99) afecta únicamente al
  **servidor de desarrollo** (permite que un sitio web haga peticiones al dev server y
  lea la respuesta); no afecta el build de producción.
- **Decisión:** NO aplicar `npm audit fix --force`, porque actualizaría Vite a una
  versión mayor (8.x) con cambios incompatibles que romperían el frontend recién montado.
  Se aceptan temporalmente, dado que el riesgo real es bajo (desarrollo local no expuesto
  a internet).
- **Consecuencias:** pendiente conocido. Se revisará en una tarea dedicada de
  actualización de dependencias cuando Vite/Vitest publiquen versiones que cierren el
  aviso sin ruptura. No bloquea F0-00.
- **Revisar:** ejecutar `npm audit` periódicamente; reevaluar si aparece un vector que
  afecte producción.

[[Agregar aquí cada nueva decisión: ADR-011, ...]]
