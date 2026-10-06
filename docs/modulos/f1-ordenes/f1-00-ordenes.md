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

**`CalendarioPeriodoTransmision.tsx` — "Spots por día" genera un registro POR SPOT**
(ADR-127, petición del usuario): antes "Spots por día" = N agregaba, por cada fecha
elegida, UNA fila con `spots_diarios = N`. Ahora genera N filas (una por spot), cada una
con `spots_diarios = 1` y su propio "Horario de transmisión" editable — para que el
usuario le mueva la hora a cada spot del día, o quite/agregue spots sueltos de esa
fecha (ya funcionaba: `PeriodoTransmisionGrid.tsx` nunca validó unicidad de fecha).
El modelo ya soportaba 2+ filas con la misma fecha (`uq_orden_estacion_dia_oe_fecha_hora`
es `(orden_estacion_id, fecha, hora_inicio)`, no solo fecha) — para no chocar con ese
constraint desde el primer guardado, cada fila generada nace con un horario distinto
(+1 minuto por fila a partir del capturado); el usuario reacomoda cada una después.
Esto expuso un bug preexistente: Programados/Reales matcheaban sus "excepciones" por
`fecha_transmision`, no por fila — con 2 spots de la misma fecha el segundo override
pisaba al primero. Corregido en el mismo cambio: `avanzar_programados`/`avanzar_reales`
(backend) y `selectors.ts`/`RealesForm.tsx` (frontend) ahora matchean por
`orden_estacion_dia_id`.

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
ADR-027) — 3 adaptadores por `CORREO_BACKEND`: `CorreoLocal` (default de dev — no envía
nada real), `CorreoSES` (API de AWS vía boto3, access key/secret de IAM) y **ADR-138**
`CorreoSmtp` (SMTP real vía STARTTLS, credenciales SMTP dedicadas — p.ej. el endpoint
SMTP de SES, DISTINTAS del access key/secret que usa `CorreoSES`). **ADR-122:**
`CorreoLocal` además guarda el mensaje armado (MIME completo, mismo `construir_mime()`
que usan los otros 2) como archivo `.eml` en `_storage_local/correos_simulados/` — se
puede abrir con un cliente de correo de escritorio para revisar cómo quedó el mensaje
(asunto, cuerpo, adjuntos reales), sin mandar nada a internet ni depender de
credenciales de SES/AWS.

**ADR-120 (petición del usuario):** en la pantalla, este envío individual quedó
reemplazado por un diálogo "Enviar por correo"/"Imprimir" que aparece al generar
CUALQUIERA de los 3 PDFs (`OrdenEstacionDetailPanel.tsx`, `FilaPdf`). "Imprimir" abre el
PDF de siempre; "Enviar por correo" (`POST .../pdf/{tipo}/correo-orden-transmision`, sin
body) manda automáticamente sin captura manual de destinatario. Reusa
`LogEnvioCorreoOrdenEstacion` (mismos valores de `tipo_pdf` que el envío individual). El
endpoint individual por-tipo de arriba sigue existiendo en el backend (sin UI propia)
por si se necesita un envío puntual a un solo destinatario.

**ADR-140 (petición del usuario):** el destinatario depende del `tipo` — antes los 3
mandaban siempre a los contactos del afiliado, pero "Orden de servicio" y "Reales" son
documentos que le interesan al ANUNCIANTE (quien contrató la pauta), no al afiliado.
Ahora: `servicio`/`reales` → TODOS los `ContactoAnunciante` **activos** con correo
cargado del Anunciante de la orden; `programados` → TODOS los `ContactoAfiliado`
**activos** con correo cargado del Afiliado dueño de la estación (sin cambio, es el
documento operativo entre OIR y la emisora). El botón de cada PDF se deshabilita de
antemano según el catálogo que le corresponda (`contactoAnuncianteApi.listPorAnunciante`
para servicio/reales, `contactoAfiliadoApi.listPorAfiliado` para programados) — un tipo
habilitado no habilita al otro.

