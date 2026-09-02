# Módulo F1 — Órdenes · Fase: F1

> Ficha de alcance de TODO el módulo `ordenes` (las 4 entidades de F1 se implementan
> juntas por su fuerte acoplamiento: OC → OE → Verificacion → Incidencia). Referencias:
> spec BD v2 (`docs/referencias/bd_especificacion_grc_oir_texto_extraido.txt`, sección
> "FASE 1 — Órdenes de Transmisión") y `Fase_1_-_Ordenes.html`. Esta ficha se escribió
> retroactivamente al cerrar la Tanda 3 (cubre Tandas 1-3); se sigue completando en las
> Tandas 4-6.

## Propósito

Cubrir el ciclo operativo central: Ventas captura la orden recibida del
anunciante/agencia (`OrdenCliente`), el sistema la deriva en órdenes internas por
estación (`OrdenEstacion`, 1 → N), se verifica lo realmente transmitido
(`Verificacion`) y se registran las diferencias (`Incidencia`). El cierre de todas las
OE de una OC habilita la facturación (F2).

## Entidades (spec BD v2 + extensiones aditivas)

### OrdenCliente (36 campos spec + 8 aditivos)
PK `orden_id`. FKs a `EmpresaFacturadora`, `Vendedor` (principal/secundario),
`Anunciante`, `Agencia`, `Contrato`, `Marca`, `Categoria`, `Usuario` (`created_by`).
Calculados (servicio, `Decimal`): `anio_venta`/`mes_venta` (de `fecha_venta`),
`total_dias_campania` (`DATEDIFF+1`), `subtotal`/`iva`/`total`.

**Extensiones aditivas** (no están en la spec, aprobadas explícitamente):
- **Comisiones snapshot** (`porcentaje_comision_vendedor_principal_snap`,
  `_vendedor_secundario_snap`, `_agencia_snap` — ADR-029): fijadas al vender, no cambian
  si el catálogo cambia después. Auditadas en `LogCambioParametro` (`entidad="OrdenCliente"`).
- **Campos de cierre** (`odc_cerrada_ref`, `carta_conciliacion_ref`,
  `cierre_sin_odc_cerrada`, `cierre_sin_carta_conciliacion`, `fecha_cierre` — ADR-034):
  snapshot de lo que faltaba AL MOMENTO del cierre.
- **Adjuntos reales** (`archivo_orden_original_path`, `odc_cerrada_ref`,
  `carta_conciliacion_ref`, `reporte_programados_ref`, `reporte_reales_ref` — ADR-042): se
  suben de verdad vía `POST /ordenes/adjuntos` (lista blanca de extensiones + magic bytes),
  no solo se captura el nombre del archivo.

**Checklist de Vo.Bo.** — tabla hija `OrdenClienteVoBoItem` (ADR-033), NO JSON: 10 ítems
fijos (`ITEMS_VOBO`), cada uno con `completado`/`usuario_id`/`fecha_completado`.

### OrdenEstacion (27 campos spec + 5 aditivos)
PK `orden_estacion_id`. FK a `OrdenCliente`, `Contrato`, `Anunciante`, `Vendedor`,
`Agencia`, `Categoria`, `Estacion`, `Plaza`, `Usuario`. Calculados (servicio):
`importe_estacion` (agregado de días), `importe_oir`/`iva_oir`/`total_oir`,
`importe_emisora`/`iva_emisora`/`total_emisora`.

**Desviación aditiva clave (ADR-030):** la spec modela `fecha_transmision`/
`hora_inicio`/`hora_fin`/`spots_solicitados`/`spots_asignados`/`spots_faltantes` como
campos PLANOS (una fila = un día), pero la propia spec autoriza "agrupar por rango" —
se usa esa lectura: esos campos viven en la tabla hija **`OrdenEstacionDia`** (una fila
por día), con 3 capas de captura (asignado → programado → verificado, ver docstring de
`orden_estacion.py`). `spots_faltantes` deja de persistirse: se calcula al leer.
`testigos_url`/`testigos_ubicacion_alterna`/`notas_transmision`/`reporte_programados_ref`/
`reporte_reales_ref` (tampoco en spec, mismo ADR) viven en `OrdenEstacion` (se capturan
una vez por lote, no por día).

`OrdenEstacion.estatus` es un ciclo de vida **propio e independiente** del de
`OrdenCliente` (confirmado en la spec): cada OE cierra por su cuenta; `OrdenCliente`
pasa a `orden_cerrada` cuando TODAS sus OE están `cerrada` (se valida en el servicio).

