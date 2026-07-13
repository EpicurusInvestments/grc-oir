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

[[Agregar aquí cada nueva decisión: ADR-021, ...]]