**ADR-126 (corrección de un bug reportado por el usuario):** el diseño original de
ADR-120 mandaba SIEMPRE el mismo "paquete fijo" — el PDF de Programados — sin importar
cuál de los 3 botones (#1 Servicio, #2 Programados, #3 Reales) disparó el diálogo. El
usuario probó los 3 y detectó que todos adjuntaban el PDF equivocado. Ahora cada botón
manda **su propio** PDF (+ Material a Transmitir, si la OE tiene): `tipo` viaja en la URL
(`/pdf/{tipo}/correo-orden-transmision[/eml]`) y en `LogEnvioCorreoOrdenEstacion.tipo_pdf`
(ya no se escribe el valor genérico `"orden_transmision"`, que se conserva solo para leer
bitácora histórica). En el frontend, cada `FilaPdf` vuelve a mostrar su propia línea de
"último envío" filtrando el historial por su propio `tipo` (antes de ADR-120 ya era así;
ADR-120 lo había colapsado en una sola línea a nivel de OE, que ya no tenía sentido con
un paquete fijo único — con el bug corregido, tampoco lo tiene con un paquete genérico).

**ADR-124 (petición del usuario):** junto a "Enviar por correo"/"Imprimir", un tercer
ícono 📧 ("Abrir correo") — descarga el mismo `.eml` de ADR-122 (mismos
destinatarios, PDF de `tipo` desde ADR-126) vía `POST .../pdf/{tipo}/correo-orden-transmision/eml`,
para que el usuario lo abra con doble clic en su cliente de correo de escritorio
(Outlook confirmado: lo recibe como un borrador NUEVO editable — Outlook trata un
`.eml` ajeno como reenvío, con "RV:" en el asunto y el mensaje original citado abajo —
con "Para"/adjuntos ya resueltos y "De" tomado de la cuenta propia del usuario en
Outlook, no del archivo) y lo mande él mismo desde su cuenta — útil mientras SES no esté
en producción. No reemplaza el botón verde de envío automático; son dos caminos
independientes que el usuario elige.

**ADR-125:** al probar con Outlook de escritorio real, el `.eml` se serializa con CRLF
(`email.policy.SMTP`; Outlook de escritorio es estricto con esto, a diferencia de
Outlook Web, que lo toleraba sin problema). Se probó además anteponer los destinatarios
como texto en el cuerpo (para copiar/pegar en "Para" tras "Reenviar" — "Responder a
todos" sí precarga "Para" pero pierde los adjuntos, es un trade-off real de Outlook, no
un bug de este sistema), pero se quitó a petición del usuario; el cuerpo queda igual
que el del envío automático. El tooltip del ícono sí se conserva: **"Usa Reenviar para
enviar el correo"**.

**ADR-144 (petición del usuario, corrige ADR-124/125):** el `.eml` ahora SÍ abre directo
como mensaje nuevo editable — `construir_mime()` agrega el encabezado `X-Unsent: 1`
(soportado por Outlook y otros clientes de escritorio) cuando se llama con
`como_borrador=True`, algo que ADR-124 no sabía que existía al concluir que el modo
lectura era "un límite fijo". Solo `generar_eml_orden_transmision()` lo activa; los
adaptadores de envío real (SES/SMTP/Local) nunca lo hacen, para no marcar como "no
enviado" un mensaje que sí se mandó/guardó. Tooltip actualizado a **"Abre un borrador
nuevo listo para enviar"**.

**ADR-145 (petición del usuario) — se retira el envío real; "Abrir correo" queda como
ÚNICO flujo de correo:** tras probar SES real (credenciales SMTP de ADR-138) y toparse
con que la cuenta sigue en modo *sandbox* (remitente no verificado — trabajo de IT fuera
de alcance), el usuario decidió no perseguir el envío directo y quedarse solo con "Abrir
correo". Se retiraron por completo: el botón "✉️ Enviar por correo" y su handler en
`FilaPdf`, los 2 endpoints de envío (`POST .../pdf/{tipo}/enviar-correo`,
`POST .../pdf/{tipo}/correo-orden-transmision`), sus funciones de servicio, y TODO
`app/integrations/correo/` salvo `mime.py` (que sigue usando el `.eml`) — es decir, los 3
adaptadores (`CorreoLocal`, `CorreoSES`, `CorreoSmtp` de ADR-138) y la fábrica
`get_correo()`/`CORREO_BACKEND` descritos en el párrafo de ADR-105 más arriba **ya no
existen**; ese párrafo queda como registro histórico de por qué se construyeron, no
como descripción del estado actual. "Abrir correo" (ADR-124/144) NO cambió en nada su
comportamiento — sigue gateado por los mismos catálogos de contactos activos
(ADR-140) y sigue escribiendo en la misma bitácora `LogEnvioCorreoOrdenEstacion` (ahora
el único flujo que la alimenta, siempre `exitoso=true`).

**ADR-118 (petición del usuario):** la tabla de días del PDF #2 (Horarios Programados)
quitó "Pedidos"/"Asignados" y agregó "Material a Transmitir" (mismo criterio que
`nombreMaterial()` del frontend — override del día o el primero subido) + un solo
"Horario" (ya no Hora Inicio/Hora Término por separado, coherente con ADR-107/108).

**ADR-156 (petición del usuario):** el PDF #1 (Orden de Servicio) y el PDF #3 (Horarios
Reales) nunca se habían actualizado con ese mismo criterio — #1 seguía con 2 columnas
"Inicio"/"Término" (mismo valor repetido) en su tabla de "Periodo de Transmisión"; #3
mostraba su columna "HORA" como un rango `inicio - fin` (también el mismo valor
repetido). Ambos pasan a un solo horario: #1 consolida en una columna "Horario de
Transmisión", #3 deja "HORA" con un solo valor.

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