**PDFs de Orden interna (ADR-043/044, sin spec previa — nueva funcionalidad):** 3 PDFs
previsualizables desde el detalle de "Órdenes internas" — "Orden de servicio" (2.1),
"Horarios programados" (2.2) y "Horarios reales de transmisión" (2.3) —, generados AL
VUELO (`GET /ordenes/estaciones/{id}/pdf/servicio|programados|reales`, sin guardar
archivo) con `reportlab`. El de servicio siempre está disponible; los de
programados/reales devuelven 400 si la OE no llegó todavía a esa etapa. El nombre de
empresa/domicilio que aparece en cada PDF sale de `EmpresaFacturadora` (catálogo F0), no
de un texto fijo. Encabezado con logos de OIR y Grupo Radio Centro (`app/assets/logos/`
— sustituibles sin tocar código, ver README ahí). En el frontend, los 3 botones viven en
la barra de acciones del footer (NO en una sección "Documentos") y abren un visor de PDF
en una pestaña nueva con barra de imprimir/guardar, en vez de forzar la descarga.

### Verificacion (spec, 10 campos)
PK `verificacion_id`. FK **adaptada** a `orden_estacion_dia_id` (la spec la ancla a
`orden_estacion_id`; se ancla al día porque la propia spec autoriza esa granularidad —
ver ADR-030). Tabla REAL persistida: revierte una decisión previa del frontend-only
(E.1, tomada sin acceso a la spec) que la modelaba como vista derivada.

### Incidencia (spec, 11 campos)
PK `incidencia_id`. FK a `Verificacion` y (denormalizada) a `OrdenEstacion`. Modelo
**híbrido** (ADR-031): la generación automática (al capturar una `Verificacion`) solo
puede inferir `faltante`/`excedente`; los otros 3 tipos de la spec (`cambio_horario`,
`cambio_fecha`, `spot_no_emitido`) quedan para alta manual (Tanda 5). `resolucion`
(spec) se agrega completo, default `pendiente`.

## Estados

| Entidad | Campo | Valores |
|---|---|---|
| OrdenCliente | `estatus_orden` | recibida → capturada → en_transmision → en_verificacion → orden_cerrada → facturada → cobrada │ cancelada |
| OrdenCliente | `estatus_pago_afiliado` / `estatus_pago_agencia` | pendiente │ en_revision │ pagado |
| OrdenEstacion | `estatus` | borrador → asignada → en_transmision → en_revision → cerrada │ cancelada |
| Incidencia | `resolucion` | pendiente → aceptada │ credito_cliente │ descuento_afiliado │ sin_resolucion |

Vocabulario **exacto de la spec** — el prototipo HTML aprobado usa un vocabulario "v5"
distinto (`orden_cliente_sin_vobo`, `asignada_afiliado`, etc.); el mapeo entre ambos vive
en el adaptador del frontend (Tanda 4), no en el backend.

## Roles / permisos

RBAC del módulo `ordenes` (propuesta §9, columna "Órdenes" — grounded, no inventado):

| Área | Acceso |
|---|---|
| Ventas | Captura (`ordenes:crear`/`editar`, implica lectura) |
| Facturación, Tesorería, CxC, CxP, Dirección/Finanzas, Admin | Solo lectura (`ordenes:leer`) |
| Nóminas | Sin acceso |

A diferencia de Catálogos (donde Admin escribe), aquí **Admin es solo lectura** — la
propuesta no le da captura sobre Órdenes.

## Reglas de negocio clave (implementadas en la Tanda 5)

- `OrdenCliente.estatus_orden = orden_cerrada` solo cuando TODAS sus `OrdenEstacion`
  están `cerrada` (`OrdenClienteService.cerrar`); `OrdenEstacion` promueve la OC de
  `capturada`→`en_transmision` al crearse, y de `en_transmision`→`en_verificacion`
  cuando la ÚLTIMA OE hermana cierra (`avanzar_reales`).
- Campos calculados (`subtotal`/`iva`/`total`/`anio_venta`/`mes_venta`/
  `total_dias_campania` de OC; `porcentaje_participacion_oir`/importes/IVA/totales de
  OE) SIEMPRE en el servicio, nunca aceptados del cliente.
- Comisiones snapshot: se capturan libres al vender (Ventas, sin auditoría — es alta);
  después SOLO se editan por `PATCH /clientes/{id}/comisiones` (Dirección/Admin,
  motivo siempre requerido, auditado en `LogCambioParametro`) — propuesta §9 literal.
  Al cerrar, cualquier % que siga `null` se rellena con el default del catálogo
  (Vendedor/Agencia) SIN auditar (completar un vacío, no una edición).
- Incidencia automática (en `avanzar_reales`): `diferencia_spots = spots_verificados -
  spots_programados_efectivo`; `monto_ajuste = diferencia_spots * precio_spot` de la OE;
  se crea una `Verificacion` por CADA día de la OE (spec), pero solo se genera
  `Incidencia` en los días con diferencia.
- Editar `precio_unitario` (tarifa cliente) de una OC con OE ya creadas es libre — cada
  `OrdenEstacion` ya guarda su propio `precio_spot`, así que las existentes no se ven
  afectadas. Es **aviso, no candado** (a diferencia de otras ediciones de la OC que sí
  validan contra las OE hijas): `OrdenClienteForm.tsx` muestra un banner ámbar si la OC
  en edición ya tiene ≥1 OE, explicando que las existentes quedan con la tarifa anterior
  y las
  nuevas usarán la actualizada. No hay validación de backend — es puramente informativo.

