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

### ADR-011 — Timestamps: `DATETIME2` cross-dialect y `updated_at` en toda entidad (F0-01)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-01)
- **Contexto:** `sa.DateTime` compila a `DATETIME` (legacy, menor rango/precisión) en SQL
  Server, pero la spec y las buenas prácticas piden `DATETIME2`. Además, las pruebas
  corren en SQLite, que no conoce `DATETIME2`. Por otro lado, la spec lista solo
  `created_at` en Plaza/Estación, mientras `CLAUDE.md §6` exige `updated_at` en toda entidad.
- **Decisión:** un helper `datetime2()` en `core/db.py` devuelve
  `DateTime().with_variant(mssql.DATETIME2(), "mssql")`: usa `DATETIME2` en SQL Server y
  cae a `DATETIME` en SQLite (pruebas). Se agrega `updated_at` a **las tres** entidades de
  F0-01 (unifica el criterio de §6 sobre la enumeración de la spec; ver ficha f0-01, E-3).
- **Consecuencias:** columnas de auditoría con el tipo correcto en producción sin romper
  las pruebas locales; desviación consciente y uniforme respecto a la spec en `updated_at`.

### ADR-012 — Conexión y migraciones: engine desde `settings`, secretos con `$` entre comillas (F0-01)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-01)
- **Contexto:** al generar/aplicar la primera migración real surgieron dos problemas: (1)
  `migrations/env.py` pasaba la URL por `config.set_main_option`, y `configparser`
  interpretaba el `%` del `odbc_connect` URL-encodeado como sintaxis de interpolación y
  fallaba; (2) `python-dotenv` interpola `$` en los valores del `.env`, mutilando
  contraseñas con `$` (p.ej. `...$$w0rd...`) → *Login failed*.
- **Decisión:** (1) `env.py` ya NO pasa la URL por configparser: crea el engine
  directamente con `create_engine(settings.sqlalchemy_url, ...)` (online) y usa
  `settings.sqlalchemy_url` en el contexto offline. (2) Las contraseñas con caracteres
  especiales (`$`) se escriben entre **comillas simples** en el `.env` (documentado en
  `.env.example`), porque python-dotenv no interpola dentro de comillas simples.
- **Consecuencias:** `alembic upgrade`/`--autogenerate` funcionan contra RDS; regla clara
  para credenciales en `.env` local y en el gestor de secretos de qa/producción. La
  primera migración (`7300e6f940a3`) creó Plaza, Afiliado y Estación en `GRC-OIR`.

### ADR-013 — CORS configurable por entorno (F0-01)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-01)
- **Contexto:** el frontend (SPA en `http://localhost:5173`) y el backend
  (`http://localhost:8000`) viven en orígenes distintos. Sin CORS, el navegador cancela el
  preflight `OPTIONS` de los `POST`/`PUT` (405) y no se pueden crear/editar registros; los
  `GET` simples sí pasaban. En producción el frontend tendrá otro dominio.
- **Decisión:** se agrega `CORSMiddleware` de FastAPI en `app/main.py` con los orígenes
  permitidos tomados de la variable de entorno **`CORS_ORIGINS`** (coma-separada), nunca
  hardcodeados. En desarrollo, `http://localhost:5173`; en qa/producción se define el
  dominio real. Se habilitan todos los métodos y headers para cubrir el preflight y los
  headers de auth de desarrollo (`X-Dev-User` / `X-Dev-Area`); `allow_credentials=True`
  para soportar cookies/credenciales cuando se integre el SSO.
- **Consecuencias:** el frontend puede crear/editar contra el backend en local; la
  configuración de orígenes es por entorno (12-factor). Al integrar el SSO, revisar si
  conviene restringir `allow_headers`/`allow_methods` a lo estrictamente necesario.

### ADR-014 — Comparar columnas BIT con `== True/False`, no con `.is_(...)` (F0-01)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-01)
- **Contexto:** un conteo usaba `Columna.activo.is_(True)`. SQLAlchemy lo compila a
  `activo IS 1`, que en SQL Server es **sintaxis inválida** (`IS` solo compara con NULL);
  en SQLite (donde corren las pruebas) sí funciona. Resultado: 500 en RDS al desactivar
  afiliados/plazas, pero pruebas en verde — un bug que se colaba por la brecha
  SQLite↔SQL Server.
- **Decisión:** para columnas booleanas (`BIT`) se compara con `== True` / `== False`
  (SQLAlchemy → `activo = 1` / `= 0`, portable) o con la variable Python directamente
  (`col == params.activo`). Nunca `.is_(True/False)` sobre BIT (`.is_(None)` sí es válido,
  es para NULL). Se acompaña de `# noqa: E712` donde aplica.
- **Consecuencias:** desactivación funciona en RDS. Para evitar recurrencia se agregaron
  pruebas: una que compila el filtro con el dialecto de SQL Server y exige `activo = 1`
  (no `IS`), y un guard que escanea los módulos de catálogos y falla si reaparece
  `.is_(True/False)`. **Lección transversal:** validar contra SQL Server (no solo SQLite)
  las consultas con especificidades de dialecto (BIT, tipos de fecha, `TOP`/`LIMIT`, etc.).

### ADR-015 — TarifaPlaza: neta calculada+persistida, anti-solapamiento y filtro de vigencia (F0-02)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-02)
- **Contexto:** la entidad `TarifaPlaza` introduce en F0 cosas que los catálogos previos no
  tenían: un campo **calculado** (`tarifa_neta`), **montos decimales**, **vigencias** con
  regla de no-solapamiento, y un filtro derivado Vigentes/Expiradas que el CRUD genérico de
  F0-00 no contempla. Además la tabla `Usuario` aún no existe (llega en F0-04).
- **Decisión:**
  1. **`tarifa_neta` calculada en el servicio con `Decimal` y persistida** (fórmula de la
     spec `bruta * (1 - descuento/100)`, `ROUND_HALF_UP` a 2 decimales). No se acepta en los
     schemas Create/Update; se recalcula en cada edición con los valores efectivos.
  2. **Montos como `NUMERIC(14,2)` / `NUMERIC(5,2)`** (nunca float) y **serializados como
     string** en el JSON de la API para preservar precisión (E-4).
  3. **Anti-solapamiento en el repositorio** con intervalos cerrados
     (`existente.desde <= nuevo.hasta AND nuevo.desde <= existente.hasta`, bordes
     inclusivos), solo contra tarifas **activas** de la misma combinación, excluyendo la
     propia al editar. Se valida al crear, editar y **reactivar**; conflicto → 409.
  4. **`vigencia_desde`/`vigencia_hasta` ambas NOT NULL** (E-1: el negocio no maneja tarifas
     abiertas) + CHECK `vigencia_hasta >= vigencia_desde`.
  5. **`created_by` como texto (username), no FK** (E-2): no hay tabla `Usuario` hasta F0-04;
     se reevaluará migrar a FK entonces.
  6. **Filtro Vigentes/Expiradas server-side** sin tocar `crud_router.py` (E-3): en
     `tarifa.py` se retira SOLO la ruta `listar` que arma la factory y se registra una
     equivalente que acepta `?vigencia`; el `hoy` lo fija el servidor. El resto de endpoints
     de la factory quedan intactos. Mismo espíritu con que `estacion.py` añade su ruta propia.
- **Consecuencias:** primer catálogo con dinero y fechas; sienta el patrón (Decimal en
  servicio, string en el cable, comparaciones de fecha/booleanas portables a SQL Server —
  ADR-014). La personalización de la ruta de lista es local al módulo; si más catálogos
  necesitaran filtros extra de lista, convendría evaluar un punto de extensión en la factory
  en vez de repetir el retiro de ruta.

### ADR-016 — Parámetros sensibles: `LogCambioParametro` persistida y mecanismo único en `core/` (F0-03)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-03, tanda 1)
- **Contexto:** F0-03 introduce los primeros **PARÁMETROS SENSIBLES** de la spec
  (`porcentaje_comision_agencia_default`, y en tandas siguientes `dias_credito_default` y
  `porcentaje_comision_contrato`). CLAUDE.md (principio 6) exige permiso por campo + registro
  en bitácora al modificarlos. Los hooks `core/field_permissions.verificar(...)` y
  `core/audit.log_cambio_parametro(...)` existían desde F0-00 con firma estable, pero el
  segundo **solo escribía al logger** (sin persistir) y ninguno tenía consumidores. La
  entidad/pantalla `LogCambioParametro` pertenece a F5, pero la tabla y el registro se
  necesitan YA (F0-03 es donde primero se usan).
- **Decisión:**
  1. **Crear la tabla `log_cambio_parametro` en la migración de F0-03** (no esperar a F5) y
     definir su modelo SQLAlchemy en `core/audit.py` (junto al hook), para que quede en
     `Base.metadata` al importar el hook. Valores anterior/nuevo como **texto** (los campos
     sensibles son heterogéneos: `Decimal`, `Integer`, ...).
  2. **`log_cambio_parametro` pasa a persistir**: se le agrega `db: Session` (firma sin
     consumidores previos → cambio seguro) y hace `db.add(...)` en la **misma sesión** del
     servicio; el `commit` del repositorio lo escribe **atómicamente** junto con el cambio
     de la entidad. Conserva el `logger.info`.
  3. **Un único orquestador** `audit.registrar_cambio_sensible(...)` encapsula la política:
     `field_permissions.verificar` → exigir `motivo` (solo en edición) → `log_cambio_parametro`.
     Los servicios (Agencia, luego Anunciante/Contrato) lo llaman desde `_pre_create`
     (alta, `anterior=None`, sin exigir motivo — decisión E-3) y `_pre_update` (solo si el
     valor **cambia**). `motivo_cambio` es un campo **transitorio** del schema Update: el
     servicio lo consume (`payload.pop`) y nunca llega a la BD.
  4. **Permiso por campo hoy = solo `admin`** (decisión confirmada de la ficha); cuando F5
     administre `PermisoCampo` se cambia solo el cuerpo de `field_permissions.verificar`.
- **Consecuencias:** la auditoría de sensibles opera end-to-end desde F0-03 sin re-trabajo
  en F5 (solo faltará la pantalla de consulta). El mecanismo vive una sola vez en `core/`;
  cada entidad sensible solo declara su campo y llama al orquestador. La atomicidad garantiza
  que no haya cambios sin su traza (ni trazas de cambios revertidos). En el frontend, estos
  campos llevan el tag «Audit log» y piden "Motivo del cambio".
- **Actualización (2026-07, F1):** `audit.registrar_cambio_sensible(...)` llama
  internamente a `field_permissions.verificar(...)`, que sigue **hardcodeado a "solo
  Admin"** (punto 4 arriba, placeholder de F0 pendiente de `PermisoCampo` real en F5).
  El canal de comisiones de F1 (ADR-029, `PATCH /ordenes/clientes/{id}/comisiones`) es
  Dirección/Admin — Ventas también pasa por `_pre_create` al dar de alta la OC (alta
  libre, sin motivo). Usar el orquestador genérico ahí habría bloqueado a AMBAS áreas
  con un 403 falso (el placeholder no conoce "Dirección"). **Corrección:** los 2 puntos
  de F1 que tocan comisión (`create()` y `actualizar_comisiones()` en
  `orden_cliente.py`) llaman **directo** a `audit.log_cambio_parametro(...)` (la
  función de más bajo nivel, sin chequeo de permiso), porque cada uno YA implementa su
  propia autorización correcta por área antes de llegar ahí. **Lección para módulos
  futuros:** el orquestador `registrar_cambio_sensible` solo es seguro de reusar
  mientras el placeholder de `field_permissions` siga siendo "Admin-only" — cualquier
  campo sensible cuya autorización real involucre un área distinta de Admin debe
  auditar con `log_cambio_parametro` directo (con su propio chequeo de área en el
  servicio) hasta que F5 implemente `PermisoCampo` de verdad, momento en el que
  `field_permissions.verificar` pasa a resolver el permiso real y el orquestador vuelve
  a ser seguro para todos los casos.

