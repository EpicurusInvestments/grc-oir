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

### OrdenCliente (36 campos spec + 10 aditivos)
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
- **Spots Bonificables** (`cantidad_spots_bonificables`, `subtotal_spots_bonificables` —
  ADR-067): spots que se transmiten y se asignan a `OrdenEstacion` igual que cualquier
  otro (`total_spots` no cambia de significado) pero no se cobran al cliente. Desde esta
  extensión, `subtotal`/`iva`/`total` se calculan sobre `total_spots −
  cantidad_spots_bonificables` (spots facturables), no sobre `total_spots` — ver ADR-067
  para la fórmula completa y su propagación gratuita a `FacturaCliente`/archivo plano.

**Checklist de Vo.Bo. (ELIMINADO — ver ADR-100):** existió una tabla hija
`OrdenClienteVoBoItem` (ADR-033, NO JSON: 10 ítems fijos `ITEMS_VOBO`, cada uno con
`completado`/`usuario_id`/`fecha_completado`) que gateaba la transición `recibida →
capturada`. Petición del usuario (2026-09-22, rediseño "Orden de Servicio/Orden de
Transmisión"): se elimina por completo — `OrdenClienteService.create()` guarda y pasa
DIRECTO a `capturada`, sin checklist ni paso intermedio. `recibida` sigue en el enum
(la spec la define) pero queda inalcanzable por el flujo normal.

### OrdenEstacion (27 campos spec + 6 aditivos)
PK `orden_estacion_id`. FK a `OrdenCliente`, `Contrato`, `Anunciante`, `Vendedor`,
`Agencia`, `Categoria`, `Estacion`, `Plaza`, `Usuario`. Calculados (servicio):
`importe_estacion` (agregado de días), `importe_oir`/`iva_oir`/`total_oir`,
`importe_emisora`/`iva_emisora`/`total_emisora`.

**Spots Bonificables** (`cantidad_spots_bonificables` — ADR-068, análogo a ADR-067 de
`OrdenCliente`): spots que se asignan y transmiten con normalidad (el balance contra
`OrdenCliente.total_spots` no cambia) pero no se cobran a la estación. Reducen
`importe_estacion` (`spots_facturables = spots_asignados − cantidad_spots_bonificables`),
que a su vez arrastra `importe_oir`/`importe_emisora` y sus IVA/totales —
`porcentaje_participacion_oir` no cambia (solo depende de las tarifas). No hay CHECK que
lo acote contra los spots asignados: esa suma vive en `OrdenEstacionDia` (tabla hija), no
es una columna propia de `orden_estacion` — la validación es del servicio.

**`producto_tarifa` y `duracion_spot`** (ADR-102 + ADR-106, Fase 2 del rediseño "Asignar
estaciones"): producto del catálogo Tarifa (`spot│mencion│control_remoto│patrocinio`) Y
duración (`20s│30s│60s`), AMBOS elegidos POR ESTACIÓN — secuencia del formulario:
Estación → Producto → Duración → Tarifa. NO confundir `producto_tarifa` con el campo
`producto` de esta misma tabla (heredado de `OrdenCliente.producto`, "Campaña" en texto
libre). Al crear/editar, el servicio busca la tarifa ACTIVA de `TarifaPlaza` para
(estación + `Estacion.tipo_senal` + `duracion_spot` de ESTA OE + `producto_tarifa`) y,
solo si `precio_spot` no coincide con su `tarifa_neta`, exige `motivo_cambio_tarifa` y
audita en `LogCambioParametro` (`entidad="OrdenEstacion"`, `campo="precio_spot"`) — sin
candado de permiso (Ventas sigue capturando libre; ver ADR-102 para el porqué).
**ADR-106 corrige el alcance original de ADR-102:** ahí se había decidido que
`duracion_spot` se heredara SIN cambio de la OC; tras revisar el flujo en vivo, el
usuario pidió que fuera independiente por estación, igual que `producto_tarifa` — la
columna ya existía (mismo CHECK del catálogo), solo cambió de dónde sale el valor.
**ADR-115 (fix, frontend):** en el formulario, si la combinación estación/producto/
duración NO tiene tarifa en el catálogo, "Tarifa por spot" se VACÍA para que el usuario
la capture a mano (antes se quedaba con el valor de la última combinación que sí tenía
tarifa). Un precio ya tecleado a mano nunca se pisa.

**"Material a Transmitir" — `OrdenEstacionAudio`** (ADR-103, Fase 3 del rediseño): tabla
hija NUEVA, fuera de la spec BD v2 — uno o más audios por OE, subidos vía endpoints
dedicados (`POST`/`GET`/`DELETE /ordenes/estaciones/{id}/audios`), NO por el
`create()`/`update()` genérico (a diferencia de `reporte_programados_ref`, que es una
sola referencia que se reemplaza). El primero subido (`orden=0`) es el DEFAULT que usan
los días sin asignación propia; `OrdenEstacionDia.orden_estacion_audio_id` (nullable)
guarda la excepción puntual de un día, asignada con
`PUT .../dias/{dia_id}/audio` (otro endpoint dedicado). Lista blanca propia
(`EXTENSIONES_AUDIO_ORDENES`: mp3/wav/ogg) y tope propio (`S3_MAX_AUDIO_BYTES`, 15 MB) —
ninguno comparte constante con los adjuntos de documentos (ADR-042). En el frontend, la
sección "Material a Transmitir" requiere el `orden_estacion_id` ya creado — vive en
`OrdenEstacionDetailPanel.tsx` (el detalle, junto a los PDFs — ADR-106 corrigió esto: el
usuario no la encontraba porque solo vivía en el formulario de edición, no en la vista de
detalle donde se navega normalmente) y también en `OrdenEstacionForm.tsx` cuando `oe` ya
existe (edición), donde además alimenta el selector de audio POR DÍA de
`PeriodoTransmisionGrid.tsx`.

**Flujo tras guardar el alta — pregunta "¿generar otra?"** (ADR-116, reemplaza el
comportamiento original de ADR-103): al guardar una OE nueva, YA NO pasa directo a modo
edición de esa misma OE (ese motivo dejó de aplicar desde ADR-109 — el material se sube
DURANTE la captura, no hace falta la OE ya creada). Ahora se pregunta con un modal
("¿Deseas generar otra Orden de Transmisión para esta misma Orden de Servicio?"): "Sí"
deja el formulario en blanco para capturar otra estación de la MISMA OC (mismo mecanismo
de remount vía `key` que usaba ADR-113 para la transición alta→edición, ahora reutilizado
para "otra alta más"); "No" va a la lista con la recién creada arriba (orden por
`created_at` descendente, ya existente). "Cancelar" (antes de guardar) regresa a "Órdenes
de Servicio" (la OC elegida, si ya había una). Este flujo es EXCLUSIVO del alta — en
edición, "Guardar" solo guarda y vuelve al detalle, sin preguntar nada.

**ADR-113 (fix, sigue vigente):** cualquier transición de identidad del formulario que no
remonte el componente (`<OrdenEstacionForm>` reusa la misma instancia de React) deja su
estado local (`periodo`, `estacionId`, etc. — inicializado con `useState(prop ?? default)`,
que solo corre una vez) con datos VIEJOS, aunque el prop `oe`/título sí se actualicen. La
`key` de `OrdenEstacionListPage.tsx` cubre tanto la transición a edición (por id de OE)
como, desde ADR-116, cada "generar otra" en el alta (por un contador que sube en cada
"Sí").

**"Cancelar transmisión" — `OrdenEstacionDia.cancelada`** (ADR-104, Fase 4 del
rediseño): columna nueva, fuera de la spec BD v2. Cancela UN día puntual (no la OE
completa) en cualquier momento después de guardada la orden, sin candado de `estatus` —
`POST .../dias/{dia_id}/cancelar` (body `{motivo}`). El día NUNCA se borra ni se oculta:
conserva su fila (auditoría) pero queda excluido de las sumas de `spots_asignados` (balance
de spots de la OC) y del recálculo de importes de la OE. Reutiliza el mecanismo YA
existente de `Verificacion`+`Incidencia` (el mismo de `avanzar_reales`): crea una
`Verificacion` con `spots_verificados=0` y una `Incidencia` tipo `spot_no_emitido` —
por eso un día que ya tiene `Verificacion` (cancelado antes, o ya verificado por el
flujo normal 2.2→2.3) no se puede volver a cancelar (409), sin necesitar ninguna regla
de `estatus` explícita. En el frontend, el botón vive en `PeriodoTransmisionGrid.tsx`
junto al de quitar fila (solo con la OE ya creada), con el motivo capturado en un campo
de texto en línea; una fila cancelada se muestra atenuada con la etiqueta "Cancelado".

**`PeriodoTransmisionGrid.tsx`/`CalendarioPeriodoTransmision.tsx` — "Horario de
transmisión" único + "Material a Transmitir" con default visible** (ADR-107 + ADR-108,
correcciones sobre la Fase 4): "Hora inicio"/"Hora término" pasan de 2 columnas a UNA
sola ("Horario de transmisión") Y de 2 valores a UNO solo (ADR-108: ya no es un rango —
`hora_inicio`/`hora_termino`, columnas del modelo sin cambio de esquema, se capturan
SIEMPRE iguales, tanto en el calendario como en la tabla — **ADR-112 (fix)**: el backend
seguía exigiendo un rango real, `hora_fin > hora_inicio` estricto, tanto en el validador
Pydantic como en el CHECK de la base; se relajó a `>=` porque el valor único de ADR-108
implica igualdad, no un rango — sin este fix, TODA alta/edición real fallaba con 422).
La columna de audio (ADR-103,
renombrada "Material a Transmitir") aparece desde el ALTA (con solo pasar `audios`,
aunque venga vacía) y muestra SIEMPRE el nombre del material que le toca a cada día — el
propio si tiene override, si no el default (`audios[0]`, el primero subido) — incluidos
los días recién generados por el calendario que todavía no tienen `orden_estacion_dia_id`
real (antes mostraban un "—" sin explicación; ahora, si no hay ningún audio subido
todavía, una nota debajo de la tabla explica que hay que guardar la orden primero).
"Sustitución de Material" es un ícono (🔄) que revela el combo bajo demanda — solo
disponible para un día con id real, ya que cambiar su default sigue siendo el endpoint
dedicado `PUT .../dias/{id}/audio`.

**Subida de "Material a Transmitir" DURANTE el alta, y obligatoria para el calendario**
(ADR-109 + ADR-110, correcciones sobre la Fase 4): antes, subir un audio requería que la
OE ya existiera (`orden_estacion_id` real). Ahora, al dar de alta, cada archivo elegido
se sube de inmediato a S3 vía `POST /ordenes/material-staging` (sin ningún id de padre —
mismo patrón que el PDF de la Orden de Servicio, `AdjuntoOrdenInput`/`subirAdjuntoOrden`,
ADR-042/ADR-109) y el `{ref, nombre_archivo}` que devuelve viaja en
`OrdenEstacionCreate.audios`; el servicio crea las filas reales de `OrdenEstacionAudio`
en el mismo orden al crear la OE (el primero = default). El endpoint dedicado
(`agregar_audio`) sigue siendo el único camino para agregar material DESPUÉS de que la
OE ya existe; `OrdenEstacionUpdate` no gana este campo. Además (ADR-110), mientras no
haya al menos un audio subido (en alta) — o siempre en edición, donde la regla no
aplica retroactivamente — el calendario y la tabla de periodo permanecen deshabilitados
(`disabled`), con una nota indicando que hay que subir el material primero; el guardado
también valida esta condición.

**"Sustitución de Material" también en el ALTA** (ADR-111): con 2+ audios subidos
durante la captura, el botón 🔄 ya no requiere `orden_estacion_dia_id` real — con
`permiteAsignacionLocal` (`PeriodoTransmisionGrid.tsx`, prendido solo cuando `!isEdit`)
el cambio se guarda en la fila misma y viaja al crear como `audio_staging_ref` por día
(`OrdenEstacionDiaCreate`), resuelto por el servicio contra los `audios` de la MISMA
solicitud (las filas de `OrdenEstacionAudio` se crean primero, con `db.flush()` de por
medio, para poder resolver el `ref` al id real antes de armar los días). En edición, la
sustitución de un día YA guardado sigue siendo, sin cambio, el endpoint dedicado e
inmediato (`onAsignarAudio`); un día nuevo sin guardar en edición NO tiene forma de
llevarse un override de audio a "Guardar" todavía (limitación conocida, fuera de
alcance de este ADR).

**Envío de los PDFs por correo — `LogEnvioCorreoOrdenEstacion`** (ADR-105, Fase 5 del
rediseño): tabla nueva, fuera de la spec BD v2 — bitácora de cada intento de envío
(`POST .../pdf/{tipo}/enviar-correo`, `tipo` = servicio/programados/reales), exitoso o
no. Reusa los 3 generadores de PDF YA existentes (`orden_estacion_pdf.py`) como adjunto;
el mismo gateo por sub-estado de sus `GET` sigue aplicando (p.ej. "reales" antes de 2.3
→ 400, sin generar bitácora). El correo se manda vía integración nueva
`app/integrations/correo/` (mismo patrón anti-corrupción que `AlmacenamientoPort`,
ADR-027): `CorreoSES` real o `CorreoLocal` (default de dev — SES en modo sandbox exige
verificar cada destinatario, así que un envío real de extremo a extremo no es viable sin
la cuenta AWS del cliente). **ADR-122:** `CorreoLocal` además guarda el mensaje armado
(MIME completo, mismo `construir_mime()` que usa `CorreoSES`) como archivo `.eml` en
`_storage_local/correos_simulados/` — se puede abrir con un cliente de correo de
escritorio para revisar cómo quedó el mensaje (asunto, cuerpo, adjuntos reales), sin
mandar nada a internet ni depender de credenciales de SES/AWS.

**ADR-120 (petición del usuario):** en la pantalla, este envío individual quedó
reemplazado por un diálogo "Enviar por correo"/"Imprimir" que aparece al generar
CUALQUIERA de los 3 PDFs (`OrdenEstacionDetailPanel.tsx`, `FilaPdf`). "Imprimir" abre el
PDF de siempre; "Enviar por correo" (`POST .../correo-orden-transmision`, sin body)
manda SIEMPRE el mismo paquete fijo — PDF de Programados + todo el Material a
Transmitir — a TODOS los `ContactoAfiliado` **activos** con correo cargado del afiliado
dueño de la estación (ya no hay captura manual de destinatario). Reusa
`LogEnvioCorreoOrdenEstacion` con un 4º valor de `tipo_pdf`, `"orden_transmision"`. El
botón se deshabilita de antemano si el afiliado no tiene ningún contacto activo con
correo (`contactoAfiliadoApi.listPorAfiliado`, catálogo `ContactoAfiliado` — no la
Estación, que no tiene contactos propios). El endpoint individual por-tipo de arriba
sigue existiendo en el backend (sin UI propia) por si se necesita un envío puntual a un
solo destinatario.
**ADR-118 (petición del usuario):** la tabla de días del PDF #2 (Horarios Programados)
quitó "Pedidos"/"Asignados" y agregó "Material a Transmitir" (mismo criterio que
`nombreMaterial()` del frontend — override del día o el primero subido) + un solo
"Horario" (ya no Hora Inicio/Hora Término por separado, coherente con ADR-107/108).

**Desviación aditiva clave (ADR-030):** la spec modela `fecha_transmision`/
`hora_inicio`/`hora_fin`/`spots_solicitados`/`spots_asignados`/`spots_faltantes` como
campos PLANOS (una fila = un día), pero la propia spec autoriza "agrupar por rango" —
se usa esa lectura: esos campos viven en la tabla hija **`OrdenEstacionDia`** (una fila
por día), con 3 capas de captura (asignado → programado → verificado, ver docstring de
`orden_estacion.py`). `spots_faltantes` deja de persistirse: se calcula al leer.
`testigos_url`/`testigos_ubicacion_alterna`/`notas_transmision`/`reporte_programados_ref`/
`reporte_reales_ref` (tampoco en spec, mismo ADR) viven en `OrdenEstacion` (se capturan
una vez por lote, no por día). **ADR-119 (petición del usuario):** `testigos_url`/
`testigos_ubicacion_alterna` ya NO se capturan desde "Capturar Reales" — la pantalla los
reemplazó por "Evidencias de lo Transmitido" (audios, tabla nueva
`orden_estacion_evidencia`, mismo patrón que "Material a Transmitir" pero sin `orden`/
default/override por día — lista plana). Las 2 columnas siguen existiendo en la base
(se preserva cualquier dato ya capturado); simplemente dejaron de leerse/escribirse.

**ADR-123 (petición del usuario):** junto a "Evidencias de lo Transmitido", "Formato de
Horarios Reales" (tabla nueva `orden_estacion_formato_real`, mismo patrón de lista plana)
— pero acepta CUALQUIER formato (PDF, Excel, TXT, audio...), no solo audio. Único punto
de subida del sistema con lista NEGRA (`EXTENSIONES_PELIGROSAS`, ejecutables/scripts) en
vez de blanca, reforzado con una revisión de contenido (firma de ejecutable de Windows,
"MZ") sin importar la extensión declarada — ver `leer_adjunto_libre()` en
`app/integrations/almacenamiento/documentos.py`.

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

**ADR-117 (petición del usuario, REVERTIDA el mismo día):** se intentó que `create()`
naciera directo en `en_transmision` (saltando 2.1 "Asignada") — se revirtió por completo
porque dejaba `update()` permanentemente inalcanzable (`FROZEN_STATES_OE` congela edición
desde `en_transmision`). `create()` volvió a dejar la fila en `asignada`, sin cambios. Ver
ADR-117 en `arquitectura.md` para el detalle completo (se conserva documentado por si se
retoma).

**ADR-121 (petición del usuario):** logra el mismo objetivo de fondo (saltarse "2.2
Capturar Programados" como paso MANUAL) sin el problema de ADR-117: `create()` sigue
dejando la fila en `asignada` (que YA es editable hoy), y `avanzar_reales()` ahora acepta
avanzar directo desde `asignada` **o** desde `en_transmision` — "Capturar Reales" (2.3) ya
no requiere haber pasado por `avanzar_programados()` primero. `reporte_programados_ref`
(antes solo capturable en ese paso) se agregó a `OrdenEstacionCreate`/`Update`, así que se
puede adjuntar/corregir desde el alta o mientras la OE siga editable. El botón "→
Capturar programados (2.2)" y su pantalla (`ProgramadosForm.tsx`) se retiraron de la UI —
el endpoint `POST .../programados` se conserva intacto en el backend (con sus pruebas)
por si se necesita un ajuste puntual de `spots_programados` distinto al asignado.

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
- **`OrdenEstacion.precio_spot` puede superar `OrdenCliente.precio_unitario` (ELIMINADO
  el candado previo — ver ADR-101):** el margen OIR (`porcentaje_participacion_oir`/
  `importe_oir`/`iva_oir`/`total_oir`) simplemente se vuelve negativo; `precio_spot >= 0`
  sigue siendo el único piso.
- Editar `fecha_inicio_campania`/`fecha_fin_campania` de una OC (`_pre_update`) es
  **direccional**: AMPLIAR el rango se permite siempre (todo día ya capturado en las OE
  hijas seguía cabiendo); ANGOSTARLO (inicio más tarde o fin más temprano que el
  guardado) se valida contra `OrdenEstacionDia.fecha_transmision` de esas OE — si algún
  día ya capturado quedaría fuera del nuevo rango, `400 error_dominio`. No es un bloqueo
  en bloque: solo se dispara cuando de verdad se angosta al menos un lado.
- Editar `precio_unitario` (tarifa cliente) de una OC con OE ya creadas es libre — cada
  `OrdenEstacion` ya guarda su propio `precio_spot`, así que las existentes no se ven
  afectadas. Es **aviso, no candado** (a diferencia de otras ediciones de la OC que sí
  validan contra las OE hijas): `OrdenClienteForm.tsx` muestra un banner ámbar si la OC
  en edición ya tiene ≥1 OE, explicando que las existentes quedan con la tarifa anterior
  y las
  nuevas usarán la actualizada. No hay validación de backend — es puramente informativo.
- **Editar una `OrdenEstacion`** (`OrdenEstacionService.update`, `PUT
  /estaciones/{id}`) corrige errores de captura de tarifa/días/observaciones. Solo
  mientras la OE siga en `borrador`/`asignada` (`FROZEN_STATES_OE`) — desde
  `en_transmision` en adelante ya existen `Verificacion` ligadas a sus días exactos
  (spec: una por día), así que se bloquea con `409` para no dejarlas huérfanas o
  desalineadas. No reasigna `orden_id` ni `estacion_id` (eso sería, en la práctica, otra
  OE distinta) y revalida TODO lo que ya valida el alta: tarifa vs. OC, días dentro de la
  campaña, balance de spots de las OE hermanas (excluyendo a la propia OE que se edita),
  recalculando % OIR e importes desde cero. En el frontend, el vocabulario v5
  (`adapters/vocabulario.ts`) colapsa `borrador`/`asignada` en el único sub-estado
  `asignada_afiliado`, así que el botón "Editar" de `OrdenEstacionDetailPanel` se
  condiciona a ese sub-estado.
- **Crear una `OrdenEstacion` también se permite con la OC en `en_verificacion`**
  (`OrdenEstacionService.create`), no solo en `capturada`/`en_transmision` (bug real).
  `en_verificacion` se alcanza AUTOMÁTICAMENTE en cuanto la ÚLTIMA OE que existe EN ESE
  MOMENTO cierra (`avanzar_reales`) — no cuando de verdad ya no quedan spots de la OC por
  asignar. Si la primera OE capturada no agotó `total_spots`, la OC ya saltó a
  `en_verificacion` sin que quedara ninguna forma de asignar el resto. Sigue bloqueado
  desde `orden_cerrada` en adelante (facturada/cobrada/cancelada): esos sí son estados
  asentados, no un efecto colateral de cuántas OE existían al momento del cierre
  automático. El frontend no necesitó cambios: su vocabulario v5 ya agrupaba
  `en_transmision`/`en_verificacion` en el mismo estado `"orden_interna"` para el filtro
  de "OC elegible" — el bloqueo era puramente del backend.

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
    **Actualización (2026-09-21, ADR-098):** el backend retiró `mencion` de
    `DuracionSpot` — ahora vive solo como `producto` de `TarifaPlaza` (F0-02, ADR-097).
    El dropdown de `OrdenClienteForm.tsx` quedó en 3 valores (`20s`/`30s`/`60s`).

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
- **Rama `feature/f1-spots-bonificables`: Spots Bonificables en `OrdenCliente` (ADR-067,
  extensión aditiva a petición del equipo):** dos columnas nuevas
  (`cantidad_spots_bonificables`, `subtotal_spots_bonificables`, calculada) entre
  `total_spots` y `precio_unitario`. `subtotal`/`iva`/`total` pasan de calcularse sobre
  `total_spots` a calcularse sobre `total_spots − cantidad_spots_bonificables` (spots
  facturables) — `total_spots` conserva su significado para `OrdenEstacion` y el balance
  de spots, sin cambios ahí. Se propaga gratis a `FacturaCliente` (ADR-064) y al archivo
  plano del timbrador (ADR-066), sin tocar código de F2. Frontend: nuevo campo "Spots
  bonificables" en el formulario de alta/edición, bloque "Calculado" expandido de 3 a 5
  tarjetas, selector central `totalesOC()` actualizado (lista, detalle y cierre heredan
  el cálculo correcto sin cambios propios). Ver ADR-067 para la fórmula completa,
  incluida la nota de migración de SQL Server (`server_default` + `DROP COLUMN`).
  Verificado: 4 pruebas nuevas de backend + 6 de frontend, suites completas en verde.
- **Rama `feature/f1-spots-bonificables`: Spots Bonificables en `OrdenEstacion` (ADR-068,
  análogo a ADR-067 pero a nivel de OI):** columna `cantidad_spots_bonificables` entre
  "Tarifa por spot" y el resto de la captura. `importe_estacion` pasa de calcularse sobre
  `spots_asignados` a calcularse sobre `spots_asignados − cantidad_spots_bonificables`
  (spots facturables) — el balance de spots contra `OrdenCliente.total_spots` no cambia,
  los bonificables se siguen asignando/transmitiendo igual. Sin CHECK de BD para el tope
  contra spots asignados (esa suma vive en `OrdenEstacionDia`, tabla hija): la validación
  es del servicio. Se propaga gratis a la lista/detalle de OI y a la tabla de OE hijas
  del detalle de OC (todos consumen `oiImporte()`, actualizado en `selectors.ts`, sin
  tocarse ellos mismos). Frontend: nuevo campo "Spots bonificables" junto a "Tarifa por
  spot" en `OrdenEstacionForm.tsx`, panel "Cálculos en vivo" expandido con "Spots
  bonificables"/"Spots facturables". Ver ADR-068 para la fórmula completa. Verificado:
  3 pruebas nuevas de backend + 7 de frontend, suites completas en verde.

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