## Integraciones

Ninguna en F1 (los reportes de afiliado — testigos, programados/reales — se cargan
como referencia de archivo; no hay parseo automático todavía).

## Dependencias

F0 completo (todos los catálogos que F1 referencia): EmpresaFacturadora, Vendedor,
Anunciante, Agencia, Contrato, Marca, Categoria, Plaza, Afiliado, Estacion, Usuario.

## Estado de implementación

- **Tanda 1 (modelos + migración):** 6 tablas nuevas (`orden_cliente`,
  `orden_cliente_vobo_item`, `orden_estacion`, `orden_estacion_dia`, `verificacion`,
  `incidencia`) en `backend/app/modules/ordenes/*.py` (un archivo plano por entidad,
  patrón real de F0). Migración `73fa97f9e718`. SQLite local de desarrollo (ADR-028,
  `DATABASE_URL`) — **nunca** AWS RDS. Infra CRUD genérica (`BaseRepository`/
  `BaseService`/`crud_router`/schemas) reubicada de `catalogos/` a `app/shared/`
  (ADR-032), igual que `DuracionSpot` (`app/shared/enums.py`).
- **Tanda 2 (datos semilla):** `backend/scripts/seed_dev.py` — reproduce los mocks del
  frontend (10 OrdenCliente, 18 OrdenEstacion, 66 días, 47 Verificacion, 3 Incidencia, 3
  entradas de historial de comisiones). Idempotente (`Session.merge()` + UUIDs
  deterministas `uuid5`). Hallazgos mock→modelo documentados en el propio script.
- **Tanda 3 (API de lectura):** endpoints `GET` en `docs/API-CONTRACT.md` (sección
  "Órdenes (F1)"). RBAC `ordenes` en `app/core/security.py` (grounded en propuesta §9).
  Repositorios/servicios de solo lectura (Create/Update con placeholders `BaseModel`,
  se reemplazan en la Tanda 5). Pruebas HTTP en
  `app/tests/test_f1_03_ordenes_lectura.py` (18 casos: paginación/filtros, 404, RBAC de
  las 8 áreas).
- **Tanda 4 (frontend modo `api`, solo lectura):** switch `VITE_DATA_SOURCE` (`mock`
  default │ `api`) en `frontend/.env.example`/`.env`. Los componentes/páginas/selectores
  de la demo **no cambiaron**: se agregó una capa de adaptadores
  (`frontend/src/modules/ordenes/adapters/`) que en modo `api`:
  - `vocabulario.ts` — mapeo INVERSO spec→v5 (spec tiene menos granularidad en
    `orden_interna`/`facturada`, más en `estatus` de OE que la demo nunca modeló —
    ver docstring para cada casilla y sus limitaciones conocidas).
  - `ordenesApiDTO.ts` + `ordenesApi.ts` — DTOs y llamadas HTTP crudas a `/ordenes/*`.
  - `catalogosApi.ts` — puebla los catálogos de referencia de F1 (`mocks/catalogos.ts`)
    con datos REALES de F0 (ya completo), **mutando en sitio** los arreglos que ya
    exporta ese módulo — cero cambios en los ~12 archivos que hacen
    `import { find* } from "../mocks/catalogos"`.
  - `fromApi.ts` — reconstruye `OrdenEstacion.horarios_programados`/`horarios_reales`
    (solo overrides, mismo formato que ya usan los mocks) a partir de
    `OrdenEstacionDia`+`Verificacion` reales, aplicando la misma noción de "programado
    efectivo" que ya usa `selectors.ts` — verificado contra el backend real con los 2
    casos de override sembrados (`oe2`/`oe3`, Tanda 2).
  - `cargarEstadoReal.ts` — orquesta todo y arma el mismo `OrdenesState` que
    `seedOrdenesState()`.

  `OrdenesProvider` acepta un `initialState` opcional (si se omite, sigue sembrando de
  los mocks — modo `mock` sin cambios); `OrdenesExplorerPage` resuelve el fetch async
  ANTES de montarlo en modo `api` (el inicializador de `useReducer` es síncrono), con un
  estado de carga/error explícito mientras tanto. El contexto expone `readOnly` (true en
  modo `api`): los 6 métodos de escritura lanzan si se llaman (el backend real, Tanda 3,
  todavía no expone escritura) y los botones que los disparan (Nueva OC/OE, Editar,
  Asignar estaciones, Cerrar, Capturar programados/reales) quedan deshabilitados con un
  tooltip explicativo.

  Verificado: 136/136 pruebas de frontend (mock, sin cambios), `tsc`/`eslint` limpios, y
  el pipeline completo (`cargarEstadoReal` + selectores existentes) ejercitado contra el
  backend real sembrado (Tanda 2) con una prueba de integración temporal (no forma parte
  de la suite permanente: depende de un backend vivo).