**ADR-146 (petición del usuario) — 2 componentes nuevos, "Reporte del afiliado" retirado
de esta pantalla:** junto a Evidencias/Formato de Horarios Reales, una segunda fila con
"Carga de Órdenes Reales Desde Layout" (tabla nueva `orden_estacion_layout_real`, lista
BLANCA — inicialmente csv/xlsx/xls/txt, restringida a SOLO csv por ADR-155) y "Formato de Horarios
Reales Enviado al Cliente" (tabla nueva `orden_estacion_formato_real_cliente`, misma
lista negra que ADR-123 pero EXCLUYE además audio — a diferencia de "Formato de Horarios
Reales", que sí lo admite). `csv`/`txt` no tienen firma binaria verificable (texto
plano): `leer_adjunto()` ahora acepta una firma vacía como "sin validar contenido para
esta extensión" en vez de fallar. Se retiró "Reporte del afiliado" de "Capturar Reales"
(`RealesForm.tsx`) — mismo criterio que ADR-143: se dejó de mostrar/enviar desde el
frontend (incluida la línea de `toApi.ts` que lo mandaba incondicionalmente en cada
"Avanzar a 2.3"), pero `OrdenEstacion.reporte_reales_ref` y su endpoint genérico de
adjuntos quedan intactos en el backend.

**ADR-147 (petición del usuario) — el CSV de "Carga de Órdenes Reales Desde Layout" ya
se parsea y reemplaza la tabla:** columnas `Estacion, Fecha, Hora, Spots` (Spots
opcional, default 1). `Estacion` es un control (compara normalizado contra la estación
de esta OE, sin crear datos de otra). Subir un CSV REEMPLAZA COMPLETO lo cargado en la
tabla de "Capturar Reales" — un día que no viene en el archivo vuelve a su valor
programado (confirmado con el usuario). Una fila inválida (estación distinta, valor no
parseable) se ignora y se reporta, sin tumbar el resto del archivo. El usuario sigue
teniendo que presionar "Avanzar a 2.3 →" para persistir — cargar el layout solo llena la
tabla, igual que una edición manual por fila. xlsx/xls/txt ya no se pueden subir en
absoluto (ADR-155: se quitaron de la lista blanca, nunca se parseaban).

**ADR-148/ADR-150 (petición del usuario):** salir de "Capturar Reales" sin "Avanzar a
2.3" borra el archivo de layout que se haya subido EN ESA MISMA SESIÓN (mismo criterio
que los overrides de la tabla, que ya se descartaban solos al no persistir hasta
"Avanzar") — uno que ya existiera de una sesión anterior ya avanzada no se toca.
`RealesForm.tsx` recuerda qué archivos había al abrir la pantalla; la limpieza vive en
la función de limpieza de un `useEffect` (corre al DESMONTAR el componente), no en el
`onClick` de un botón en particular — ADR-148 la había atado solo al botón "Cancelar",
y el usuario reportó que si se abandonaba la pantalla por otra vía (navegar a otra
sección) el archivo se quedaba sin borrar; ADR-150 la movió al desmontaje para cubrir
cualquier forma de salir.

**ADR-149 (petición del usuario) — suma de spots + días nuevos:** si 2+ filas del CSV
comparten la MISMA fecha+hora, sus `Spots` se SUMAN (no se pisan entre sí). Una
fecha+hora que NO existe entre los días de esta OE ya NO es un error — se ofrece como
**día NUEVO** a crear al avanzar a 2.3, mismo criterio que asignar una hora distinta al
crear la OE (ADR-127: una hora distinta, aunque sea por 1 minuto, es un registro
distinto). El día nuevo nace con `spots_asignados = spots_solicitados =
spots_verificados` = la suma de `Spots` del CSV (confirmado con el usuario) — por
construcción nunca genera `Incidencia` (verificado == programado). Solo se crea de
verdad al "Avanzar a 2.3" (`POST .../reales`, body `dias_nuevos`), validando lo mismo
que un día nuevo al crear/editar la OE: rango de campaña de la OC, que no exista ya un
día con esa fecha+hora, y el balance de spots de TODA la OC. Una fecha+hora nueva cuya
suma de spots da 0 no se puede crear (`spots_solicitados` exige > 0) y se reporta como
error.