### ADR-017 — Collation de la BD `GRC-OIR` (RDS) confirmada case-insensitive (F0-03)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-03, tanda 1)
- **Contexto:** la unicidad de `nombre_agencia` debía ser insensible a mayúsculas/minúsculas.
  Faltaba confirmar el comportamiento del índice único frente a la collation real de RDS
  (decisión E-6).
- **Decisión / hallazgo:** `SELECT DATABASEPROPERTYEX('GRC-OIR','Collation')` en RDS devuelve
  **`SQL_Latin1_General_CP1_CI_AS`** (Case-Insensitive, Accent-Sensitive). Por tanto el índice
  único `ix_agencia_nombre_agencia` ya trata "ACME"/"acme" como duplicado a nivel de motor. El
  servicio, además, verifica con `func.lower(...)` (portable a SQL Server y SQLite) para dar un
  **409 `conflicto`** claro antes del `INSERT`, en lugar de un `IntegrityError` crudo.
- **Consecuencias:** las verificaciones de unicidad textual son CI de forma consistente
  (motor + servicio) sin `COLLATE` explícito. Es **accent-sensitive**: "media"≠"médiá"
  (aceptable para nombres propios; revisar si el negocio pidiera lo contrario).

### ADR-018 — El handler de `RequestValidationError` serializa con `jsonable_encoder` (F0-03)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-03, tanda 1 — bug encontrado en pruebas)
- **Contexto:** un `PUT`/`POST` con un dato mal formado que dispara un **validador propio**
  (`@field_validator`/`@model_validator` que hace `raise ValueError(...)`, p.ej. RFC de
  Agencia/Afiliado o la vigencia de TarifaPlaza) devolvía **500** en vez de 422. Causa: el
  handler central de `errors.py` metía `exc.errors()` directamente en el `JSONResponse`, y
  para esos errores Pydantic v2 incluye en `ctx` el **objeto `ValueError` original**, que
  `json.dumps` no puede serializar (`TypeError: Object of type ValueError is not JSON
  serializable`). Las validaciones de tipo/longitud/rango sí serializaban (por eso no se
  había detectado). Es un defecto del **handler central**, no de los validadores (que
  lanzan `ValueError` correctamente).
- **Decisión:** pasar `exc.errors()` por **`fastapi.encoders.jsonable_encoder`** antes de
  armar el sobre (igual que el handler por defecto de FastAPI). El mensaje humano del
  validador se conserva en el campo `msg` de cada error; el `ctx` no serializable se
  reduce a algo seguro.
- **Consecuencias:** cualquier validador de dominio que lance `ValueError` produce ahora un
  **422 `validacion`** legible con el sobre uniforme, en todos los módulos (Agencia,
  Afiliado, TarifaPlaza y futuros). Regresión cubierta con pruebas HTTP en
  `test_f0_03_agencia.py` (POST y PUT con RFC inválido → 422, no 500).

### ADR-019 — Máquina de estados de Contrato con endpoint dedicado (F0-03)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-03, tanda 3)
- **Contexto:** `Contrato.estado_contrato` (vigente/suspendido/finalizado/cancelado) es un
  estado de negocio con transiciones restringidas, distinto de `activo` (baja lógica).
  Meterlo en el `PUT` genérico permitiría saltos arbitrarios de estado.
- **Decisión:** mapa de transiciones explícito en el servicio (`TRANSICIONES`):
  `vigente→{suspendido,finalizado,cancelado}`, `suspendido→{vigente,cancelado}`,
  `finalizado→{cancelado}`, `cancelado→∅`. Se cambia SOLO por
  `POST /catalogos/contratos/{id}/estado-contrato`; transición no permitida →
  `StateTransitionError` (409 `transicion_invalida`); mismo estado = idempotente.
  `estado_contrato` NO se acepta en Create/Update (se crea en `vigente`). `activo` y
  `estado_contrato` son dimensiones **independientes** (spec §6).
- **Consecuencias:** primer catálogo con máquina de estados; sienta el patrón para las
  entidades con estado de F1+ (OrdenCliente, FacturaCliente, etc.). Las transiciones de
  estado NO se registran en `LogCambioParametro` (esa bitácora es para parámetros
  sensibles; la auditoría general de operaciones es un tema aparte, posterior).

### ADR-020 — Adjuntos de contrato: puerto de almacenamiento con subida S3 diferida (F0-03)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-03, tanda 3)
- **Contexto:** los contratos guardan PDF en S3 bajo `contratos/<numero_contrato>/`, pero no
  hay bucket ni credenciales todavía, y CLAUDE.md prohíbe inventarlas. La spec define
  `archivo_contrato_path` (singular); un contrato tiene N archivos.
- **Decisión:** (1) `archivo_contrato_path` guarda el **prefijo/carpeta** del contrato en S3
  (no un archivo), calculado por el servicio; la lista de PDFs se obtendrá listando ese
  prefijo. (2) **Puerto anti-corrupción** `integrations/almacenamiento/port.py`
  (`prefijo_contrato`/`listar`/`subir`) con **adaptador local** (`adapter_local.py`) que
  resuelve el prefijo pero NO sube (subida **diferida**: `subir()` lanza un error de dominio
  claro). El servicio depende solo del puerto (inyectado). (3) Config `S3_BUCKET_CONTRATOS`
  / `AWS_REGION` en `.env.example` sin valores; credenciales por el proveedor de AWS del
  entorno (Secrets Manager en qa/producción), nunca versionadas. **Sin tabla
  `ContratoDocumento`** por ahora (basta el prefijo; se reevalúa si se requiere metadata por
  archivo — decisión E-2).
- **Consecuencias:** el dominio queda listo para S3 sin acoplarse a él; activar la subida
  real será añadir un `AlmacenamientoS3` que implemente el puerto y cambiar la inyección,
  sin tocar la capa de negocio. La integración real de S3 se hará como tarea aparte tras F0-03.
- **Actualización (2026-07-23):** **IMPLEMENTADA** en **ADR-027** — se añadió el adaptador S3
  real, la selección local/S3 por `STORAGE_BACKEND` y los endpoints de adjuntos. La subida
  ya NO está diferida.

### ADR-021 — Lectura acotada del historial de auditoría por entidad en F0-03
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-03, tanda 4)
- **Contexto:** el panel de detalle de la pantalla aprobada muestra un "Historial de
  cambios" del registro (fecha, usuario, campo, valor anterior→nuevo, motivo). Esos datos
  ya se persisten en `LogCambioParametro` desde F0-03 (ADR-016), pero la **pantalla de
  administración completa** de auditoría (todos los cambios, filtros globales) es de F5. Se
  necesitaba una lectura mínima sin adelantar F5.
- **Decisión:** exponer un endpoint **de solo lectura acotado a una entidad**:
  `GET /catalogos/<recurso>/{id}/historial`, que lee `LogCambioParametro` filtrado por
  (`entidad`, `entidad_id`) ordenado por `fecha_cambio` desc. La lógica vive una sola vez en
  `core/audit.listar_historial(...)` + `BaseService.historial(...)` (reutilizable por todos
  los catálogos); cada módulo que lo necesite añade la ruta (Agencia en la tanda 4). Se
  protege con `catalogos:leer` (mismo permiso de lectura del catálogo). NO expone escritura
  ni consulta global: eso sigue siendo F5.
- **Consecuencias:** el panel puede mostrar el historial desde F0-03 sin construir la
  pantalla de F5; cuando llegue F5, su pantalla de administración consulta la misma tabla y
  este endpoint por-entidad se conserva como atajo del detalle. Nota de rendimiento: la
  consulta usa el índice `ix_log_cambio_parametro_entidad (entidad, entidad_id)`.

### ADR-022 — Alcance de catálogos de facturación/finanzas: omisiones y diferimientos (F0-04)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-04) · decisiones confirmadas por el equipo.
- **Contexto:** la spec BD v2 lista 7 entidades para el grupo facturación/finanzas
  (EmpresaFacturadora, Vendedor, Categoria, MetodoPago, CuentaContable, LayoutFactura,
  Usuario). El equipo ajustó el alcance de F0-04.