- **Tanda 5 (escritura y lógica de negocio — SOLO backend):** endpoints `POST`/`PUT`/
  `PATCH` en `docs/API-CONTRACT.md` (sección "Órdenes (F1)" → "Escritura"). Nuevo
  `app/modules/usuarios/lookup.py` (`resolver_usuario_id`) para resolver `created_by`
  desde `CurrentUser.username` — expuso que `seed_dev.py` sembraba a los 2 usuarios demo
  con NOMBRE completo en vez de username (corregido: `nombre_usuario` funciona como
  username en este stub de dev-auth, ver `dev.admin`). El canal de comisiones
  (`PATCH /clientes/{id}/comisiones`) NO reutiliza `audit.registrar_cambio_sensible`
  (bloquearía a Ventas/Dirección: el hook genérico de F0 hardcodea "solo Admin") — usa
  `audit.log_cambio_parametro` directo, ya que la autorización real la decide el chequeo
  de área explícito del propio servicio. Pruebas en
  `app/tests/test_f1_05_ordenes_escritura.py` (27 casos: cálculos, folio, checklist,
  congelamiento, comisiones por canal/área, herencia y validaciones de OE, cascada de
  estatus OE→OC, incidencia automática, cierre) + flujo E2E completo verificado a mano
  contra `dev_ordenes.db` real (crear → checklist → Vo.Bo. → asignar OE → programados →
  reales → cerrar → comisiones). 233/233 pruebas de backend, ruff/mypy limpios.
- **Tanda 5b (frontend, escritura real):** los 6 métodos de `OrdenesContext.tsx`
  (`crearOC`/`actualizarOC`/`crearOE`/`avanzarAProgramados`/`avanzarAReales`/`cerrarOC`)
  ahora son `async` y, en modo `api`, llaman a los endpoints reales de la Tanda 5 en vez
  del reducer local; en modo `mock` la lógica es EXACTAMENTE la de antes (el reducer no
  se tocó, solo se agregaron 4 acciones aditivas — `REEMPLAZAR_OC`/`REEMPLAZAR_OE`/
  `AGREGAR_INCIDENCIAS`/`REEMPLAZAR_HISTORIAL_OC` — que la rama `api` usa para reflejar
  lo que el backend ya calculó, sin recalcular nada en el cliente). Adaptadores nuevos:
  `escrituraApi.ts` (9 llamadas HTTP crudas), `toApi.ts` (v5 → body del request,
  excluyendo SIEMPRE comisión/checklist del `PUT` y comisiones/documentos calculados del
  `/cerrar`), `refrescar.ts` (reutiliza `fromApi.ts` de la Tanda 4 para reconstruir el
  objeto v5 tras cada escritura, sin duplicar lógica). Se quitaron `readOnly`/
  `siEscribible` (`OrdenesContext.tsx` y los 4 componentes que los usaban) — los botones
  de escritura vuelven a estar activos en modo `api`.

  Dos brechas reales resueltas en esta tanda:
  - `apiClient.ts` fijaba `X-Dev-User`/`X-Dev-Area` UNA vez al cargar el módulo — sin
    forma de cambiar de usuario en caliente. Nuevo `setDevAuthHeaders(username, area)`
    exportado, conectado a `demoSession.tsx#setUserKey` (modo `api`); se agregó una
    entrada "Dirección" a `DEMO_USERS` (antes ninguna usaba esa área real, necesaria
    para poder ejercitar por UI el canal de comisiones Dirección-only).
  - `duracion_spot`: el formulario ofrecía 8 valores (herencia del prototipo), el
    backend real (`DuracionSpot`) solo acepta 4 (`20s`/`30s`/`60s`/`mencion`) — el
    dropdown se angosta a esos 4 SOLO en modo `api` (`OrdenClienteForm.tsx`).

  Aspereza conocida, NO corregida esta tanda (es "solo UX" per `frontend/CLAUDE.md`): el
  mock de la demo deja editar comisión a Ventas mientras la OC no esté congelada
  (`canEditSensitiveSnap()`); el backend real es Dirección/Admin-only siempre, congelada
  o no. En modo `api`, un intento de Ventas simplemente llega como el 403 real en
  `submitError` — no se cambió la lógica de habilitación del formulario.

  Los 24 tests de `OrdenesContext.test.tsx` (+ 1 helper de `OrdenEstacionForm.test.tsx`)
  se migraron al patrón async (`act(() => ...)` → `await act(async () => ...)`,
  `toThrow()` → `rejects.toThrow()`) — misma lógica/aserciones, solo cambia la invocación.
  Verificado: `tsc`/`eslint` limpios, 136/136 pruebas de frontend en verde, y un ciclo
  E2E manual completo (crear OC → checklist → Vo.Bo. → crear OE con promoción de
  estatus → programados → reales con incidencia automática → cierre; más el canal de
  comisiones: 403 real para Ventas, éxito para Dirección tras `setDevAuthHeaders`
  dinámico) ejercitado llamando a los adaptadores reales de escritura contra
  `uvicorn`+`dev_ordenes.db` (SQLite local, ADR-028) — no hay navegador disponible en
  este entorno para una verificación visual, limitación ya documentada en la Tanda 4.