**ADR-151 (petición del usuario, corrige ADR-149):** sin cargar ningún layout, la
tabla sigue el flujo de SIEMPRE (`oe.periodo_transmision`, edición manual). En cuanto
un layout aporta algo útil, la tabla PRINCIPAL se reconstruye COMPLETA a partir de lo
que trajo el archivo — ya NO hay una tabla aparte de "días nuevos": los días
existentes que el layout tocó y las propuestas de día nuevo conviven en la MISMA
tabla (columnas Día/Fecha/Horario/Spots/Resultado/Editar/✕, igual que siempre; un
día nuevo muestra "Nuevo" en Resultado en vez de bonif./desc./sin cambio). Un día del
periodo original que NO viene en el archivo ya no se queda visible como "sin cambio"
— se quita de la vista por completo (el backend lo sigue verificando igual al
avanzar, sin incidencia; es una decisión solo de qué se MUESTRA en pantalla).
**Corregido por ADR-157:** esto resultó ser un vacío real, no solo una decisión de UI
— ver abajo.

**ADR-152 (petición del usuario):** un día nuevo propuesto por el layout que el
backend rechazaría al avanzar (fuera del rango de campaña de la OC, o fecha+hora
duplicada) se marca EN LA MISMA FILA de la tabla — fondo rojo + el motivo debajo de
"Nuevo" — en vez de que el usuario se entere hasta que "Avanzar a 2.3" falle con un
mensaje genérico. El botón "Avanzar a 2.3" se deshabilita mientras exista alguna fila
así. El balance de spots de toda la OC sigue validándose solo al avanzar (requiere una
consulta al backend que esta validación local no hace).

**ADR-153 (petición del usuario):** la celda "Fecha" de un día nuevo del layout
también se puede editar inline (antes solo Hora/Spots) — mismo `<input type="date">`
que llama a `actualizarDraftNuevo`, para corregir una fecha fuera de rango sin tener
que volver a subir el CSV.

**ADR-154 (corrige un bug de ADR-153):** la fila de cada día nuevo usaba una `key` que
incluía `fecha`/`hora` — al editar la Fecha, React remontaba el `<input type="date">`
a media edición y el usuario perdía el foco antes de terminar de teclear, dejando un
valor incorrecto. Se cambió a una `key` estable por índice.

**ADR-155 (petición del usuario):** "Carga de Órdenes Reales Desde Layout" se
restringe a SOLO `.csv` (antes csv/xlsx/xls/txt) — xlsx/xls/txt nunca se parseaban,
solo se guardaban sin avisar que no se iban a aplicar.

**ADR-157 (petición del usuario, corrige ADR-151):** "validar lo que el botón OK hace
actualmente... esas validaciones no las hemos hecho cuando cargamos el layout" — la
carga del layout ahora CONCILIA de verdad contra lo programado, de los 4 casos que
pidió el usuario: (1) diferencia en spots en un día que coincide → ya marcaba
bonif./desc. correctamente (sin cambios); (2) diferencia de hora → el usuario
confirmó NO intentar adivinar un match por solo fecha (se resuelve con los otros 2
casos: el horario viejo queda como faltante, el nuevo como "Nuevo"); (3) registros
adicionales → ya se marcaban "Nuevo" (sin cambios); (4) **registros faltantes**
(un día ya programado que el CSV no menciona) — antes desaparecía de la tabla
(ADR-151); ahora `_parsear_layout_reales_csv()` lo agrega a `aplicados` con `spots=0`
(como si el usuario lo hubiera editado a mano a 0), así que sigue viéndose en la
tabla con su descuento y genera su `Incidencia` normal al avanzar. Un día ya
**cancelado** (ADR-104) se excluye de este chequeo (ya tiene su propia
`Verificacion`).

**ADR-158 (petición del usuario):** el panel "Al avanzar a 2.3 se generarán" (bonif./
desc./impacto neto) solo sumaba `oe.periodo_transmision` — un día NUEVO del layout
(ADR-149) nunca entraba a esa cuenta, aunque sus spots sean reales adicionales a lo ya
vendido ("se agregaron 2 nuevos spots y no los registró como bonificaciones"). Un día
nuevo siempre cuenta como bonificación completa en el panel (nunca genera `Incidencia`
en el backend, eso no cambia — es puro ajuste de presentación en el frontend).