- **Decisión:**
  1. **F0-04 implementa 4:** `EmpresaFacturadora`, `Vendedor` (con % sensible auditado),
     `Categoria`, y el **modelo** de `Usuario` (tabla + seed; su pantalla es F5).
  2. **`MetodoPago` y `CuentaContable`: diferidos a F0-05.** No se crean tabla ni pantalla
     propias aquí; se gestionarán dentro de `ConstantesSistema` (pantalla "Constantes del
     sistema", menú "Configuración").
  3. **`LayoutFactura`: omitido por ahora** (ni entidad, ni pantalla). Es una **desviación
     consciente** respecto a la spec v2; si el negocio lo requiere, se reintroduce como
     tarea aparte.
- **Consecuencias:** F0-04 queda enfocado; F2 (Facturación) tendrá que contemplar la
  reintroducción de `LayoutFactura` si se necesita el layout del timbrador por empresa. Los
  catálogos SAT/timbrador y método de pago/cuenta contable se consolidan en F0-05. Se
  registra aquí para que la omisión no se lea como olvido.

### ADR-023 — Modelo `Usuario` base + seed mínimo para RBAC (F0-04)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-04)
- **Contexto:** el RBAC (`core/security.py`) resuelve el usuario por headers de desarrollo
  (`X-Dev-User`/`X-Dev-Area`, ADR-008) sin tabla. F0-04 crea el **modelo** `Usuario` de la
  spec para que F5 construya su pantalla y cablee `get_current_user` contra la tabla.
- **Decisión:** tabla `usuario` con los **7 campos exactos** de la spec (sin `updated_at`;
  el resto de catálogos sí lo llevan por ADR-011). `area` = VARCHAR + CHECK `ck_usuario_area`
  con los mismos valores que `core.security.Area` (fuente única). `email` único. Se siembra
  **un** admin alineado al dev: `nombre_usuario='dev.admin'`, `email='dev.admin@grcoir.com'`,
  `area='admin'` (id determinista), de modo que en F5 el header `X-Dev-User=dev.admin` empate
  con un registro real. La **pantalla** de administración de usuarios es de F5.
- **Consecuencias:** el modelo vive en `app/modules/usuarios/models.py` (módulo espejo,
  model-only, sin router/servicio). No hay endpoints de Usuario en F0-04. El seed evita el
  desajuste header↔tabla cuando F5 conecte el RBAC a la BD.

### ADR-024 — CuentaContable como tabla propia; MetodoPago como constante SAT (F0-05)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-05) · decisión confirmada por el equipo.
- **Contexto:** F0-05 consolida los catálogos SAT/timbrador en `ConstantesSistema` (entidad
  HOMOGÉNEA: grupo/clave/descripcion/valor). Dos catálogos diferidos de F0-04 (ADR-022) debían
  ubicarse aquí: `MetodoPago` y `CuentaContable`. El primero encaja como constante SAT simple;
  el segundo tiene estructura propia (`codigo_cuenta`, `nombre_cuenta`, `tipo_cuenta` ENUM).
- **Decisión:**
  1. **`MetodoPago` = grupo de `ConstantesSistema`** (valores `PUE`/`PPD`): es homogéneo con el
     resto de constantes SAT, no amerita tabla propia.
  2. **`CuentaContable` = tabla propia** (Opción 2 del plan), NO un registro dentro de la
     genérica. Motivos: (a) fidelidad a la spec v2 (regla de oro #3), que la lista como entidad
     con campos propios; (b) su ENUM `tipo_cuenta` se implementa como VARCHAR + CHECK nombrado
     (`ck_cuenta_contable_tipo`, 5 valores), imposible sobre el `valor` genérico compartido por
     9 grupos; (c) integridad futura: una tabla real con PK permite que F3/F4 la referencien por
     FK; (d) costo bajo: es otro catálogo sobre la base de F0-00 (como `Categoria`).
  3. **Unicidad de `ConstantesSistema` = `(grupo, clave)`** compuesta y case-insensitive (la
     misma clave puede repetirse entre grupos, no dentro de uno); `CuentaContable.codigo_cuenta`
     único CI. Ambas verificadas en el servicio con `func.lower(...)` (ADR-017).
- **Consecuencias:** los catálogos SAT quedan bajo una sola entidad flexible y CuentaContable
  conserva su semántica y validación fuertes. `MetodoPago`/`CuentaContable` dejan de estar
  "diferidos". Pendiente menor (F-6): confirmar con contabilidad si CuentaContable requiere
  campos extra (naturaleza, agrupador); de ser así se amplía sin romper lo existente.

### ADR-025 — Carga masiva CSV: dry-run→confirmar, stateless, import parcial atómico (F0-05)
- **Estado:** aceptada · **Fecha:** 2026-07 (F0-05, tanda 2) · primera importación de archivos
  del proyecto.
- **Contexto:** el Admin debe poder cargar los catálogos SAT en lote desde un CSV oficial,
  además de la captura manual. Es la primera vez que el proyecto recibe archivos; había que
  definir el mecanismo sin comprometer seguridad ni claridad del resultado.
- **Decisión:**
  1. **Endpoint** `POST /catalogos/constantes/importar` (`multipart/form-data`, `catalogos:crear`
     → solo admin). `archivo` (.csv) + `commit` (bool) + `modo_duplicados`.
  2. **Flujo dry-run → confirmar, STATELESS:** `commit=false` devuelve el reporte de qué se haría
     sin escribir; el cliente re-sube el MISMO archivo con `commit=true` para aplicar (se
     revalida). No se persiste el archivo en el servidor (sin temporales, sin PII residual).
  3. **Validación en dos niveles:** estructural (columnas/vacío/UTF-8 → 400; tamaño/filas →
     413) que aborta todo; y por fila (enum de grupo, obligatorios, longitudes, `activo`), que
     NO aborta: **import parcial** (válidas entran, inválidas se reportan con motivo).
  4. **Duplicados:** `actualizar` (upsert, default; idempotente al re-cargar la lista oficial),
     `omitir` o `rechazar`; duplicado **dentro del archivo** → 2ª fila rechazada. Clasificación
     sin N+1 precargando el índice `(grupo, clave)` en memoria (`mapa_por_grupo_clave`).
  5. **Atomicidad:** el subconjunto válido se aplica en UNA transacción (rollback total si falla
     a nivel BD). El reporte es idéntico en dry-run y commit (previsualización fiel).
  6. **Límites/seguridad:** 2 MB / 5 000 filas (configurables en `config.py`); solo `.csv`;
     procesado en memoria con `csv`/`io` de la stdlib (sin pandas). Única dependencia nueva:
     `python-multipart` (requerida por FastAPI para `UploadFile`/`Form`).
  7. **Helper reutilizable** `importacion_csv.py`: aísla lo mecánico y agnóstico al dominio
     (lectura con tope, decodificación/BOM, sniff de delimitador, validación estructural, tipos
     del reporte). La validación por fila y la política de duplicados viven en el servicio del
     catálogo. Así CuentaContable u otros catálogos podrán tener carga CSV reusando el helper.
- **Consecuencias:** patrón de importación de archivos establecido para todo el sistema (NOI,
  estados de cuenta, XML de proveedor en fases posteriores podrán inspirarse en él, aunque esos
  van por la capa de integración). La neutralización de CSV-injection (`= + - @`) corresponde a
  la EXPORTACIÓN a Excel (F2/reportes), no a esta importación (que solo almacena texto). Por
  ahora solo `ConstantesSistema` expone `/importar`; CuentaContable queda listo para sumarlo.

### ADR-026 — Dashboard como Home real + navegación global entre fases (solo frontend)
- **Estado:** aceptada · **Fecha:** 2026-07-20
- **Contexto:** hasta ahora la única ruta (`/`) era el explorador de Catálogos, que hacía
  de "home" de facto. El sistema tendrá 6 fases (F0–F5) y hacía falta un Home verdadero y
  una forma de navegar entre fases, reutilizable por las pantallas futuras. Cambio
  transversal, solo de presentación (no toca API ni BD).
- **Decisión:**
  1. **Rutas:** `/` → `DashboardPage` (Home, malla de 6 fases); `/catalogos` →
     `CatalogosExplorerPage` (lo que antes vivía en `/`). El router queda declarado para
     sumar cada fase futura con su propia ruta.
  2. **Fuente única `phaseRegistry`** (`src/shared/phases/phaseRegistry.ts`): un arreglo con
     las 6 fases (código, nombre, descripción, acento de color, ilustración WebP+PNG, ruta y
     `enabled`). **Tanto el Dashboard como el drawer se generan iterando este arreglo.**
     Activar una fase futura = poner `enabled: true` + su `route`, y montar la ruta. No se
     tocan el Dashboard ni el menú.
  3. **Navegación global reutilizable** (`AppNavDrawer`): drawer deslizante montado desde
     `AppHeader`, por lo que **toda pantalla que use el header hereda la hamburguesa + el
     menú** sin re-trabajo. Cierra con overlay, Escape y botón de cerrar.
  4. **Estado "Próximamente":** las fases no construidas se muestran atenuadas, en escala de
     grises y no clicables, con badge gris — consistente entre tarjeta y menú.
  5. **Color por fase** reutilizando la paleta ya existente en `theme.css` (F0 morado · F1
     teal · F2 azul · F3 ámbar · F4 gris · F5 rojo) vía clases `.pc-accent-*`; se añadieron
     solo los tonos sólidos de acento que faltaban (azul/ámbar/gris/rojo).
  6. **Imágenes:** 6 ilustraciones 3D optimizadas de PNG (~1–1.3 MB) a **WebP calidad 82**
     (5–6 KB) con **PNG fallback** (~55–67 KB) vía `<picture>`; recortadas al contenido y
     cuadradas a 256px. Total 6.7 MB → 32.6 KB WebP. Viven en
     `src/modules/dashboard/assets/` (importadas → Vite las hashea).
- **Consecuencias:** existe un Home real y un patrón de navegación entre fases listo para
  reusar; cada fase nueva se "enciende" en un solo lugar. Animaciones sutiles (fade-in
  escalonado, hover con elevación y zoom) con respeto a `prefers-reduced-motion`. Ficha del
  módulo en `docs/modulos/transversal/dashboard-navegacion.md`.

### ADR-027 — Integración REAL de S3 para adjuntos de contrato (implementa ADR-020)
- **Estado:** aceptada · **Fecha:** 2026-07-23 · **implementa/cierra ADR-020**.
- **Contexto:** ADR-020 dejó el puerto de almacenamiento anti-corrupción con la subida
  DIFERIDA (adaptador local placeholder). Ya hay bucket privado (`s3-grc-oir-dev`, `us-west-2`)
  y un usuario IAM con permisos mínimos, validado por el equipo. Toca implementar la subida/
  descarga real de PDF de contrato sin cambiar cómo el dominio usa el puerto.
- **Decisión:**
  1. **Se reutiliza el puerto** `AlmacenamientoPort`, extendido con `obtener(clave)` y
     `borrar(clave)`, y `listar` ahora devuelve `DocumentoAlmacenado` (nombre, clave, tamaño,
     fecha). El servicio de Contrato sigue dependiendo SOLO del puerto (inyección).
  2. **Dos adaptadores que cumplen el MISMO puerto:** `AlmacenamientoLocal` (ahora
     **filesystem real**, default para dev/pruebas) y `AlmacenamientoS3` (boto3 sobre el
     bucket privado). La **selección es por configuración** (`STORAGE_BACKEND=local|s3`);
     `get_almacenamiento()` es el único punto de decisión y **falla ruidosa** si se pide `s3`
     sin `S3_BUCKET_CONTRATOS`/`AWS_REGION` (no cae en silencio al local). Cero lógica
     duplicada: saneo de nombre, validación PDF/tamaño y prefijo son compartidos
     (`integrations/almacenamiento/documentos.py`).
  3. **Credenciales:** `config.py` declara `aws_access_key_id`/`aws_secret_access_key`
     (opcionales, vacías por defecto); pydantic-settings las lee del `.env` y el adaptador
     las pasa **explícitamente** a boto3. Si están vacías (qa/producción), boto3 usa su
     **cadena por defecto**: rol de instancia / AWS Secrets Manager. Siguen viniendo solo del
     entorno/`.env`, **nunca hardcodeadas**. En `.env.example` van como `[[POR LLENAR]]`.
     *(Corrige la decisión inicial F-1: se intentó dejarlas SOLO a la cadena por defecto de
     boto3, pero pydantic-settings **no exporta a `os.environ`**, así que el `.env` no
     alimentaba a boto3 y daba `NoCredentialsError`. Pasarlas explícitas resuelve el canal
     pydantic-settings↔boto3 y funciona igual en local y Docker, depurando comillas.)*
  4. **Servicio seguro de PDFs:** el bucket es privado; los PDF se sirven SIEMPRE por el
     backend (que valida RBAC), nunca por URL pública ni presigned. El cliente jamás envía
     una clave S3 cruda: manda solo el `nombre`, y el backend compone la clave desde el
     prefijo del propio contrato → acota el acceso y bloquea *path traversal*.
  5. **Endpoints** (bajo `/catalogos/contratos/{id}/adjuntos`): listar (GET) y descargar
     (GET `/{nombre}`) = `catalogos:leer`; subir (POST, multipart) y borrar (DELETE) =
     `catalogos:editar`. Validación: solo PDF (extensión + *magic bytes* `%PDF-`), tamaño
     máx. configurable (`S3_MAX_PDF_BYTES`, default 10 MB) → 413; errores de S3 → 502
     (`AlmacenamientoError`) con mensaje legible, sin filtrar detalle interno.
  6. **Nombre repetido SOBRESCRIBE** (put idempotente), con aviso en la UI (decisión F-3);
     si el negocio lo requiere, se puede cambiar a rechazar duplicados.
- **Consecuencias:** activar S3 es cambiar una variable de entorno; el dominio no cambió.
  `boto3` queda como dependencia formal en `pyproject.toml`. Sigue **sin tabla
  `ContratoDocumento`** (basta el prefijo). **Limitación conocida:** renombrar
  `numero_contrato` recalcula el prefijo pero NO mueve los objetos ya subidos en S3 (fuera
  de alcance; se reevaluará si el negocio lo requiere). Pruebas sin credenciales: adaptador
  local (filesystem) para servicio/router y un **cliente boto3 falso en memoria** para el
  adaptador S3.

### ADR-028 — SQLite local para desarrollo de F1, nunca AWS RDS (F1, tanda 1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1, tanda 1)
- **Contexto:** F1 (Órdenes) es el primer módulo desarrollado con acceso directo a un
  agente de código en este entorno. El equipo decidió que ningún desarrollo de F1
  tocara la instancia RDS compartida (`devapps.../GRC-OIR`) mientras se itera rápido
  con datos sintéticos — el riesgo de un `alembic upgrade`/seed accidental contra la
  base compartida no se considera aceptable para este flujo de trabajo.
- **Decisión:** `Settings.database_url` (vacío por defecto) permite anular por completo
  la construcción de la URL `mssql+pyodbc` de siempre: si viene seteada (p.ej.
  `sqlite:///./dev_ordenes.db`), `settings.sqlalchemy_url` la usa tal cual y el engine
  perezoso de `core/db.py` la reconoce (`check_same_thread=False`, sin `pool_pre_ping`).
  `backend/scripts/seed_dev.py` (idempotente, `Session.merge()` + UUIDs deterministas
  `uuid5`) **aborta explícitamente** si `DATABASE_URL` no apunta a SQLite, para que un
  olvido de variable de entorno no siembre contra RDS por accidente. La base SQLite es
  **desechable por diseño**: se recrea con `alembic upgrade head` + `seed_dev.py`.
  Los MODELOS (`Base.metadata`) son los mismos en ambos motores — el switch solo cambia
  qué motor los materializa.
- **Consecuencias:** iteración local rápida y sin red, con datos deterministas y
  reproducibles; ningún comando de este flujo (migraciones, seed, servidor de
  desarrollo, pruebas E2E manuales) toca RDS mientras `DATABASE_URL` no se setee a
  ella explícitamente. RDS sigue siendo la única base de qa/producción — este switch es
  exclusivamente para desarrollo/pruebas locales de F1 (y módulos futuros que lo
  necesiten). Guardarraíl transversal para cualquier agente/persona que opere este
  repo: **nunca ejecutar un comando de BD sin verificar primero que `DATABASE_URL`
  apunta a SQLite.**

### ADR-029 — Comisiones snapshot en OrdenCliente: extensión aditiva, alta libre + canal dedicado de edición (F1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1)
- **Contexto:** la spec BD v2 no modela un "% de comisión efectivo" por orden — solo los
  defaults de catálogo (`Vendedor.porcentaje_comision_default`,
  `Agencia.porcentaje_comision_agencia_default`). La propuesta comercial, sin embargo,
  es explícita: *"el porcentaje de comisión de un vendedor puede editarse solo por
  Dirección, aunque Ventas tenga captura sobre el resto de la orden"* — lo que exige un
  valor propio por OC que no cambie si el catálogo cambia después, y una autorización
  distinta a la del resto de campos de la orden.
- **Decisión:** 3 columnas aditivas en `OrdenCliente`
  (`porcentaje_comision_vendedor_principal_snap`/`_vendedor_secundario_snap`/
  `_agencia_snap`), PARÁMETRO SENSIBLE (auditadas en `LogCambioParametro`). Se capturan
  **libres al vender** (Ventas, sin motivo — es un alta, no una edición) y, una vez
  creada la OC, **solo se editan** por el canal dedicado
  `PATCH /ordenes/clientes/{id}/comisiones` (Dirección/Admin, `motivo_cambio` siempre
  requerido), **sin importar si la OC está congelada o no** — más simple y más fiel a
  la cita de la propuesta que una regla condicionada al estado. Al cerrar la orden
  (`cerrar()`), cualquier % que siga `null` se rellena con el default vigente del
  catálogo (Vendedor/Agencia) **sin auditar** (es completar un vacío, no una edición).
- **Consecuencias:** el valor de comisión de una OC queda inmune a cambios posteriores
  del catálogo; la autorización del canal de comisiones vive en el servicio
  (`Area.DIRECCION`/`Area.ADMIN`), separada del permiso de router (`ordenes:leer`) que
  solo decide quién puede *llegar* al endpoint — ver nota de permisos en
  `docs/API-CONTRACT.md`. Ver también la excepción de auditoría de este canal en la
  actualización de 2026-07 de ADR-016.

### ADR-030 — Granularidad por día (`OrdenEstacionDia`) y tres capas de captura asignado/programado/verificado (F1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1)
- **Contexto:** la spec BD v2 modela `fecha_transmision`/`hora_inicio`/`hora_fin`/
  `spots_solicitados`/`spots_asignados`/`spots_faltantes` como columnas PLANAS de
  `OrdenEstacion` (una fila = un día), pero la propia spec autoriza la alternativa:
  *"Si la orden cubre un rango de fechas, se puede crear una OrdenEstacion por fecha o
  AGRUPAR POR RANGO."* El prototipo aprobado, además, distingue tres momentos de
  captura por día (lo asignado al inicio, lo programado que confirma el afiliado, lo
  verificado que realmente se transmitió) que la spec no separa explícitamente.
- **Decisión:**
  1. **Agrupar por rango**: esos 6 campos se mueven a la tabla hija `OrdenEstacionDia`
     (una fila por día de la OE), tal como la spec autoriza.
  2. **Tres capas de captura por día**: `OrdenEstacionDia.spots_asignados` (spec, NOT
     NULL, 2.1) → `OrdenEstacionDia.spots_programados` (NUEVO, nullable, 2.2: `NULL` =
     el afiliado no lo ha confirmado todavía; al confirmarse se llena con el valor
     EFECTIVO de ese día, no con un delta) → `Verificacion.spots_verificados` (spec,
     2.3, **siempre** una fila por día, tenga o no diferencia). "Programado efectivo" =
     `spots_programados ?? spots_asignados`.
  3. **`spots_faltantes` deja de persistirse**: pasa a ser un agregado calculado por el
     servicio al leer (`SUM(spots_solicitados) − SUM(spots_asignados)` de los días de
     la OE), igual que `importe_estacion` y los importes/IVA/totales que dependen de él.
  4. **Campos de lote fuera de `OrdenEstacionDia`**: `testigos_url`/
     `testigos_ubicacion_alterna`/`notas_transmision`/`reporte_programados_ref`/
     `reporte_reales_ref` (tampoco en la spec) se capturan UNA VEZ por lote al avanzar
     2.1→2.2 o 2.2→2.3 (no por día) — viven en `OrdenEstacion`, coherente con cómo ya
     los captura el prototipo de frontend.
  5. **`Verificacion` se ancla a `orden_estacion_dia_id`**, no a `orden_estacion_id`
     (la spec la ancla a la OE; se ancla al día porque la propia spec autoriza esa
     granularidad) — es una tabla REAL persistida, revierte una decisión previa del
     frontend-only (E.1, tomada sin acceso a la spec) que la modelaba como vista
     derivada.
- **Consecuencias:** el ciclo 2.1→2.2→2.3 queda modelado exactamente como el prototipo
  aprobado lo captura, sin perder fidelidad a la spec (que autoriza el agrupamiento).
  `OrdenEstacion.estatus` es un ciclo de vida PROPIO e independiente del de
  `OrdenCliente`: cada OE cierra por su cuenta cuando sus días quedan reconciliados;
  `OrdenCliente.estatus_orden = orden_cerrada` es una transición aparte, gatillada
  cuando TODAS las OE de la OC ya están `cerrada` (se valida en el servicio).

### ADR-031 — Incidencia: modelo híbrido automático/manual (F1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1)
- **Contexto:** la spec define 5 tipos de `Incidencia` (`faltante`, `excedente`,
  `cambio_horario`, `cambio_fecha`, `spot_no_emitido`) y un flujo de `resolucion`
  completo. La generación automática al capturar una `Verificacion` (comparar
  verificado vs. programado efectivo) solo puede inferir matemáticamente
  `faltante`/`excedente` (una diferencia de spots); los otros 3 tipos requieren
  contexto que nadie captura todavía en el flujo automático (un cambio de horario o de
  fecha, o un spot que simplemente no salió al aire pese a coincidir el conteo).
- **Decisión:** modelo híbrido. La tabla `incidencia` implementa los 11 campos de la
  spec completos, incluida `resolucion` (default `pendiente`), pero:
  1. **Generación automática** (`avanzar_reales`, un evento por día con diferencia):
     solo produce `faltante`/`excedente`, calculando `diferencia_spots =
     spots_verificados − spots_programados_efectivo` y `monto_ajuste = diferencia_spots
     × precio_spot` de la OE. Se crea una `Verificacion` por CADA día de la OE (spec),
     pero solo se genera `Incidencia` en los días con diferencia distinta de cero.
  2. **Alta manual de los otros 3 tipos y edición de `resolucion`: diferida** — el
     frontend no tiene pantalla que las consuma hoy; se retoma cuando exista ese
     consumidor (ver "Diferido, sin consumidor hoy" en la ficha del módulo).
- **Consecuencias:** el modelo queda completo respecto a la spec desde ahora (sin
  migración futura para agregar campos), pero el ALCANCE funcional de esta tanda cubre
  solo la porción automática, la que el flujo operativo de F1 necesita hoy.

### ADR-032 — Infra CRUD genérica reubicada a `app/shared/` (F1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1, tanda 1)
- **Contexto:** `BaseRepository`/`BaseService`/`build_crud_router`/los schemas
  compartidos y el enum `DuracionSpot` vivían en `app/modules/catalogos/` (ADR-007),
  pensados en su momento solo para F0. F1 (`OrdenCliente`/`OrdenEstacion`) necesita la
  misma infraestructura genérica (paginación, filtros, `historial()` sobre
  `LogCambioParametro`) y el mismo enum de duración de spot que ya define F0.
- **Decisión:** mover `BaseRepository`/`BaseService`/`build_crud_router`/schemas
  compartidos y `DuracionSpot` de `app/modules/catalogos/` a `app/shared/` — un solo
  lugar neutral que cualquier módulo de negocio puede importar, sin que F1 (ni módulos
  futuros) tengan que depender de `catalogos/` para infraestructura genérica.
  `catalogos/__init__.py` y los módulos que ya la usaban se actualizan a importar desde
  la nueva ubicación; el comportamiento no cambia, solo la ubicación.
- **Consecuencias:** `app/shared/` queda establecido como el lugar de lo verdaderamente
  transversal entre módulos de negocio (regla de CLAUDE.md: "no crear dependencias
  directas entre módulos; lo compartido va a `app/shared/`"), evitando que F1 (o F2+)
  importen de `catalogos/` por conveniencia. F0 no tuvo que reescribir su lógica, solo
  el import.

### ADR-033 — Checklist de Vo.Bo. como tabla hija, no JSON (F1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1)
- **Contexto:** el prototipo de frontend modela el checklist de revisión previo al
  Vo.Bo. (10 ítems fijos, PO §2) como un objeto JSON embebido en la OC
  (`revision_checklist: Record<string, boolean>`). La spec no define esta entidad (es
  una extensión aditiva aprobada), y había que decidir cómo persistirla en el backend
  real: JSON embebido (más simple, replica el frontend) vs. tabla hija relacional.
- **Decisión:** tabla hija `orden_cliente_vobo_item` (`OrdenClienteVoBoItem`), NO JSON:
  una fila por ítem fijo (`ITEMS_VOBO`, 10 valores) por cada OC, con
  `completado`/`usuario_id`/`fecha_completado` propios por ítem. Se siembran las 10
  filas al crear la OC (`_pre_create`/override de `create()`); cada ítem se marca
  individualmente vía `PATCH /ordenes/clientes/{id}/vobo/{item_clave}`.
- **Consecuencias:** cada marca de checklist queda con su propio usuario y fecha
  (trazabilidad que un JSON plano no da gratis), a costa de una tabla más y un join
  extra al leer una OC completa (`OrdenClienteRead` arma el checklist reconstruyendo el
  `Record<string, boolean>` que el frontend espera, para que `fromApi.ts` no tenga que
  cambiar). El endpoint de alta de la OC (`dar_vobo: bool`) permite crear directo con el
  checklist completo cuando la demo/flujo así lo capture, sin forzar 10 PATCH previos.

### ADR-034 — Campos de cierre: snapshot de lo que faltaba al momento del cierre (F1)
- **Estado:** aceptada · **Fecha:** 2026-07 (F1)
- **Contexto:** el flujo de cierre de una OC (PO, estado 3) pide referencias a 2
  documentos (la orden de compra cerrada del cliente, la carta de conciliación) que
  pueden no existir todavía en el momento de cerrar — el negocio permite cerrar
  igualmente y dejar constancia de qué faltó, sin bloquear el avance a facturación.
  Ninguno de estos campos está en la spec BD v2 (extensión aditiva aprobada).
- **Decisión:** 5 columnas aditivas en `OrdenCliente`: `odc_cerrada_ref`,
  `carta_conciliacion_ref` (texto libre, sin endpoint de upload todavía — ver
  limitación conocida en la ficha del módulo), `cierre_sin_odc_cerrada`/
  `cierre_sin_carta_conciliacion` (booleanos, calculados por el servicio en `cerrar()`
  a partir de si cada ref llegó `None`) y `fecha_cierre` (fecha del día en que se
  cerró). Son un **snapshot al momento del cierre**: no se recalculan después si se
  suben las referencias más tarde.
- **Consecuencias:** el negocio puede cerrar sin ambos documentos y el sistema deja
  constancia auditable de qué faltaba, sin inventar un estado adicional en
  `estatus_orden`. Si el negocio necesitara "resolver" un cierre incompleto después
  (marcar que el documento faltante ya llegó), hoy no hay endpoint para eso — quedaría
  como una extensión futura de F1 o de F2 (Facturación), que es quien primero
  necesitaría verificarlo.

### ADR-035 — Por qué las 6 tablas de F1 no llevan `activo` (y el hueco real que esto expone)
- **Estado:** aceptada, CON un hueco de implementación documentado abajo · **Fecha:** 2026-08-10
- **Contexto:** CLAUDE.md establece baja lógica (`activo`, nunca `DELETE` físico) como regla
  transversal; los 11 catálogos de F0 la cumplen. Ninguna de las 6 tablas de F1
  (`OrdenCliente`, `OrdenClienteVoBoItem`, `OrdenEstacion`, `OrdenEstacionDia`, `Verificacion`,
  `Incidencia`) la tiene — decisión tomada en la Tanda 3, documentada solo con un comentario
  dentro de `OrdenClienteListParams`/`OrdenEstacionListParams`, insuficiente para que F2/F3/F4
  sepan por qué al construir sobre estas tablas. Se revisó primero contra la spec BD v2: **la
  spec NO define `activo` en ninguna de las 4 entidades de F1** (`OrdenCliente` 36 campos,
  `OrdenEstacion` 33, `Verificacion` 10, `Incidencia` 11 — ninguna lista incluye ese campo). Si
  la spec lo hubiera pedido y se hubiera omitido, sería una desviación que cambiaría esta
  conversación; no es el caso.
- **¿El razonamiento es que `estatus_orden`/`estatus` cubre la función de la baja lógica?**
  Sí, así de claro — pero con una precisión importante: la spec modela `OrdenCliente` y
  `OrdenEstacion` como entidades con **ciclo de vida propio** (`estatus_orden`/`estatus`, cada
  uno con un valor terminal `cancelada`), a diferencia de los catálogos de F0, que son listas
  planas sin estado de negocio — ahí `activo` es la ÚNICA señal de "esto ya no aplica" posible.
  Para una entidad que YA tiene un estado de negocio explícito, agregar `activo` encima crearía
  DOS señales redundantes de lo mismo ("¿ya no aplica por `cancelada` o por `activo=false`?"),
  lo que es peor que no tener ninguna: quien lea el dato no sabría cuál consultar. El criterio
  aplica a `OrdenCliente` y `OrdenEstacion` (tienen ciclo propio) y también a `Incidencia`
  (tiene `resolucion`, que cierra su ciclo: `aceptada`/`credito_cliente`/`descuento_afiliado`/
  `sin_resolucion`). **NO aplica** — porque el concepto ni siquiera tiene sentido ahí — a
  `OrdenClienteVoBoItem`, `OrdenEstacionDia` y `Verificacion`: son registros hijos sin
  existencia independiente de su padre (un ítem de checklist, un día de periodo, una
  evidencia) — nunca son "activos" o "inactivos" por sí mismos, viven y mueren con el padre.
- **¿Cómo se retira del sistema una orden capturada por error que nunca se confirmó?**
  **Hoy, literalmente no se puede.** Verifiqué el código (grep de `cancelada`/`CANCELADA` y de cada método de `OrdenClienteService`/`OrdenEstacionService`), no fue una suposición:
  `cancelada` existe en el `StrEnum` y en el `CHECK` de ambas tablas, pero **ningún método de
  servicio ni endpoint la asigna jamás** — ni `OrdenClienteService` ni `OrdenEstacionService`
  tienen un método `cancelar`, y `estatus_orden`/`estatus` no son campos editables vía los
  `Update` schemas genéricos. Una orden mal capturada hoy se queda visible para siempre en
  `recibida`/`capturada`, sin forma de ocultarla ni marcarla. Esto es un hueco real de
  implementación, no una decisión de diseño: el ESQUEMA está listo para soportar la
  cancelación (el valor existe, el `CHECK` lo permite), pero el CÓDIGO nunca construyó el
  camino para llegar ahí. No se corrige en esta tanda (no fue lo que se pidió y toca lógica de
  negocio, no el esquema) — queda anotado como pendiente en la ficha del módulo.
- **Decisión final:** se mantiene sin `activo` en las 6 tablas — el diseño (estado propio en
  vez de una bandera genérica) es correcto y no se revierte. Lo que SÍ hace falta, como tarea
  aparte y futura, es construir el endpoint de cancelación que el esquema ya permite.
- **Consecuencias:** F2/F3/F4, al construir sobre `OrdenCliente`/`OrdenEstacion`, deben saber
  que "está cancelada" se consulta por `estatus_orden`/`estatus`, nunca por un campo `activo`
  que no existe — y que, hasta que se implemente el endpoint de cancelación, ninguna orden en
  este sistema puede pasar realmente a `cancelada` por ningún camino soportado.
- **Confirmación tras la primera aplicación real a RDS (2026-08-10):** el hueco dejó de ser
  teórico — las órdenes de prueba que se capturen en RDS (base compartida, sin re-siembra)
  no se pueden retirar por ningún camino existente. Se reconsideró explícitamente si esto
  cambia la decisión de esquema: **no la cambia**. Agregar `activo` ahora tampoco resolvería
  el problema por sí solo — el hueco real es la AUSENCIA DE UN ENDPOINT que asigne
  `cancelada` (o que apague `activo`, si existiera); ninguna de las dos columnas tiene hoy un
  camino de código para llegar a "esto ya no cuenta". La decisión de diseño (estado propio,
  no una bandera redundante) se mantiene; lo que se degradó de "pendiente, futuro" a
  "urgente" es construir el endpoint mínimo de cancelación — recomendado ANTES de capturar
  datos de prueba en RDS, no después.

### ADR-036 — Tipos explícitos vía `with_variant` para fecha/hora/texto largo en `mssql` (F1)
- **Estado:** aceptada · **Fecha:** 2026-08-10 (F1, revisión del informe de migración a RDS)
- **Contexto:** al leer el DDL real generado para el dialecto `mssql` (Tanda 3 de la
  auditoría de migración a RDS), aparecieron dos comportamientos del dialecto de
  SQLAlchemy que nadie había pedido ni decidido:
  1. `sa.Date()`/`sa.Time()` a secas SOLO compilan a `DATE`/`TIME` nativos cuando el
     dialecto puede detectar la versión real del servidor (`server_version_info`,
     poblado al conectarse). En modo **offline** (`alembic ... --sql`, sin conexión —
     exactamente el modo con el que se generó la evidencia de esta auditoría) esa
     detección no existe, y el dialecto cae a `DATETIME` legado (compatible con SQL
     Server pre-2008). Confirmado con una prueba aislada del compilador.
  2. `sa.UnicodeText()` a secas compila a `NTEXT` (deprecado por Microsoft) de forma
     **incondicional** — a diferencia del punto 1, esto pasa igual en modo online.
- **Decisión:** no depender de la detección implícita del dialecto para ningún tipo de
  columna. Tres helpers nuevos en `core/db.py`, mismo patrón que el `datetime2()` ya
  existente (que ya forzaba `DATETIME2` explícito, sin que nadie lo hubiera visto como
  un problema hasta ahora):
  - `fecha_sql()` → `Date().with_variant(mssql.DATE(), 'mssql')`
  - `hora_sql()` → `Time().with_variant(mssql.TIME(), 'mssql')`
  - `texto_largo()` → `UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql')`
  Aplicados a las 9 columnas de fecha/hora y las 7 de texto largo de F1
  (`orden_cliente`, `orden_estacion`, `orden_estacion_dia`, `verificacion`,
  `incidencia`). Verificado con el SQL offline regenerado: 0 `NTEXT`, 0 `DATETIME`
  espurio, 7 `NVARCHAR(max)`, 7 `DATE`, 2 `TIME` — exactamente las columnas esperadas.
- **Por qué importa más allá de esta migración:** el punto 1 es la misma clase de
  bug que ADR-014 (`.is_(True)` sobre `BIT`) — un comportamiento que funciona bajo un
  supuesto implícito (ahí, el dialecto de pruebas; aquí, que siempre habrá una conexión
  viva al generar SQL) y que se rompe silenciosamente cuando ese supuesto deja de
  cumplirse. Con este ADR, el SQL offline generado por CUALQUIER migración futura del
  proyecto es un preview fiel de lo que se va a crear, sin depender de si quien lo
  generó tenía una conexión abierta.
- **F0 NO se toca en esta tanda.** `Categoria.descripcion_categoria` y
  `EmpresaFacturadora.direccion_empresa` usan `UnicodeText()` a secas — el mismo bug de
  `NTEXT` (sus propios comentarios de código incluso afirman, incorrectamente, que ya
  compilan a `NVARCHAR(MAX)`; confirmado que no es así). Si esas migraciones ya
  corrieron contra RDS, esas 2 columnas ya son `NTEXT` ahí — corregirlas requeriría un
  `ALTER TABLE` sobre una base compartida, fuera del alcance de esta migración de F1.
  **Queda como ticket aparte.** El proyecto queda temporalmente con dos formas de
  modelar texto largo (F0 sin corregir, F1 con `texto_largo()`) — se anota aquí
  explícitamente para que se lea como decisión de alcance, no como descuido.
- **Consecuencias:** módulos futuros (F2+) deben usar `fecha_sql()`/`hora_sql()`/
  `texto_largo()` de `core/db.py` para cualquier columna nueva de ese tipo, igual que ya
  se usa `datetime2()` — no `sa.Date()`/`sa.Time()`/`sa.UnicodeText()` a secas.

### ADR-037 — `Incidencia`: dos FK al mismo padre, consistencia garantizada por el único punto de creación (F1)
- **Estado:** aceptada · **Fecha:** 2026-08-10 (F1, revisión del informe de migración a RDS)
- **Contexto:** `Incidencia` tiene `verificacion_id` (FK a `Verificacion`) Y
  `orden_estacion_id` (FK a `OrdenEstacion`, denormalizada — la spec la pide así, "permite
  filtrar incidencias por OE sin pasar por Verificacion"). Pero la cadena real es
  `Incidencia.verificacion_id → Verificacion.orden_estacion_dia_id →
  OrdenEstacionDia.orden_estacion_id`: nada en el ESQUEMA obliga a que el
  `orden_estacion_id` denormalizado de una `Incidencia` coincida con el que resulta de
  seguir esa cadena — SQL Server no tiene una forma nativa de expresar esa validación
  cruzada entre tablas (un `CHECK` no puede referenciar otra tabla; requeriría un
  trigger, que este proyecto no usa).
- **Decisión: NO se cambia el modelo.** La desnormalización se justifica por consulta
  (evita un `JOIN` de 3 tablas para algo tan común como "incidencias de esta OE") y el
  costo de un trigger no se justifica hoy. En cambio, se documenta la garantía real y
  dónde vive:
  - **Hoy la consistencia SÍ está garantizada — pero por el servicio, no por el
    esquema.** El único punto de creación de `Incidencia` es
    `OrdenEstacionService.avanzar_reales` (`orden_estacion.py`): dentro de un mismo
    `for dia in dias` (donde `dias = self._repo.listar_dias(orden_estacion_id)`, es
    decir, SOLO días de la OE que se está procesando), la `Verificacion` se crea con
    `orden_estacion_dia_id=dia.orden_estacion_dia_id` y, si hay diferencia, la
    `Incidencia` se crea con `orden_estacion_id=obj.orden_estacion_id` (el mismo `obj`
    de toda la llamada) y `verificacion_id=verificacion.verificacion_id` (la que se
    acaba de crear, en la misma iteración). Ambos valores derivan de la MISMA OE por
    construcción — no hay forma de que diverjan mientras este sea el único punto de
    alta.
  - **Invariante a verificar si esto cambia**: la alta manual de `Incidencia` (ADR-031,
    diferida — hoy sin endpoint) DEBE revalidar esta misma cadena antes de insertar
    (que `Verificacion.orden_estacion_dia_id` resuelto a través de
    `OrdenEstacionDia.orden_estacion_id` coincida con el `orden_estacion_id` recibido),
    porque ya no habría una única función controlando ambos valores a la vez.
  - **Invariante a verificar en cualquier carga de datos futura** (migración de datos
    históricos, importación masiva): la misma revalidación aplica — una carga que
    escriba las dos FK de forma independiente podría romper la consistencia en
    silencio, sin que el esquema lo detecte.
- **Consecuencias:** ningún cambio de código. Este ADR es el registro de una garantía
  que hoy es real pero implícita, para que quien construya la alta manual de
  `Incidencia` o una carga de datos sepa exactamente qué debe revalidar.

### ADR-038 — `Verificacion.reconciliada` es hoy un campo muerto (F1)
- **Estado:** aceptada, CON pregunta de negocio abierta · **Fecha:** 2026-08-10
- **Contexto:** al confirmar cómo se asigna `reconciliada` (revisión externa del
  informe de migración a RDS), se verificó en el código que el único lugar donde se
  escribe es el `Verificacion(...)` que construye `OrdenEstacionService.avanzar_reales`
  — siempre `reconciliada=True`, literal, nunca `False`. Ningún otro método la lee para
  decidir nada (el cierre de la OE se basa en que existan las filas de `Verificacion`,
  no en el valor de este campo). Un `BIT NOT NULL` que siempre vale `1` y que nadie
  consulta no distingue nada — no cumple el propósito que le da la spec (habilitar el
  cierre solo cuando la reconciliación se acepta).
- **Por qué pasó esto:** la spec describe un flujo de 4 pasos (capturar realidad →
  revisar diferencias → reconciliar → cerrar) con puntos de decisión intermedios. La
  implementación de F1 comprime esos 4 pasos en una sola transacción atómica dentro de
  `avanzar_reales`: se capturan los reales, se generan las incidencias, se marca
  `reconciliada=True` y se cierra la OE, todo en el mismo commit. No existe hoy un
  estado intermedio donde haya evidencia capturada pero la diferencia todavía no esté
  aceptada — por diseño de la implementación actual, no por limitación técnica.
- **Decisión:** NO se cambia el flujo de `avanzar_reales` (es una decisión de negocio,
  no técnica — fuera del alcance de esta auditoría). SÍ se agrega `updated_at` nulable
  a `Verificacion` (ver ADR-036 para el criterio de tipos explícitos) por el costo
  asimétrico: el argumento de "registro inmutable, no necesita `updated_at`" solo se
  sostiene mientras `reconciliada` siga siendo un campo muerto. Si el negocio pide un
  flujo con verificaciones capturadas pero no reconciliadas, `reconciliada` pasaría a
  ser mutable y la columna haría falta — agregarla ahora es una línea; agregarla
  después de aplicar a RDS es un `ALTER TABLE` sobre una base compartida.
- **Pregunta de negocio abierta (para el área usuaria):** *¿Existe un momento en que la
  verificación queda capturada pero la diferencia todavía no se acepta (por ejemplo,
  Ventas necesita revisar antes de reconciliar), o el reporte del afiliado siempre se
  resuelve en el mismo acto — se captura y se reconcilia junto, sin un paso
  intermedio?* La respuesta determina si `avanzar_reales` necesita partirse en dos
  pasos (capturar → reconciliar) o si el diseño actual (todo en un acto) ya refleja
  correctamente cómo trabaja el área.
- **Consecuencias:** si la respuesta es "sí, hace falta un paso intermedio", esto
  afecta el flujo de servicio de F1 (nuevo estado, nuevo endpoint de "reconciliar") y
  probablemente el frontend (`RealesForm`) — trabajo futuro, no arrancado. Si la
  respuesta es "no, siempre se resuelve junto", `reconciliada` se queda como está
  (redundante pero inofensivo) y se puede considerar deprecarlo formalmente más
  adelante.

### ADR-039 — `ROUND(x, 2)` en CHECK de suma exacta: SQLite no tiene DECIMAL de punto fijo (F1)
- **Estado:** aceptada · **Fecha:** 2026-08-10
- **Contexto:** al agregar los primeros CHECK de IGUALDAD entre montos calculados
  (`importe_oir + importe_emisora = importe_estacion`, `total_oir = importe_oir +
  iva_oir`, `total_emisora = importe_emisora + iva_emisora` — Tanda 4c/4d de la
  auditoría de migración a RDS), la re-siembra de la demo en SQLite falló para 1 de 18
  `OrdenEstacion` (`oe8`): `44478.00 + 7116.48` da `51594.48` exacto en aritmética
  `Decimal` de Python, pero SQLite almacena columnas `NUMERIC` como `float64` (no tiene
  tipo decimal de punto fijo nativo). En `float64`, `44478.0 + 7116.48 =
  51594.479999999996`, que no coincide bit a bit con el `float64` de `51594.48`
  guardado por separado — el CHECK sin ajustar rechazaba una fila matemáticamente
  correcta. Confirmado con un diagnóstico aislado (`sqlite3` en memoria) que el mismo
  patrón se reproduce con cualquier suma de dos `NUMERIC` cuyo resultado no sea
  exactamente representable en `float64`.
- **Por qué SQL Server no tiene este problema:** `NUMERIC(14,2)`/`DECIMAL(14,2)` en
  SQL Server es de punto fijo real (aritmética decimal, no floating point) — la misma
  suma ahí da el resultado exacto siempre, sin importar los valores. Todos los CHECK de
  rango (`>= 0`, `<= 100`) agregados en tandas anteriores nunca mostraron este problema
  porque una desigualdad es robusta a 1 ULP de ruido de `float64`; una IGUALDAD entre
  dos sumas calculadas por separado no lo es. Este es el primer CHECK de este tipo
  (suma exacta) que entra a la migración — por eso el problema no había aparecido antes.
- **Decisión:** envolver ambos lados de los 3 CHECK de suma exacta en `ROUND(x, 2)`:
  `ROUND(importe_oir + importe_emisora, 2) = ROUND(importe_estacion, 2)`, y análogo
  para `total_oir`/`total_emisora`. `ROUND` es una función estándar tanto en SQLite
  como en T-SQL. En SQL Server es un no-op inofensivo (los valores ya son exactos); en
  SQLite neutraliza el ruido de `float64` sin enmascarar una violación real — verificado
  con el mismo diagnóstico aislado que una diferencia de 1 centavo completo (no de
  redondeo) sigue siendo rechazada por el CHECK con `ROUND`.
- **Alternativas descartadas:** (a) quitar los 3 CHECK — pierde la protección real en
  RDS por una limitación que solo existe en el entorno de prueba local; (b) ajustar los
  valores del mock de `seed_dev.py` para evitar la colisión de `float64` — no resuelve
  el problema de fondo (cualquier combinación futura de datos podría volver a
  coincidir con un límite de `float64`), solo lo pospone a la próxima coincidencia.
- **Consecuencias / alcance del CHECK:** cualquier CHECK futuro que compare una
  IGUALDAD entre dos expresiones de `NUMERIC` calculadas independientemente debe
  envolverse en `ROUND(x, N)` con la misma escala de la columna — no es exclusivo de
  `orden_estacion`. Los CHECK de desigualdad (`>=`, `<=`) no necesitan este tratamiento.
- **Implicación mayor — el problema no es del CHECK, es de la BASE DE DESARROLLO
  COMPLETA:** el hallazgo no es una curiosidad puntual de 3 constraints. **Toda columna
  `Numeric`/`DECIMAL` del proyecto se guarda como `float64` en la SQLite de desarrollo**,
  no solo las 3 que tienen CHECK de suma exacta. La regla del proyecto (`backend/CLAUDE.md`
  §Convenciones, ADR-015) es *"montos como `NUMERIC`, nunca float — es un sistema
  financiero"*; en la SQLite local, el MOTOR DE ALMACENAMIENTO viola esa regla por su
  cuenta y en silencio, sin que el código Python haga nada mal. Consecuencia concreta:
  **toda prueba que hoy lee un monto de la base (subtotal, IVA, total, importe_oir/
  importe_emisora, y cualquier futuro monto de F2/F3) y lo compara con `==` NO está
  validando aritmética decimal exacta** — está validando aritmética `float64`, que
  coincide con la decimal exacta LA MAYORÍA de las veces pero no todas (como `oe8`
  demostró). El cálculo en Python sigue siendo exacto (`Decimal`, ADR-015); lo que deja
  de ser exacto es el viaje de ida y vuelta a través de SQLite. Una prueba que hoy pasa
  comparando montos exactos está probando algo distinto de lo que va a pasar en
  producción contra SQL Server (ahí sí sería exacto, siempre) — coincide por suerte de
  los valores concretos, no por garantía del mecanismo.
- **Misma familia que ADR-014:** ADR-014 (columnas `BIT`, `.is_(True)` compila distinto
  en cada dialecto — pasaba en SQLite, fallaba en RDS) y este ADR-039 (`NUMERIC` se
  almacena distinto en cada dialecto — puede fallar una IGUALDAD en SQLite que sería
  exacta en RDS) son la MISMA clase de riesgo: **la SQLite local (ADR-028) no es un
  sustituto fiel de SQL Server para todo lo que depende del dialecto** — solo para el
  esquema/las migraciones (que sí se auditan offline contra `mssql`, tandas 2-4d) y para
  la lógica de negocio que no toca tipos específicos del motor. ADR-014 lo demostró para
  `BIT`; este ADR lo demuestra para `NUMERIC`. Cualquier prueba que dependa de un tipo de
  dato con semántica distinta entre SQLite y SQL Server (BIT, NUMERIC, posiblemente
  otros aún no encontrados) hereda el mismo riesgo.
- **Advertencia para F2 (Facturación) y F3 (Cobranza/Pagos):** ambas fases van a tener
  MUCHA más aritmética de dinero que F1 (subtotales/IVA/totales de factura, comisiones,
  conciliación de pagos parciales, redondeos de requisiciones). Las pruebas en SQLite
  local **no bastan** para certificar que esa aritmética es correcta en producción — solo
  certifican que el CÓDIGO PYTHON (`Decimal`) es correcto, que ya lo garantiza ADR-015
  independientemente de la base. Cualquier CHECK de igualdad sobre montos en F2/F3 debe
  nacer ya con `ROUND(x, 2)` (no esperar a que la re-siembra lo descubra, como pasó aquí)
  — y si en F2/F3 se agregan pruebas que verifiquen sumas o cuadres de montos LEYENDO DE
  LA BASE (no solo comparando los `Decimal` en memoria antes de persistir), esas pruebas
  necesitan corroborarse contra SQL Server real al menos una vez, no basta con que pasen
  en SQLite.
- **Qué verificar contra SQL Server real, una vez aplicada esta migración:** (1) que los
  3 CHECK de suma exacta con `ROUND` compilan y se pueden crear sin error de sintaxis en
  T-SQL (confirmado por lectura del DDL offline, sección 8 del informe — pendiente de
  confirmación al aplicar); (2) insertar al menos una fila con montos que en SQLite
  hubieran producido el mismo tipo de colisión de `float64` (p.ej. replicar los valores
  de `oe8`) y confirmar que el CHECK pasa SIN necesitar `ROUND` — si alguna vez fallara
  en SQL Server, sería señal de que la premisa de este ADR (NUMERIC es de punto fijo
  real ahí) está mal, y habría que investigar de inmediato; (3) que ninguna de las
  pruebas de F1 que comparan montos empieza a fallar contra RDS de forma distinta a como
  pasa en SQLite (correr la suite de pruebas de integración, si existe, contra un
  ambiente de QA con RDS antes de considerar F2/F3 "probado").

### ADR-040 — Admin es superusuario (WRITE) en todos los módulos, no solo Catálogos (F1)
- **Estado:** aceptada · **Fecha:** 2026-08-11
- **Contexto:** la matriz RBAC de la propuesta Pointwise (§9 "Roles y matriz de
  permisos") le da al área Admin captura (C) solo sobre Catálogos y Seguridad —
  sobre Órdenes (F1), y por extensión sobre cualquier módulo futuro, la propuesta
  original solo le da lectura (L). El equipo pidió explícitamente ampliar esto: que
  el usuario `dev.admin`/área `admin` tenga todos los permisos de todas las pantallas,
  sin excepción.
- **Decisión:** `Area.ADMIN` es superusuario — siempre `Acceso.WRITE` — sobre CUALQUIER
  módulo de la matriz `RBAC` (`app/core/security.py`), presente o futuro. Se implementó
  centralizado en `_nivel()` (verifica `area is Area.ADMIN` ANTES de consultar el dict
  `RBAC` por módulo), no repartido módulo por módulo — así un módulo nuevo (F2, F3...)
  no necesita acordarse de agregar la entrada de Admin. Se retiraron las entradas
  explícitas `Area.ADMIN: Acceso.WRITE` (en `catalogos`, quedaba redundante) y
  `Area.ADMIN: Acceso.READ` (en `_LECTURA_ORDENES`, quedaba contradictoria con el nuevo
  comportamiento) de la matriz de datos, para que no haya dos fuentes de verdad
  describiendo el acceso de Admin.
- **Es una desviación deliberada de la propuesta, no un descuido:** se preguntó
  explícitamente al equipo antes de tocar el código (regla del proyecto: no
  "mejorar" la matriz de permisos por cuenta propia) — se ofrecieron dos alcances
  (bypass solo para el usuario de desarrollo `dev.admin`, o cambio real de la matriz
  para el área `admin`) y el equipo eligió el segundo.
- **Fuera de alcance de este ADR:** el canal de comisiones de F1
  (`PATCH /clientes/{id}/comisiones`) no pasa por esta matriz — su autorización es un
  chequeo de área explícito dentro del propio servicio (`Area.DIRECCION`/`Area.ADMIN`,
  ver `orden_cliente.py`), que ya incluía a Admin desde la Tanda 5; no se tocó. Los
  permisos a nivel de campo (`PermisoCampo`, F5) tampoco se tocan — son un mecanismo
  distinto, pendiente de construirse como entidad real.
- **Consecuencias:** cualquier módulo nuevo que agregue su propia entrada a `RBAC` NO
  necesita (ni debe) listar a `Area.ADMIN` — ya la tiene garantizada por `_nivel()`. Si
  en el futuro el equipo decide que Admin SÍ debe quedar limitado en algún módulo
  específico (p.ej. por una regla de segregación de funciones en F3/Tesorería), ese caso
  necesitaría una excepción explícita en `_nivel()` (hoy no existe ninguna) — no alcanza
  con quitarlo de la matriz de datos, porque el superusuario ya no la consulta.

### ADR-041 — Proveedor de autenticación intercambiable + sesión JWT (F5-00)
- **Estado:** aceptada · **Fecha:** 2026-08-12 (F5-00, adelanto consciente de F5) ·
  **sustituye a ADR-008** en cuanto al proveedor por defecto (el modo por headers sobrevive
  como un adaptador más, con sus mismas restricciones).
- **Contexto:** el sistema se identificaba con headers de desarrollo (`X-Dev-User`/
  `X-Dev-Area`, ADR-008), lo cual (1) no sirve para demostrar el sistema al cliente y (2)
  deja sin base el RBAC que F1 en adelante necesita. El SSO corporativo sigue
  `[[POR LLENAR]]`: no se puede depender de Azure AD para avanzar, pero tampoco conviene
  cablear un login local que después haya que arrancar de raíz.
- **Decisión:**
  1. **Puerto + adaptadores seleccionables por entorno**, replicando el patrón del
     almacenamiento S3 (ADR-027): `app/core/auth/port.py` define `AuthProviderPort`
     (`autenticar` / `resolver_usuario`) y `get_auth_provider()` es el ÚNICO punto de
     decisión, según `AUTH_PROVIDER`. Tres adaptadores: `local` (implementado),
     `dev_headers` (ADR-008 tal cual) y `azure_ad` (**interfaz preparada, implementación
     diferida**: falla ruidosamente, nunca cae en silencio a otro proveedor).
  2. **`local` es el DEFAULT** para que las demos al cliente siempre pasen por la pantalla
     de login. `dev_headers` lo activa cada quien en su `.env` para no loguearse en cada
     prueba local, y **solo funciona con `APP_ENV=development`** (401 fuera de ahí; la
     comprobación vive en el adaptador para que el código de error siga siendo
     `no_autenticado` y no un 500 de configuración).
  3. **Ubicación en `core/auth/`, no en `integrations/`:** la identidad la consume *cada*
     endpoint (como `security.py`, `audit.py`, `field_permissions.py`) y el adaptador local
     necesita la tabla `usuario`; un paquete bajo `integrations/` importando un modelo de
     `modules/` invertiría la dirección anti-corrupción. Cuando se implemente Azure AD, su
     cliente OIDC sí irá a `integrations/azure_ad/` y el adaptador lo consumirá.
  4. **Sesión JWT** (HS256, firmada con `SECRET_KEY` del entorno), con claims de identidad
     y área, **8 h configurables** (`JWT_EXPIRA_HORAS`, una jornada laboral). El token dice
     quién dice ser; el **estado del usuario (`activo`, `area`) se relee de la BD en cada
     request**, de modo que desactivar a alguien o cambiarle el área surte efecto de
     inmediato en lugar de esperar a que expire su token. Fuera de `development` se
     RECHAZA firmar o validar con la `SECRET_KEY` de ejemplo del repositorio.
  5. **Credencial = email** (único e indexado); `nombre_usuario` no lo es. Contraseñas con
     **bcrypt** (`app/core/auth/passwords.py`, único lugar que conoce el algoritmo; migrar
     a argon2id sería reescribir ese archivo). **Mensaje de error único** para usuario
     inexistente / contraseña incorrecta / usuario inactivo / usuario sin contraseña, y
     verificación señuelo cuando no hay hash, para que **ni el mensaje ni el tiempo**
     revelen si un correo está dado de alta.
  6. **Contraseña inicial del seed `dev.admin` por ENTORNO**, no versionada: la migración
     lee `SEED_ADMIN_PASSWORD` / `SEED_ADMIN_PASSWORD_HASH` y, si no están, deja
     `password_hash` en NULL (fail-closed, sin contraseñas por defecto). Un hash bcrypt
     escrito en una migración es un secreto versionado y atacable offline; la skill
     `migraciones-sqlserver` lo prohíbe.
  7. **Dos destinos de traza, según la naturaleza del dato** (gestión de usuarios):
     cambiar `area` o `activo` —los campos que otorgan o quitan acceso— se registra en
     **`LogCambioParametro`** con valor anterior/nuevo, reutilizando el mecanismo de
     F0-03. El **reseteo de contraseña** NO: no tiene "valores" que mostrar en el panel de
     detalle de una entidad, así que va a un **log de seguridad** mínimo
     (`core/security_log.py`, logger `grcoir.seguridad`) que registra quién, a quién,
     desde qué IP y cuándo, **sin la contraseña ni el hash**. Ese módulo es la costura
     para la bitácora de seguridad FORMAL (tabla consultable + pantalla) de F5 pleno: se
     reescribe el cuerpo de una función, no los llamadores.
  8. **El RBAC no cambió de forma**: `requiere_permiso` y la matriz área × módulo siguen
     siendo los mismos datos en `core/security.py`; lo único que cambió es **de dónde sale
     el `CurrentUser`**. Por eso los 11 catálogos de F0 y sus pruebas **no se tocaron**
     (el `conftest` fija `dev_headers` para ellas). Se añadió la entrada `"usuarios"`,
     exclusiva de Admin **incluso en lectura**, porque el padrón de usuarios no es un
     catálogo consultable por las demás áreas. Al integrarse con F1 quedó como
     `"usuarios": {}` (diccionario vacío) siguiendo el **ADR-040**: Admin obtiene WRITE de
     `_nivel()` en todos los módulos, así que ninguna entrada nueva debe listarlo.
  9. **Frontend — la sesión es infraestructura compartida.** El token vive en
     `shared/lib/session.ts` (sin React, porque lo consumen tanto el `apiClient` como el
     provider) y el estado de sesión en `modules/auth/`. Tres decisiones que sostienen el
     resto:
     - **Shim `currentUser`** (`shared/lib/currentUser.ts`): las 14 pantallas de F0 leen la
       identidad de forma síncrona; en vez de migrarlas todas, el `SessionProvider` mantiene
       ese objeto sincronizado. Cero churn y cero conflicto con la rama de F1 en curso. La
       migración a `useSession()` es un PR aparte. El mismo módulo expone el cierre de
       sesión, para que `shared/ui/AppHeader` no tenga que importar un módulo de negocio.
     - **Al montar se llama `/auth/me`**, no se confía en datos guardados: valida el token y
       trae el área fresca. De ahí el estado `cargando`, sin el cual recargar la página
       rebotaría a /login antes de que la respuesta llegara.
     - **El 401 de `/auth/login` NO cuenta como sesión expirada** (si no, escribir mal la
       contraseña expulsaría al usuario de la propia pantalla de login).
  10. **Destino después de iniciar sesión.** Se vuelve a la pantalla interrumpida **solo si
     la sesión se perdió trabajando** (401 del backend). Un login desde cero —primera
     visita, URL escrita a mano, logout explícito o token viejo en el navegador— entra al
     **Dashboard**, que es el Home real del sistema.
  11. **Color: el login usa el rojo de MARCA, no el color de fase.** Se añadió el token
     `--grc-red: #D73347` (extraído del logo) en `theme.css`, distinto de `--red-bg`/
     `--red-text`, que son semánticos de error. La aplicación es por **scope**: redefinir
     los tokens `--phase-*` dentro de `.login-page` (y de `.phase-f5`) tiñe la pantalla
     completa —botones, foco de campos, tag de fase, sidebar— **sin duplicar una sola
     regla** ni afectar a las demás fases, que siguen con su color. `ExplorerLayout` acepta
     `phaseClass` para eso. Esto generalizó `.btn-phase:hover`, que tenía el morado
     hardcodeado, a un token `--phase-hover` (mismo valor en `:root`, cero cambio visual).
  12. **`RequireArea` explica en vez de redirigir en silencio.** Es solo UX —el backend
     valida el RBAC en cada endpoint—, pero un no-admin que abre `/seguridad` lee un mensaje
     claro con salida al Inicio; una redirección muda se lee como que la app está rota.
- **Consecuencias:** activar Azure AD será implementar un adaptador y cambiar una variable,
  sin tocar routers ni servicios. `Area`/`CurrentUser` se movieron a `core/auth/identity.py`
  para romper el ciclo `security ↔ auth`, pero **se re-exportan desde `core/security.py`**:
  todos los imports existentes siguen funcionando. Nuevas dependencias formalizadas en
  `pyproject.toml`: `pyjwt` y `bcrypt` (no `passlib`, sin releases desde 2020 y roto con
  bcrypt ≥ 4). `CurrentUser` ganó `usuario_id`/`email` opcionales (en `dev_headers` van en
  `None`: no hay registro detrás).
- **Limitaciones conocidas y riesgos aceptados** (a revisitar en **F5 pleno**):
  - **Sin control de intentos fallidos ni rate limiting** en el login. Un contador en
    memoria sería inútil con varios workers; hacerlo bien exige almacén compartido. Riesgo:
    fuerza bruta contra un correo conocido. Mitigación parcial: bcrypt con costo 12 encarece
    cada intento.
  - **Token en `localStorage` del navegador** (frontend, tanda 3): simple y suficiente para
    una SPA en otro origen, pero **expuesto a XSS**. La alternativa (cookie `httpOnly` +
    CSRF) es más segura y cambia CORS y el flujo completo.
  - **Sin refresh token**: al expirar las 8 h se vuelve a iniciar sesión.
  - **`logout` es un no-op de servidor**: el token es *stateless* y sigue siendo válido
    hasta expirar aunque el cliente lo descarte. Si el negocio exige invalidación inmediata,
    habrá que añadir una lista de revocación.
  - **Sin política de rotación ni caducidad de contraseñas**, y sin "forzar cambio en el
    primer inicio de sesión".

### ADR-042 — Adjuntos de Órdenes: endpoint genérico + lista blanca de extensiones (F1)
- **Estado:** aceptada · **Fecha:** 2026-08-20 (F1).
- **Contexto:** 5 campos de "adjuntar archivo" en Órdenes (`OrdenCliente.
  archivo_orden_original_path`/`odc_cerrada_ref`/`carta_conciliacion_ref`,
  `OrdenEstacion.reporte_programados_ref`/`reporte_reales_ref`) eran "simulados": el input
  de tipo `file` solo capturaba `nombre del archivo`, nunca se leía ni subía nada. El
  almacenamiento S3 real ya existe (ADR-027), pero atado 1:1 a Contrato (subida/lista/
  descarga/borrado por `numero_contrato`, solo PDF).
- **Decisión:**
  1. **Un solo endpoint genérico** (`POST`/`GET /api/v1/ordenes/adjuntos?tipo=...`,
     `app/modules/ordenes/adjuntos.py`) para los 5 campos, en vez de replicar el CRUD
     completo de Contrato por entidad: son referencias de UN archivo por campo (no listas),
     así que no hace falta listar/borrar — subir uno nuevo simplemente reemplaza la
     referencia. `tipo` (enum `TipoAdjuntoOrden`) decide el prefijo del bucket
     (`ordenes/odc/`, `ordenes/cierre/odc/`, `ordenes/cierre/carta/`,
     `orden_estacion/reportes/reales|programados/`) — mismo bucket que Contrato
     (`S3_BUCKET_CONTRATOS`), prefijos distintos para no mezclarlos. La clave incluye un
     UUID (`<uuid_hex>_<nombre>`) porque, a diferencia de Contrato, no siempre hay un
     "número" estable para agrupar antes de que la orden exista (alta de OC).
  2. **Lista blanca de extensiones ampliada** (`leer_adjunto` en
     `integrations/almacenamiento/documentos.py`, junto a `leer_pdf` que sigue intacto para
     Contrato): `pdf, doc, docx, xls, xlsx, jpg, jpeg, png` — documentos + imágenes,
     deliberadamente SIN ejecutables/scripts. Cada extensión valida su propia firma de
     contenido (*magic bytes*: `%PDF-`, `\xFF\xD8\xFF`, `\x89PNG...`, `PK\x03\x04` para
     OOXML, OLE2 para legacy) — no basta con renombrar un `.exe` a `.pdf` para subirlo.
  3. **`archivo_orden_original_path` es un campo REAL de la spec BD v2** ("PDF/imagen de la
     orden original recibida del cliente", VARCHAR(500)) que ya existía en el modelo y en
     `OrdenClienteRead`, pero nunca se expuso en `OrdenClienteCreate`/`Update` — por eso el
     campo "Adjuntar ODC" del formulario no tenía dónde persistir. Se agregó a ambos
     schemas; **sin migración** (la columna ya existía). El frontend conserva el nombre
     interno `odc_pdf_ref` (usado en `register`/`watch` de `OrdenClienteForm`) y lo traduce
     en `adapters/toApi.ts`/`fromApi.ts` — único lugar que conoce ambos nombres.
  4. **Descarga solo por prefijos conocidos** (`_PREFIJOS_DESCARGABLES`): el endpoint de
     descarga rechaza con 404 cualquier `ref` que no empiece con uno de los 5 prefijos de
     Órdenes, aunque compartan bucket con Contrato — no debe poder usarse para leer
     `contratos/...` sin pasar por el RBAC de Catálogos.
- **Consecuencias:** los 5 campos ahora suben y persisten de verdad; la descarga sigue
  sirviéndose por el backend (bucket privado), nunca por URL pública, mismo criterio que
  Contrato. `odc_cerrada_ref`/`carta_conciliacion_ref`/`reporte_*_ref` ya eran columnas
  reales (ADR-030/034): solo les faltaba un mecanismo de subida real, no un cambio de
  esquema.

> **Nota de numeración:** el **ADR-043** (un solo `.env` en la raíz, `envDir` de Vite)
> está redactado en la rama `fix/ordenes-correcciones-f1`, todavía sin mergear a `main`.
> Los ADR de F2 arrancan en 044 para no colisionar cuando ambas ramas se integren.

### ADR-044 — F2 usa DOS claves de RBAC (`facturacion` y `costos`) para UN solo módulo de código
- **Estado:** aceptada · **Fecha:** 2026-08-24 (F2, tanda 1).
- **Contexto:** la ficha de F2 pide áreas de CAPTURA distintas por ENTIDAD dentro del
  mismo módulo: Facturación captura `FacturaCliente`; CxP captura `FacturaAfiliado`,
  `FacturaAgencia` y `CostoAdicional`. Pero `_nivel(modulo, area)` en `core/security.py`
  resuelve el permiso **por módulo**, no por entidad: `RBAC["facturacion"]` es un solo
  diccionario área→acceso. Con una sola clave, o Facturación podía capturar costos o CxP
  podía capturar facturas de cliente — ninguna de las dos aceptable.
- **Decisión:** dos claves de permiso, `facturacion` (WRITE: Facturación) y `costos`
  (WRITE: CxP), sobre **un solo paquete de código** `app/modules/facturacion/`. Lo que se
  parte es el permiso, no el módulo: la ficha pide las 5 entidades juntas por su
  acoplamiento, y separarlas en dos paquetes obligaría a que uno importara del otro. Los
  nombres no son inventados: son exactamente los dos que el mapa fases→módulos del
  `CLAUDE.md` §4 ya predefine para F2 (`facturacion`, `costos`).
  Se descartó la alternativa de una clave única + chequeo de área explícito en cada
  servicio de costos: repetiría en 3 servicios lo que la matriz resuelve como datos, que
  es justo lo que el `backend/CLAUDE.md` prohíbe ("datos, no ifs repartidos").
- **Consecuencias:** el módulo tiene permisos NO uniformes — `/facturacion/clientes/*`
  exige `facturacion:*` y el resto `costos:*`. Queda documentado en el `__init__.py` del
  módulo, en el `router.py` y en `API-CONTRACT.md`, porque es lo primero que sorprende al
  leer el código. Admin sigue sin listarse en ninguna de las dos matrices: `_nivel()` le
  da WRITE en todo módulo presente y futuro (ADR-040). El chequeo de área explícito SÍ se
  usa, pero solo donde la matriz no alcanza: autorizar una factura de proveedor exige
  Dirección/Admin (mismo patrón que el canal de comisiones de F1).

### ADR-045 — `LIKE` con clases de caracteres (`[0-9]`) es T-SQL puro: no usarlo en CHECK
- **Estado:** aceptada · **Fecha:** 2026-08-24 (F2, tanda 1).
- **Contexto:** `CostoAdicional.periodo_contable` es `VARCHAR(7)` con formato `YYYY-MM`
  (spec). Para garantizarlo en el esquema se escribió el CHECK natural en T-SQL:
  `periodo_contable LIKE '[0-9][0-9][0-9][0-9]-[0-9][0-9]'`. **SQL Server lo soporta;
  SQLite no.** SQLite no implementa clases de caracteres en `LIKE`: compara `[0-9]`
  literalmente, así que el patrón no calza NUNCA y el CHECK rechaza todos los valores,
  incluido el válido `'2026-02'`. Lo detectó la prueba de la Tanda 1 (la inserción del
  dato correcto falló), y se confirmó aislado con `sqlite3` en memoria: el patrón devuelve
  0 para los 4 valores probados, válidos e inválidos por igual.
- **Decisión:** usar `LIKE '____-__'`. El comodín de UN carácter (`_`) sí es estándar en
  ambos motores. Garantiza la FORMA (7 caracteres con guion en la quinta posición:
  rechaza `'feb-2026'` y `'2026-2'`), pero no que los caracteres sean dígitos — eso lo
  valida el schema Pydantic en la captura. Es la garantía más fuerte que se puede expresar
  de forma **portable** en una constraint de tabla.
- **Por qué importa más allá de este campo:** es la misma clase de bug que ADR-014
  (`.is_(True)` sobre `BIT`), ADR-036 (`sa.Date()` cayendo a `DATETIME` offline) y ADR-039
  (`NUMERIC` como float64 en SQLite) — una construcción que funciona bajo un supuesto
  implícito de dialecto y se rompe en silencio en el otro. Con la diferencia de que este
  falla en el sentido MENOS habitual: el DDL habría pasado cualquier revisión pensada para
  SQL Server, y lo que se habría roto es el desarrollo local completo. **Regla para
  módulos futuros: cualquier CHECK que use `LIKE` debe limitarse a `%` y `_`; si hace
  falta validar un formato más fino, va en el schema Pydantic, no en la constraint.**

[[Agregar aquí cada nueva decisión: ADR-046, ...]]