- **Diferido, sin consumidor hoy:** alta manual de Incidencia y edición de `resolucion`
  (ADR-031) — el frontend no tiene pantalla para eso; subida real de archivos (hoy
  `*_ref` son texto libre, sin endpoint de upload).
- **Tanda 6 (cierre de F1):** pasada completa de calidad sobre TODO el repo (no solo los
  archivos nuevos de F1) — backend: 233/233 pytest, ruff y mypy limpios sobre `app/`
  completo; frontend: `tsc`/`eslint` limpios y 136/136 vitest. ADRs 028-034 formalizados
  en `docs/arquitectura.md` (SQLite dev-only, comisiones snapshot, `OrdenEstacionDia` +
  3 capas de captura, Incidencia híbrida, infra CRUD en `app/shared/`, checklist Vo.Bo.
  como tabla hija, campos de cierre) + una actualización a ADR-016 documentando por qué
  el canal de comisiones de F1 no reusa `audit.registrar_cambio_sensible` (el
  placeholder de `field_permissions` es "solo Admin"; F1 necesita Dirección) y qué
  condición debe cumplirse para que vuelva a ser seguro reusarlo (F5/`PermisoCampo`
  real). Con esto, **F1 queda cerrado** (Entrega 1 = F0+F1 completa, backend+frontend,
  lectura+escritura); lo que sigue es una fase nueva (F2 Facturación) o los ítems
  diferidos de abajo, ninguno de los dos arranca sin pedirlo explícitamente.
- **Tanda 7 (retiro del modo `mock` del frontend):** con la app corriendo de forma
  estable contra el backend real (Tanda 5b + migración a RDS), se eliminó por completo
  la capa de datos falsos en TypeScript que solo servía para la demo sin backend —
  `frontend/src/modules/ordenes/mocks/` (5 archivos: `catalogos.ts`, `ordenesCliente.ts`,
  `ordenesEstacion.ts`, `incidencias.ts`, `historialComisiones.ts`, `index.ts`),
  `components/DemoUserSwitcher.tsx`, `state/demoSession.tsx` y `config.ts`
  (`DATA_SOURCE`/`VITE_DATA_SOURCE`, también quitada de `.env`/`.env.example`).
  `mocks/catalogos.ts` no era datos de demo sino la caché de catálogos que
  `catalogosApi.ts` puebla en sitio con datos reales — se reubicó (sin cambios de
  forma) a `state/catalogosCache.ts`, ahora con los 11 arreglos naciendo vacíos en vez
  de precargados con filas dummy. `OrdenesContext.tsx` perdió los 6 branches `if
  (DATA_SOURCE === "api") {...} else {...}` (y las 6 acciones/reducer-cases que solo
  usaba la rama mock: `CREAR_OC`, `ACTUALIZAR_OC`, `CREAR_OE`,
  `AVANZAR_OI_PROGRAMADOS`, `AVANZAR_OI_REALES`, `CERRAR_OC`) — los 6 métodos de
  escritura ahora SIEMPRE llaman al backend real; `initialState` de `OrdenesProvider`
  pasó de opcional a obligatorio. Se quitó también `readOnly`/`permiteComisionesSensibles`
  (ya sin uso: el backend siempre fue la autoridad real). `canEditSensitiveSnap()` —el
  gating de UI que dejaba editar comisión a Ventas mientras la OC no estuviera
  congelada, la aspereza conocida anotada en la Tanda 5b— se resolvió hardcodeando el
  campo siempre editable (decisión explícita del usuario): el backend YA rechaza con
  403 real a quien no sea Dirección/Admin vía el canal dedicado de comisiones, así que
  el gating del formulario era pura UX sin ninguna protección real detrás.
  `OrdenesExplorerPage` perdió el `DemoSessionProvider`/ternario mock↔api (siempre monta
  `OrdenesExplorerApiGate`) y usa `currentUser` (`@/shared/lib/currentUser`, el mismo
  placeholder de sesión que ya usa F0) en vez del selector de usuario de la demo.
  `OrdenesContext.test.tsx` (24 pruebas) se **eliminó** en vez de migrarse: probaba
  exclusivamente la lógica de negocio de la rama mock ya borrada (folio correlativo, %
  OIR, promoción de estatus, incidencia automática, congelamiento de comisión,
  precondiciones de cierre) — se confirmó que las mismas reglas ya están cubiertas en
  el backend real (`app/tests/test_f1_05_ordenes_escritura.py`) antes de borrar, para no
  perder cobertura. `OrdenEstacionForm.test.tsx` se reescribió: su harness creaba la OC/OE
  de prueba llamando a `crearOC`/`crearOE` (ahora HTTP real, revienta sin backend vivo)
  — pasó a construir los objetos con los builders de `fixtures.ts` y pasarlos directo
  como `initialState`. `OrdenClienteForm.test.tsx`/`OrdenClienteDetailPanel.test.tsx`
  perdieron el wrapper `DemoSessionProvider`/`DemoUserSwitcher`; el primero ganó un
  sembrado propio de `state/catalogosCache.ts` (antes dependía de las filas dummy que
  vivían en `mocks/catalogos.ts`) y su describe "Congelamiento" se simplificó a un solo
  caso (ya no hay dos personas de demo que comparar). Verificado: `tsc --noEmit` y
  `eslint` limpios, 110/110 pruebas de frontend (9 archivos; menos que las 136
  anteriores por las pruebas eliminadas de la rama mock, no por pérdida de cobertura).
- **Migración a AWS RDS (numeración de tandas propia de esta auditoría, distinta de
  las tandas del módulo) — informe completo en
  `docs/modulos/f1-ordenes/INFORME-MIGRACION-RDS-F1.md`:** auditoría de compatibilidad
  SQL Server de la migración `73fa97f9e718` contra los 16 puntos estándar — sin
  conectarse a RDS en ningún momento (regla dura de esta tarea). Correcciones
  aplicadas EN SITIO sobre la misma revisión (RDS nunca la había visto): las 25 FK con
  `name=`/`ondelete='NO ACTION'` explícitos; 5 índices agregados por filtro real y 1
  redundante quitado (`ix_orden_cliente_vobo_item_orden_id`); `Incidencia` con
  `created_at`/`updated_at`; 9 `CHECK` nuevos de montos/cantidades en `orden_cliente`
  e `incidencia`; tipos explícitos `fecha_sql()`/`hora_sql()`/`texto_largo()` en
  `core/db.py` (con_variant a `DATE`/`TIME`/`NVARCHAR(MAX)`, mismo patrón que
  `datetime2()` — ADR-036) para que el SQL offline sea un preview fiel y para dejar de
  depender de `NTEXT` (deprecado). `Incidencia` documentada en ADR-037 (dos FK al
  mismo padre, consistencia garantizada por el servicio, no por el esquema). Probado
  con el ciclo completo downgrade→upgrade→re-siembra→pytest (233/233) DOS veces, en un
  archivo SQLite separado, sin interrumpir ningún proceso en uso. Nuevo script de solo
  lectura `backend/scripts/verificar_config_bd.py` — resuelve la URL exactamente por el
  mismo camino que `migrations/env.py`, contraseña SIEMPRE enmascarada incluso dentro
  de un `odbc_connect=` empacado — ver ADR-028 y siguientes.
  **Advertencia permanente en el encabezado de la migración:** una vez que RDS vea esta
  revisión por primera vez, el archivo no se vuelve a editar — cualquier cambio
  posterior va en una migración nueva encadenada.
  **3 recomendaciones aprobadas y YA aplicadas** (revisión externa, "Tanda 4b"):
  `UNIQUE(orden_estacion_dia_id)` en `verificacion` (como máximo una por día);
  `UNIQUE(orden_estacion_id, fecha_transmision, hora_inicio)` en `orden_estacion_dia`
  (evita duplicados que inflarían el balance de spots en silencio);
  `CHECK(spots_asignados <= spots_solicitados)`, respaldado por el texto literal de la
  spec. **NO se agregó** el equivalente para `spots_programados` (sin respaldo en spec
  ni prototipo) ni para `spots_verificados` (nunca debe llevar tope: "excedente" es un
  tipo de incidencia válido). Re-siembra de la demo verificada SIN violaciones tras
  agregar las `UNIQUE` — ninguna orden de la demo repite día/hora ni tiene más de una
  verificación por día. `Verificacion` ganó `updated_at` nulable (ver
  `Verificacion.reconciliada` en pendientes, abajo). Ciclo completo repetido, pytest en
  verde. **1 pregunta llevada al área usuaria, sin tocar el CHECK:** si GRC
  programa pautas que cruzan medianoche, `ck_orden_estacion_dia_horas` las rechaza hoy
  — la restricción ya existía en el prototipo de frontend aprobado, no es invención del
  backend; la solución (si se necesita) es capturar dos filas, no relajar el `CHECK`.
  **Cuarta pasada ("Tanda 4c"), cierre de la auditoría antes de la inmutabilidad:** 8
  `CHECK >= 0` agregados en `orden_estacion` (misma omisión que la Tanda 4 corrigió en
  `orden_cliente`/`incidencia` pero dejó pasar aquí); los 2 índices
  `ix_orden_estacion_dia_orden_estacion_id` (el "hallazgo menor sin aplicar" que había
  quedado pendiente de la Tanda 4b — redundante con el `UNIQUE` compuesto) e
  `ix_orden_estacion_dia_fecha_transmision` (verificado que ningún endpoint filtra por
  esa columna sola) quitados; comentarios "auto generated by Alembic" (ya falsos tras
  tantas ediciones a mano) corregidos por unos que reflejan la realidad; lectura
  completa del archivo de punta a punta sin hallazgos adicionales. **Segundo incidente
  de contraseña expuesta, mismo bug de fondo:** `scripts/seed_dev.py` imprimía
  `settings.sqlalchemy_url` sin enmascarar antes de validar que apuntara a SQLite — se
  centralizó el enmascarado en `url_enmascarada()` (`app/core/db.py`, reutilizada ahora
  por ambos scripts) y se reordenó el script para validar primero. Ciclo completo
  (downgrade→upgrade→re-siembra→pytest) repetido una cuarta vez, sin violaciones.
  **Quinta pasada ("Tanda 4d"), sobre las 2 respuestas y el hallazgo de seguridad de la
  Tanda 4c:** el riesgo real del incidente de contraseña no era el valor filtrado sino
  que el guard dependía del ORDEN de las líneas — se aisló en
  `_verificar_solo_sqlite()`, ahora la primera instrucción de `main()` (antes de crear
  el engine o imprimir nada), y se agregó `app/tests/test_seed_dev_guard.py` (2
  pruebas) para que un reordenamiento futuro lo rompa de forma visible, no silenciosa.
  Inventario de los 6 puntos del backend que crean un engine (`seed_dev.py`,
  `verificar_config_bd.py`, `app/main.py`/`/health/db`, `app/core/db.py`,
  `migrations/env.py`, los tests) confirma que `seed_dev.py` era el único que
  necesitaba el guard — el resto o no escribe, o es la app/Alembic en su rol legítimo
  de tocar RDS. `spots_solicitados` cambió a `> 0` (aplicado, con su espejo en el
  schema Pydantic). El `CHECK` de `importe_oir + importe_emisora = importe_estacion`
  se aplicó, y se extendió a `total_oir`/`total_emisora` (mismo razonamiento: sumas de
  montos ya redondeados). **Hallazgo al verificar:** la re-siembra reveló que SQLite
  guarda `NUMERIC` como `float64` (sin tipo decimal de punto fijo) — un CHECK de
  IGUALDAD entre sumas calculadas por separado puede fallar por 1 ULP de ruido de
  `float64` aunque la aritmética `Decimal` real sea exacta (pasó con 1 de 18
  `OrdenEstacion` de la demo). Los 3 CHECK se envolvieron en `ROUND(x, 2)` — no-op en
  SQL Server, neutraliza el ruido en SQLite sin enmascarar una violación real
  (verificado). Ver ADR-039. Ciclo completo repetido una quinta vez, sin violaciones.
- **Tanda 8 (RBAC: Admin pasa a superusuario en todos los módulos):** decisión explícita
  del equipo, confirmada tras preguntar (desviación deliberada de la matriz de la
  propuesta §9, que le daba a Admin solo lectura sobre Órdenes). `app/core/security.py`:
  `_nivel()` ahora resuelve `Area.ADMIN` a `Acceso.WRITE` de forma centralizada, ANTES de
  consultar la matriz `RBAC` por módulo — así Admin tiene captura en catálogos, órdenes y
  cualquier módulo futuro sin tener que listarlo módulo por módulo. Se quitaron las
  entradas explícitas `Area.ADMIN: Acceso.WRITE`/`Acceso.READ` de `RBAC`/`_LECTURA_ORDENES`
  (quedaban redundantes o, en el caso de Órdenes, contradictorias con el nuevo
  comportamiento). El canal de comisiones (`PATCH /clientes/{id}/comisiones`) ya
  permitía Admin desde la Tanda 5 (chequeo de área explícito en el servicio, no pasa por
  esta matriz) — sin cambios ahí. Verificado: 235/235 pytest, ruff y mypy limpios sobre
  `app/core/security.py`.

## Pendientes / dudas

- **Limitación conocida (Tanda 4):** `estatus_orden = facturada` (spec) no distingue
  `facturada_archivo_plano` de `facturada_timbrada` (v5) — se mapea siempre a
  `facturada_timbrada` (decisión explícita). Se resuelve de raíz cuando F2 (Facturación)
  exista en el backend real y aporte el dato que hoy falta.
- **Limitación conocida (Tanda 4):** `OrdenEstacion.estatus` real tiene 3 valores
  (`borrador`/`en_revision`/`cancelada`) sin equivalente en el vocabulario v5 de la demo
  (que solo modela el tramo asignada→programada→reales). La Tanda 5 no los usa (el
  servicio solo transiciona por `asignada`→`en_transmision`→`cerrada`) — revisar
  `vocabulario.ts` del frontend si algún flujo futuro los introduce.
- **Hueco real, sin resolver (encontrado en la auditoría RDS, Tanda 2):** ninguna OC/OE
  puede llegar hoy a `cancelada` — el valor existe en el enum y en el `CHECK`, pero
  ningún método de servicio ni endpoint lo asigna. Una orden capturada por error queda
  visible para siempre en `recibida`/`capturada`, sin forma de ocultarla. Ver ADR-035
  (`docs/arquitectura.md`) para el razonamiento completo de por qué F1 no lleva
  `activo` y por qué este hueco es de implementación, no de diseño. Construir el
  endpoint de cancelación es trabajo futuro, no arrancado.
- **Hueco real, sin resolver (mismo origen):** `Verificacion.reconciliada` se fija una
  sola vez al crear el registro (siempre `True`, nunca `False` en la práctica) y no
  existe ningún mecanismo para corregir o revertir una reconciliación mal hecha. Ver
  docstring de `verificacion.py` para el detalle; requiere una decisión de producto
  (¿se edita, se anula y se recrea?) antes de construir el endpoint correspondiente.
- **Pregunta de negocio abierta (ADR-038), llevada al área usuaria junto con la de
  medianoche:** `reconciliada` siempre vale `True` y nada lo lee — es hoy un campo
  MUERTO, porque `avanzar_reales` comprime en una sola transacción los 4 pasos que la
  spec describe por separado (capturar realidad → revisar diferencias → reconciliar →
  cerrar). Pregunta exacta para el área usuaria: *¿existe un momento en que la
  verificación queda capturada pero la diferencia todavía no se acepta, o el reporte
  del afiliado siempre se resuelve en el mismo acto?* Si la respuesta es "sí hace falta
  un paso intermedio", `avanzar_reales` necesitaría partirse en dos — no se toca el
  flujo hasta tener esa respuesta. Se agregó `updated_at` nulable a `Verificacion` por
  el costo asimétrico de no tenerlo si esto cambia (una línea ahora vs. `ALTER TABLE`
  después sobre una base compartida).
- **Deuda técnica anotada (no es parte de ninguna tanda cerrada):** las vistas
  operativas "listas para cerrar"/"listas para facturar" del frontend filtran sobre el
  array YA CARGADO en memoria (`filtrarOrdenesCliente`, `state/selectors.ts`), no vía
  query al backend — con las 10 órdenes de la demo no se nota, con volumen real sí. La
  solución es mover esos filtros a query params reales de
  `OrdenClienteRepository._apply_filters` (rango de `fecha_inicio_campania`/
  `fecha_fin_campania` + los estados que arman cada vista). El día que eso se
  implemente, **el índice de esas 2 columnas sí hará falta** — hoy deliberadamente no
  se agregó (auditoría RDS) porque nada las consulta contra el backend.
- **Ticket aparte (ADR-036):** `Categoria.descripcion_categoria` y
  `EmpresaFacturadora.direccion_empresa` (F0) compilan a `NTEXT` en `mssql` — mismo bug
  que se corrigió en F1 (ver `texto_largo()` en `core/db.py`), pero F0 no se toca en
  esta migración (posiblemente ya aplicado a RDS; un cambio ahí sería un `ALTER TABLE`
  sobre una base compartida). El proyecto queda temporalmente con dos formas de
  modelar texto largo — decisión de alcance, no descuido.
- **Aplicado (auditoría RDS, "Tanda 4d"):** `spots_solicitados` cambió de `>= 0` a
  `> 0` — mismo argumento que ya respalda `total_spots > 0` en `OrdenCliente` (un día
  sin spots solicitados no tendría razón de existir como fila).
- **Aplicado (auditoría RDS, "Tanda 4d"):** 3 CHECK de suma exacta en `orden_estacion`
  (`importe_oir + importe_emisora = importe_estacion`, `total_oir = importe_oir +
  iva_oir`, `total_emisora = importe_emisora + iva_emisora`), envueltos en `ROUND(x,
  2)` en ambos lados — necesario porque SQLite guarda `NUMERIC` como `float64` y una
  igualdad entre sumas calculadas por separado puede fallar por 1 ULP de ruido aunque
  la aritmética `Decimal` real sea exacta (hallazgo de la re-siembra, ver ADR-039).
  `ROUND` es un no-op inofensivo en SQL Server. Ver informe de migración, sección 6.
- **Pregunta llevada al área usuaria (auditoría RDS), CHECK sin tocar:** si GRC
  programa ventanas de transmisión que cruzan medianoche (23:00–01:00), el `CHECK
  (hora_fin > hora_inicio)` las rechaza — restricción heredada del prototipo de
  frontend ya aprobado, no invención del backend. Cada fila de `OrdenEstacionDia` está
  anclada a un solo día calendario, así que la solución (si se necesita) es capturar
  dos filas, no relajar el `CHECK`.
- Fuera de las preguntas/recomendaciones listadas arriba (todas ya llevadas al área
  usuaria o dejadas como recomendación explícita, ninguna aplicada sin aprobación), no
  hay duda abierta adicional a la fecha de esta ficha. Las decisiones de modelado se
  resolvieron con el equipo antes de la Tanda 1, documentadas como ADRs 028-039.
