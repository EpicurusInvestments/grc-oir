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

**`producto_tarifa` (NUEVO, fuera de la spec) y `duracion_spot`** (ADR-167, petición del
usuario): sección "Campaña y montos" de "Orden de Servicio" — se eligen del catálogo
`DuracionSpotCatalogo` ("Producto Duración", F0-06), mismo patrón Producto→Duración que
Tarifa (ADR-166). `duracion_spot` dejó el CHECK `20s|30s|60s` y se volvió NULLABLE (antes
NOT NULL) — decisión tomada con el usuario, ver ADR-167 en `docs/arquitectura.md`. Esta
columna es puramente informativa a nivel de campaña: ADR-106 ya había desconectado su
herencia hacia `OrdenEstacion.duracion_spot` (que sigue con su propio selector fijo, sin
cambios aquí). El literal "sin resultado" nunca aparece como opción seleccionable en
Duración; si el producto elegido (p.ej. Mención) no tiene ninguna duración real en el
catálogo, el combo de Duración simplemente queda deshabilitado ("Selecciona…", `NULL` por
dentro) y NO bloquea nada.

**ADR-168 (petición del usuario, probado en vivo):** a diferencia de `duracion_spot`,
`producto_tarifa` SÍ es obligatorio al crear — gatea el resto de "Campaña y montos":
Total de spots/Spots bonificables/Precio unitario están deshabilitados hasta elegir un
producto, y no se puede guardar la orden sin él. La columna de BD sigue NULLABLE (la
obligatoriedad vive en el schema `OrdenClienteCreate`, no en un `NOT NULL` — evita tener
que inventar un valor de relleno para filas ya existentes sin el campo).

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
estaciones"): AMBOS elegidos POR ESTACIÓN — secuencia del formulario: Estación →
Producto → Duración → Tarifa. NO confundir `producto_tarifa` con el campo `producto` de
esta misma tabla (heredado de `OrdenCliente.producto`, "Campaña" en texto libre). Al
crear/editar, el servicio busca la tarifa ACTIVA de `TarifaPlaza` para (estación +
`duracion_spot` de ESTA OE + `producto_tarifa` — ADR-158: ya NO filtra también por
`Estacion.tipo_senal`, retirado de `TarifaPlaza` por redundante con `estacion_id`) y,
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
tarifa).

**ADR-170 (petición del usuario, reemplaza el criterio de ADR-115 para este flujo
específico):** "un precio ya tecleado a mano nunca se pisa" dejó de ser cierto al cambiar
de Producto o Duración — ahora, cambiar cualquiera de los dos SIEMPRE limpia "Tarifa por
spot" primero (los `onChange` llaman `setPrecioSpot("")` explícitamente), y luego el
mismo mecanismo de siempre recarga la tarifa de la nueva combinación si existe en el
catálogo. Antes, un precio editado a mano sobrevivía al cambiar de combinación —
confundía, porque parecía que la tarifa vieja seguía aplicando. El criterio de ADR-115
("no pisar un precio no vacío") sigue intacto para cualquier otro caso (p.ej. no pisar
`precio_spot` ya guardado de una OE existente al montar el formulario para editarla).

**ADR-169 (petición del usuario, tras probar ADR-167/168 en "Orden de Servicio"):**
`producto_tarifa`/`duracion_spot` dejan los CHECK/enum (`spot│mencion│control_remoto│
patrocinio` / `20s│30s│60s`) y pasan a texto libre — se eligen del catálogo
`DuracionSpotCatalogo` ("Producto Duración", F0-06), mismo patrón que Tarifa (ADR-166) y
"Orden de Servicio" (ADR-167). `producto_tarifa` sigue obligatorio al crear (sin cambio);
`duracion_spot` se vuelve OPCIONAL (antes CHECK NOT NULL) — si el producto elegido no
tiene ninguna duración real en el catálogo (p.ej. Mención), el select de Duración se
deshabilita ("Sin duración capturada para este producto") pero la sección "Tarifa por
spot" se habilita igual con solo elegir el Producto (antes dependía de Duración) — se
puede teclear la tarifa y seguir llenando el resto del formulario sin bloquear nada. La
lógica de `_tarifa_sugerida()` (buscar la tarifa activa y auto-cargar `precio_spot`) NO
cambia: sigue siendo una comparación de texto exacta contra `TarifaPlaza` (texto libre
desde ADR-166), así que un producto/duración MÁS ALLÁ del enum anterior encuentra su
tarifa sembrada exactamente igual.

**ADR-173 (petición del usuario):** al crear una OE ya amarrada a su OC (`ocIdFijo`, el
flujo normal desde "+ Asignar estaciones"), Producto/Duración arrancan precargados con
los que esa OC capturó (en vez de vacíos) — si la OC no capturó Duración, arranca vacía,
sin cambiar el gateo de siempre (deshabilitada si el producto no tiene duraciones reales
en el catálogo). El usuario sigue pudiendo cambiar cualquiera de los dos; si la
combinación precargada tiene tarifa sembrada, se autocarga sola igual que si se
eligieran a mano. Nada más de la pantalla cambia — es solo el valor inicial.

**ADR-182 (petición del usuario):** la tarjeta "Orden de Servicio de origen" de
`OrdenEstacionForm.tsx` muestra también el nombre comercial del Anunciante heredado
(`findAnunciante(oc.anunciante_id)`, "—" si no está en el catálogo cargado) — puramente
informativo, de solo lectura. Se muestra en cuanto `oc` resuelve, tanto si la OE llega ya
amarrada a su OC (`ocIdFijo`/edición) como si se elige a mano en el alta suelta (bug real
de la primera versión, que solo lo mostraba en el primer caso — corregido el mismo día).

**ADR-183 (petición del usuario):** `motivo_cambio_tarifa` (ver párrafo de ADR-102/106
arriba) deja de capturarse en texto libre y pasa a un select con las Descripciones del
catálogo Constantes del Sistema, grupo `MotivoCambio`, clave `CambioTarifa`/
`CambioTarifa_N` — el MISMO catálogo que ya usa Tarifa (F0-02, ADR-179). Cae a texto
libre si el catálogo no tiene opciones activas.

**ADR-183b (petición del usuario, mismo día, corrige el criterio de visibilidad de
ADR-183):** a diferencia de Tarifa/Orden de Servicio (donde el campo queda SIEMPRE
visible, solo deshabilitado), aquí el bloque se OCULTA por completo salvo que lo ÚLTIMO
que el usuario tocó haya sido la tarifa misma Y de verdad diverja —
`tarifaEsUltimoCampoTocado`, en `false` por defecto y puesto en `true` solo por el
`onChange` del input de tarifa; tocar después Estación, Producto, Duración o Spots
bonificables lo vuelve a poner en `false` (oculta el bloque de nuevo). La obligatoriedad
de capturar el motivo (y lo que se manda al backend) sigue EXACTAMENTE la misma
condición que la visibilidad (`requiereMotivoTarifa`) — para no dejar un candado
invisible: si el usuario toca otro de esos campos después de divergir, ESE guardado ya
no exige ni audita motivo, aunque el precio siga siendo distinto al de catálogo.

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
`PeriodoTransmisionGrid.tsx`. **ADR-211/ADR-213 (petición del usuario):** en el detalle
ya no se permite subir NI quitar material desde ahí — solo ver/descargar lo que ya
existe; para agregar o eliminar hay que entrar a "Editar" (`MaterialATransmitir` gana
`permitirSubir`/`permitirQuitar`, ambos `false` en el detalle, `true` —default— en
edición).

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

**"Clonar" (ADR-210, petición del usuario — 2 entradas al mismo mecanismo):** precarga el
formulario de ALTA (no edición) con los datos de otra OE: Estación, Producto, Duración,
Tarifa por spot, Spots bonificables, Observaciones, el Período de transmisión completo
(visible de inmediato en la tabla) y el **Material a Transmitir** (los audios se clonan
vía su referencia de almacenamiento S3, `ref` — el backend la expone desde el Fix 3 de
ADR-210; cero descarga/re-subida del archivo), con cada día de la tabla ya trayendo
elegido el material que le correspondía en la OE original (Fix 4 — no un reparto
genérico por posición, la asignación EXACTA que tenía). Pensado para capturar varias OE
casi idénticas seguidas (p.ej. la misma campaña en estaciones distintas) sin volver a
teclear nada. Mientras se resuelve esa consulta se muestra "Cargando material de la
Orden de Transmisión clonada…"; si falla, el material queda vacío y el usuario lo sube a
mano, como en cualquier alta (ADR-110 sigue aplicando: sin material, el período se ve
pero queda sin editar). Tampoco se clonan `orden_estacion_dia_id` ni `cancelada`/
`hora_real` de cada día (pertenecen al historial de la OE anterior) — las
filas clonadas nacen como días nuevos; ni el motivo del cambio de tarifa (campo
transitorio, el backend no lo expone de vuelta) — si la tarifa clonada diverge del
catálogo, el selector igual aparece de inmediato (Fix 2) para que el usuario lo vuelva a
elegir. Dos formas de llegar a esto:
- **Manera 1 — modal post-guardado:** al guardar una OE nueva, el modal "¿generar
  otra?" (ADR-116) tiene un tercer botón "Clonar" que precarga la OE recién guardada.
- **Manera 2 — desde la lista:** la tabla de "Órdenes de Transmisión" tiene una columna
  "Acciones" con un botón "📋 Clonar", **visible solo en renglones en sub-estado 2.1
  "Asignada al afiliado"** — antes de que la OE avance de sub-estado tiene más sentido
  partir de ella para capturar otra igual. El clic no selecciona la fila ni abre el
  panel de detalle. "Cancelar" en ese alta se queda en "Órdenes de Transmisión" (nunca en
  "Órdenes de Servicio") — fix: la manera 2 fija la OC igual que "+ Asignar estaciones",
  pero nunca pasó por esa pantalla, así que no debe regresar ahí.

Implementación: prop `clonarDesde` en `OrdenEstacionForm` (separada de `oe`/edición, el
Selector de Estación sigue totalmente editable — solo se bloquea en modo edición) y
tercer botón opcional en `ConfirmDialog` (`extraLabel`/`onExtra`) para la manera 1 —
detalle técnico en `docs/arquitectura.md` (ADR-210).

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

**ADR-184/185 (petición del usuario) — "Hora Inicio"/"Hora Fin" vuelven a ser un RANGO
real, y "Datos de la Orden de Transmisión" agrupa visualmente por fecha (sin tocar
Reales/backend/layout):** ADR-184 cambió el generador por calendario para pedir un rango
real (`horaInicio`/`horaFin`) en vez de un solo punto (revierte ADR-108) — "Spots por
día" = N **sigue generando N filas reales** (1 spot c/u, sin cambio de ADR-127), ahora
repartidas dentro de ese rango con `repartirHoras` (`intervalo = (hora_fin − hora_inicio)
/ N`) en vez del incremento de 1 minuto. ADR-185 resuelve dónde se VEN esas N filas:
**`PeriodoTransmisionGrid.tsx`** agrupa todas las filas reales de una misma fecha en **UN
solo renglón visible** (Hora Inicio = la más temprana, Hora Fin = la más tardía, Spots =
la suma) — por dentro siguen existiendo N filas reales independientes, cada una con su
propio `orden_estacion_dia_id`. Editar Hora Inicio/Hora Fin del renglón regenera esas N
filas con `repartirHoras`; editar Spots hace lo mismo SOLO si hay un rango real
capturado (Hora Inicio ≠ Hora Fin) — si Hora Inicio === Hora Fin (el default histórico de
"+ Agregar día"), el cambio de Spots no reparte: solo actualiza `spots_diarios` en el
renglón existente, conservando su id, igual que siempre. "Material a Transmitir" y
"Cancelar transmisión" ahora aplican a todo el grupo de la fecha a la vez (antes, por
fila individual) — simplificación de UX explícita, no pedida palabra por palabra.
**Reales (`RealesForm.tsx`), el layout CSV y el backend NO se tocan** — ambos ya
consumían `periodo_transmision`/`Verificacion` como 1 fila/1 registro por
`orden_estacion_dia_id` real (confirmado leyendo el código: `Verificacion` tiene
`UniqueConstraint("orden_estacion_dia_id")`, 1:1 real con `OrdenEstacionDia`), así que
"los mismos registros de siempre" se cumple sin cambios ahí. Ver ADR-185 en
`docs/arquitectura.md` para el detalle completo, incluidos los 2 intentos previos
descartados.

**ADR-186 (corrige un bug real de ADR-185):** el renglón agrupado mostraba, como "Hora
Fin", el ÚLTIMO PUNTO del reparto (p.ej. 08:13 p.m. con 5 spots en 09:05 a.m.–11:00 p.m.),
no el fin de rango que el usuario capturó. Causa: `repartirHoras` colapsaba
`hora_termino` al mismo punto que `hora_inicio` en cada fila repartida. Fix: todas las
filas de un reparto ahora comparten `hora_termino = horaFin` (el fin de rango capturado),
y solo varía `hora_inicio` entre ellas — así, al agrupar por fecha (mínimo de
`hora_inicio`, máximo de `hora_termino`), se recupera EXACTO el rango tecleado, tanto
recién generado como al reabrir una orden ya guardada para editar. También se le dio
estilo de tarjeta al calendario (`.rdp-wrapper` en `theme.css`: fondo, borde, radio y
acento teal de F1, en vez de un `margin: 1px` casi invisible).

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

**ADR-187 (petición del usuario) — 1 material por SPOT, ya no 1 default compartido:**
"Material a Transmitir" deja de tener un solo default (`audios[0]`) para todos los días —
cada spot (cada fila real `OrdenEstacionDia`, que post-ADR-127/185 ya es 1 por spot)
recibe su propio material por POSICIÓN, en el orden de captura de los audios (spot 1 →
#1, spot 2 → #2…, repitiendo cíclicamente si hay menos materiales que spots). Sin cambios
de backend/esquema: cada fila YA tenía su propio `orden_estacion_audio_id`, lo único
nuevo es el algoritmo de asignación (`asignarPorPosicion`, `CalendarioPeriodoTransmision.tsx`)
y que se escribe de inmediato al crear la fila (generador o "+ Agregar día"), en vez de
quedar en blanco esperando el fallback de un solo default. La columna de la grid pasa de
"1 nombre + botón 🔄" a un multi-select de CASILLAS (`CheckboxMultiSelect`, nuevo en
`shared/ui/` — campo cerrado con el resumen de lo elegido; al abrir, buscador +
"[Selecciona todos]" + lista con un checkbox por opción) por fecha: muestra los
materiales ya asignados a esa fecha y reparte cualquier cambio 1 a 1 sobre sus filas
reales, validando que no excedan los spots de ese renglón (las opciones de más se
deshabilitan, no desaparecen). Importante: un día con 1 sola fila real (capturado sin rango, "+ Agregar día" con
`spots_diarios` grande) solo puede llevar 1 material — el tope es cuántas filas reales
tiene el grupo, no el conteo de spots capturado; varios materiales distintos en un mismo
día requieren que ese día tenga varias filas reales de verdad (rango real + 2+ spots).

**ADR-188 (petición del usuario) — una fecha puede repetirse en el calendario:** antes,
una fecha que ya tenía filas salía deshabilitada en el `DayPicker` y se descartaba en
silencio al generar; el usuario confirmó que sí puede querer capturar más spots para un
día ya existente (p.ej. una segunda tanda más tarde). Se quitó el bloqueo — gracias al
agrupado por fecha (ADR-185), generar filas de más para una fecha existente se ve
automáticamente como "sumar spots al mismo renglón", sin ninguna lógica de fusión
aparte. Único cuidado: los horarios nuevos no deben chocar con `hora_inicio` de las
filas ya existentes de esa fecha — se corren +1 minuto hasta encontrar uno libre (mismo
criterio que "+ Agregar día", ADR-134); si la fila es un PUNTO (1 spot, Hora inicio =
Hora fin), se corren ambos campos juntos para no violar el CHECK `hora_fin >=
hora_inicio`.

**ADR-189 (corrige un bug real) — el tope de "Material a Transmitir" es los SPOTS, no
cuántas filas reales existen:** un día sin rango ("+ Agregar día") se queda como 1 sola
fila real aunque sus spots sean varios — el usuario reportó que, con 2 spots así, el
multi-select solo dejaba elegir 1 material. El tope (`maxSelected`) pasa a ser
`grupo.spots`; si el usuario elige más materiales distintos de los que hay filas, el
grupo se EXPANDE a `grupo.spots` filas (mismo efecto que editar Hora Inicio/Hora
Fin/Spots, pierden su `orden_estacion_dia_id`) — con un rango real reparte con
`repartirHoras`; sin rango, con la función nueva `dividirPuntoEnFilas` (separa 1 minuto
por fila, criterio histórico de ADR-127, solo para que cada una tenga su propio
`hora_inicio`).

**ADR-190 (corrige un bug real) — `repartirHoras` ya no genera `hora_inicio`
repetidos:** reportado en vivo como "Network Error" al guardar — el log del backend
mostró `UNIQUE constraint failed` con 2 filas de la misma fecha insertándose con el
mismo `hora_inicio`. Causa: tras expandir un día por ADR-189, el grupo deja de ser un
"punto" (Hora Inicio ≠ Hora Fin por 1 minuto); seguir editando materiales llamaba a
`repartirHoras` con ese rango angosto (1 minuto) para varios spots — el redondeo
(`Math.round`) colapsaba varias posiciones en el mismo minuto. Fix: `repartirHoras`
ahora corre cada punto que choca +1 minuto hasta encontrar uno libre (igual que
`agregarFila`/`generar()`); si eso empuja algún punto más allá del fin capturado, el fin
efectivo de TODAS las filas del reparto se extiende para seguir cumpliendo `hora_fin >=
hora_inicio`.

**ADR-191 (petición del usuario) — el combo de "Estación" muestra "Siglas Frecuencia
TIPO Nombre" (revierte ADR-136, sin Plaza):** antes armaba
`{nombre_estacion}-{siglas}-{frecuencia}` (guiones, 3 partes). Ahora cada `<option>`
concatena `[siglas, frecuencia, tipo_senal.toUpperCase(), nombre_estacion]`, filtrando
partes vacías y uniendo con un solo espacio — ej. "XHMT 90.1 FM Multimedios Estrellas de
Oro". Cambio 100% de presentación, un solo `<select>` afectado; la Plaza sigue viéndose
sin cambio en "Datos heredados de la estación", debajo del selector.

**ADR-192 (petición del usuario) — los 3 PDFs de OrdenEstacion vuelven a mostrar Hora
Inicio Y Hora Fin (revierte ADR-118/155/156):** esos ADRs habían consolidado el horario
a un solo valor en `orden_estacion_pdf.py`, asumiendo que `hora_inicio == hora_fin`
siempre (supuesto que venía de ADR-108) — supuesto inválido desde ADR-184 en adelante
(la captura web volvió a un rango real), y nadie actualizó el backend. Fix: PDF Servicio
vuelve a 2 columnas "Hora Inicio"/"Hora Fin" en la tabla de días; PDF Programados vuelve
a mostrar el rango completo en el texto "Horario: … A …"; PDF Reales vuelve a mostrar
"inicio - fin" en la columna "HORA". No hay PDF de Orden de Servicio separado para la OC
— el único existente es el de la OE, corregido aquí.

**ADR-193 (petición del usuario) — los 3 PDFs agregan "Marca" y "Producto" (catálogo
F0-06); "Producto" se relabeled a "Campaña":** auditoría previa encontró que "Marca" no
se cargaba ni se mostraba en ningún PDF, y que lo etiquetado como "Producto"/"CAMPAÑA"
era en realidad `oc.producto` (texto libre, la Campaña) — el Producto de verdad
(`oe.producto_tarifa`, conectado al catálogo F0-06 por ADR-166/169) no aparecía en
ninguno. Fix: `_cargar_contexto` carga `Marca` (vía `oc.marca_id`); los 3 PDFs muestran
"Marca", "Campaña" (`oc.producto`, renombrado) y "Producto" (`oe.producto_tarifa`) como 3
campos distintos. Categoría/Contrato quedaron fuera de este cambio (decisión explícita
del usuario) — ninguno de los dos se carga todavía en el contexto de los PDFs.

**ADR-194 (petición del usuario) — PDF de Reales: los valores después de los ":" ya no
van en negritas:** `_campo_negrita`/`_campo_negrita_der` (exclusivas de
`generar_pdf_reales`) envolvían etiqueta Y valor en `<b>` — ahora solo la etiqueta. Los
PDFs de Servicio y Programados ya mostraban el valor sin negritas, sin cambio.

**ADR-195 (petición del usuario) — "Orden de Servicio de origen" pone el Anunciante
heredado del lado derecho:** en `OrdenEstacionForm.tsx`, el folio/selector de la OC y el
bloque de Anunciante (heredado, ADR-182) se envuelven en un `.r2` (grid de 2 columnas) en
vez de ir apilados — cambio 100% de layout. Ajuste el mismo día (*"pégalo más a la
derecha"*): se reemplaza por `display: flex; justifyContent: space-between`, que empuja
el Anunciante al borde derecho real de la tarjeta en vez de dejarlo a medio camino.
Segundo ajuste, mismo día (*"hazlo del doble o triple de largo sin afectar al
anunciante"*): el selector de la izquierda quedaba angosto con `space-between` — pasa a
`flexGrow: 1` (toma todo el espacio sobrante) y el Anunciante a `flexShrink: 0` (ancho
fijo, mismo borde derecho de antes).

**ADR-196 (petición del usuario, corrige un bug real) — el detalle de OE y los PDFs de
Servicio/Programados vuelven a agrupar el período de transmisión por fecha (Reales, sin
cambio):** desde ADR-185, SOLO la grid de captura (`PeriodoTransmisionGrid.tsx`) agrupaba
visualmente las N filas reales de una fecha (1 por spot, ADR-127) en un renglón — el
detalle (`OrdenEstacionDetailPanel.tsx`) y los PDFs de Servicio/Programados seguían
mostrando 1 renglón por spot. Fix: `agruparPorFecha`/`GrupoFecha` se exportan y el
detalle los reusa; el backend agrega `_agrupar_dias_por_fecha` (mismo criterio) para las
tablas de Servicio y Programados — "Total de Spots"/"Total de Días" también se recalculan
desde los grupos. De paso se corrige `_nombre_material` (seguía con el criterio VIEJO de
ADR-107, nunca actualizado a ADR-187: ya no hay default compartido, regresa `None` sin
override propio) y se agrega `_materiales_grupo`: la columna "Material a Transmitir" de
Programados lista TODOS los materiales distintos del día, separados por coma (antes solo
1). El PDF de Reales, además, revierte el rango `inicio - fin` que ADR-192 le había
puesto en la columna "HORA" — vuelve a ser un solo horario (`hora_inicio`), ya que
`hora_fin` es el fin de rango COMPARTIDO del día (ADR-186), no algo propio del spot de
ese renglón. "Capturar reales" (pantalla y PDF) sigue sin agruparse, a propósito.

**ADR-197 (petición del usuario) — "Material a Transmitir" permite elegir varios audios
de un jalón:** el `<input type="file">` no tenía `multiple` — el selector de Windows solo
dejaba marcar uno por apertura. Se agrega `multiple` en los 2 lugares donde existe esta
captura (`MaterialATransmitir.tsx` en edición, la sección de alta en
`OrdenEstacionForm.tsx`); el handler sube cada archivo EN SECUENCIA (no en paralelo) para
no alterar el orden que define la posición de cada spot (ADR-187); un archivo inválido o
que falla no detiene a los demás, los errores se acumulan en un solo mensaje. Sin cambios
de backend (el endpoint de subida ya aceptaba llamadas repetidas).

**ADR-198 (petición del usuario) — el bloque "Anunciante" usa el mismo título en
negritas que la tarjeta, en un renglón, sin el tag "Heredado":** el título pasa de `.fl`
(etiqueta chica gris) a `.form-card-title` (mismo estilo que "Orden de Servicio de
origen" a su izquierda), en línea junto a su valor en vez de apilado; se quita el
`FieldTag` "Heredado de la Orden de Servicio". Cambio 100% visual.

**ADR-198b (petición del usuario) — "Anunciante" sube al mismo renglón que el título de
la tarjeta, sin ":":** se posiciona con `position: absolute` en la esquina superior
derecha de la tarjeta (`position: relative`) en vez de reordenar el DOM — el título debe
seguir siendo el hermano inmediato del campo folio/selector, de lo que depende
`fieldByLabelText` (helper de pruebas en `domHelpers.ts`).

**ADR-198c (petición del usuario, corrige ADR-198b) — alineación del bloque
"Anunciante":** quedaba más arriba que el título real y con el valor en la misma línea.
Fix: `top`/`right: 18px` (el padding de `.form-card`, no `0`, que `position: absolute`
ignora) y estructura en columna (título arriba con su `marginBottom` normal, valor
debajo) — en espejo con el folio de la columna izquierda.

**ADR-198d (petición del usuario) — el selector de OC en alta suelta ya no se estira a
todo el ancho:** al mover el Anunciante a `position: absolute` (ADR-198b), el
`SearchableSelect` de la OC se quedó sin el `flexGrow: 1`/hermano de flex que antes lo
acotaba — su `.fi` es `width: 100%` de su contenedor, así que ocupaba TODA la tarjeta.
Fix: `maxWidth: 420` en ese contenedor (no afecta el folio ya elegido, `.fv.mono`,
siempre corto).

**ADR-199 (petición del usuario) — cambiar de Estación en el alta limpia
Producto/Duración/Tarifa:** `onEstacionChange` limpia esos 3 campos (mismo patrón que ya
usan Producto/Duración desde ADR-170), pero SOLO si ya había una estación elegida antes
— la primera selección no limpia nada, porque ahí es cuando ADR-173 precarga
Producto/Duración desde la OC de origen. El select de Estación ya va deshabilitado al
editar, así que esto solo aplica en alta.

**ADR-200 (petición del usuario) — "Dirección de facturación" (Orden de Servicio) pasa
a ser SIEMPRE de solo lectura:** antes se podía editar a mano aunque viniera
autocompletada del Anunciante/Agencia (ADR-181). Pasa de `disabled={congelado}` a
`readOnly` incondicional (nunca editable, independientemente de si la orden está
congelada) — `readOnly`, no `disabled`, para que los `setValue` programáticos de
ADR-181 sigan funcionando y el valor se siga mandando con React Hook Form. Se pierde la
captura manual cuando el catálogo no tiene domicilio (decisión explícita del usuario):
ese caso se corrige en el catálogo de Anunciante/Agencia, no aquí.

**ADR-208 (petición del usuario) — el detalle de "Órdenes de Servicio" agrega una
sección "Factura" (Ver/Descargar) una vez facturada:** nuevo hook
`useFacturaDeOrden(ordenId)` en `facturacion/hooks.ts` (reusa el filtro `orden_id` ya
existente de `GET /facturacion/clientes`); `OrdenClienteDetailPanel.tsx` lo importa
DIRECTO de Facturación (F1 depende de F2 aquí a propósito, mismo sentido que ya depende
el backend) y solo lo activa cuando `rootState(estatus_orden) >= 4` ("Facturada"/
"Cobrada"). Nueva sección "Factura" (separada de "Documentos", que es de cierre):
"Ver factura"/"Descargar PDF" si hay `pdf_path`, "Descargar XML" si hay `xml_path` —
mismo patrón que `FacturasClientePage.tsx` (ADR-206). Una factura cancelada de un
intento previo (ADR-047) se ignora, se usa la vigente.

**ADR-209 (petición del usuario) — "Cerrar orden" quita la casilla de confirmación:**
"Confirmo que la información de cierre es correcta." se quita de `CierreOCForm.tsx` —
cargar los documentos (o aceptar cerrarla sin ellos, la advertencia ámbar ya existente
sigue avisando) y darle a "Cerrar orden → Estado 3" ya es suficiente, sin el paso extra
de confirmación que antes bloqueaba el botón.

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
construcción nunca genera `Incidencia` (verificado == programado). **Superado por
ADR-174b:** ahora nace con `spots_programados = 0` y SIEMPRE genera su `Incidencia` de
bonificación. Solo se crea de
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
casos: el horario viejo queda como faltante, el nuevo como "Nuevo") — **revertido por
ADR-174b**, ver abajo; (3) registros
adicionales → ya se marcaban "Nuevo" (sin cambios); (4) **registros faltantes**
(un día ya programado que el CSV no menciona) — antes desaparecía de la tabla
(ADR-151); ahora `_parsear_layout_reales_csv()` lo agrega a `aplicados` con `spots=0`
(como si el usuario lo hubiera editado a mano a 0), así que sigue viéndose en la
tabla con su descuento y genera su `Incidencia` normal al avanzar. Un día ya
**cancelado** (ADR-104) se excluye de este chequeo (ya tiene su propia
`Verificacion`).

**ADR-174b (petición del usuario, revierte el punto 2 de ADR-157):** probando más a
fondo, el usuario pidió exactamente lo que ADR-157 había descartado — el
emparejamiento contra lo programado pasa a ser por FECHA (no fecha+hora exacta),
cronológico cuando una fecha tiene varios horarios (el modelo ya lo permite, ADR-127).
Un horario distinto para la misma fecha ya no se resuelve como "falta + nuevo": se
marca `cambio_horario` sobre el MISMO registro, que genera su propia `Incidencia`
`cambio_horario` al avanzar (ADEMÁS de la de spots, si también difieren — nunca una
reemplaza a la otra). Ver ADR-174b completo en `docs/arquitectura.md` para el detalle
de emparejamiento y la Incidencia automática de los registros nuevos.

**ADR-160 (petición del usuario; renumerado de ADR-158 al fusionar con
`fix/catalogos-correcciones-f0`, que ya usaba ADR-158/159):** el panel "Al avanzar a
2.3 se generarán" (bonif./desc./impacto neto) solo sumaba `oe.periodo_transmision` — un
día NUEVO del layout (ADR-149) nunca entraba a esa cuenta, aunque sus spots sean reales
adicionales a lo ya vendido ("se agregaron 2 nuevos spots y no los registró como
bonificaciones"). Un día nuevo siempre cuenta como bonificación completa en el panel
(en ese momento nunca generaba `Incidencia` en el backend, era puro ajuste de
presentación en el frontend — **desde ADR-174b sí la genera**, así que esta cuenta del
panel ahora coincide con una Incidencia real, no solo con la vista previa). **ADR-176
(petición del usuario, probando en vivo):** el panel dejó de sumar días nuevos al
mismo contador que la bonificación de días existentes — ahora cada uno tiene su propia
línea ("N spot(s) de bonificación" vs "N spot(s) en registros nuevos"), y ambos cuentan
SPOTS, no días afectados (antes "bonificación" sumaba +1 por día, sin importar cuántos
spots de diferencia tuviera ese día).

**ADR-161 (petición del usuario; renumerado de ADR-159, mismo motivo):** "no se está
registrando el log... hice un cambio en
la tarifa y me pidió el motivo lo coloqué y al guardar no se registró en el detalle
ningún log" — el backend (`_auditar_precio_spot_si_difiere`, ADR-102) ya auditaba bien
en `LogCambioParametro` y el endpoint `GET .../historial-tarifa` ya existía; el panel de
detalle de Orden de Transmisión simplemente nunca lo llamaba ni mostraba. Se agrega la
sección "Historial de cambios de tarifa" en `OrdenEstacionDetailPanel.tsx`, mismo patrón
visual que el historial de Tarifas.

**ADR-162 (petición del usuario, a raíz del historial de ADR-161):** "cada vez que
editas te está pidiendo poner el motivo aunque ya lo hayas hecho previamente, por eso ya
hay varios logs" — `_auditar_precio_spot_si_difiere` (ADR-102) solo comparaba contra la
tarifa del catálogo, nunca contra el `precio_spot` ya guardado; cualquier guardado
posterior de una OE con precio intencionalmente apartado del catálogo volvía a exigir
motivo y a duplicar el log. Ahora recibe también `precio_spot_anterior` (el valor antes
de sobrescribirlo, `None` solo en `create`) y no audita si el precio no cambió desde el
último guardado — un cambio real del precio sigue exigiendo motivo y auditando como
antes. Mismo criterio en el frontend (`OrdenEstacionForm.tsx`): el campo "Motivo del
cambio de tarifa" solo se exige si, además de diferir del catálogo, el precio se editó
en esta sesión respecto a `oe.precio_spot`.

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
**híbrido** (ADR-031): la generación automática (al capturar una `Verificacion`) infiere
`faltante`/`excedente` por diferencia de spots, y desde **ADR-174b** también
`cambio_horario` (cuando "Carga de Órdenes Reales Desde Layout" reporta una hora
distinta a la programada para la misma fecha — ver más abajo); `cambio_fecha` y
`spot_no_emitido` quedan para alta manual (Tanda 5). `resolucion` (spec) se agrega
completo, default `pendiente`.

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
(antes solo capturable en ese paso) se agregó a `OrdenEstacionCreate`/`Update` en el
backend, que lo sigue aceptando sin cambios. El botón "→ Capturar programados (2.2)" y su
pantalla (`ProgramadosForm.tsx`) se retiraron de la UI — el endpoint `POST .../programados`
se conserva intacto en el backend (con sus pruebas) por si se necesita un ajuste puntual
de `spots_programados` distinto al asignado.

**ADR-143 (petición del usuario, "ya no se ocupará"):** la sección "Reporte del afiliado"
del alta/edición (`OrdenEstacionForm.tsx`) se quitó de la pantalla — el frontend ya no la
muestra ni la manda al guardar (`toApi.ts` dejó de incluir `reporte_programados_ref` en
`create()`/`update()`, para no mandar `null` en cada "Guardar" y borrar en silencio un
reporte ya adjuntado de antes). El backend NO cambió: columna, schema y endpoint siguen
intactos, por si algún día se vuelve a necesitar o se quiere mostrar de solo lectura. Ojo:
existía una sección DISTINTA con el mismo nombre "Reporte del afiliado" en "Capturar
reales" (`RealesForm.tsx`, campo `reporte_reales_ref`) — en ese momento no se tocó, pero
ADR-146 (2026-09-30) sí la retiró de esa pantalla, con el mismo criterio de no tocar el
backend — ver esa entrada.

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
- **ADR-180 (petición del usuario) — motivo obligatorio al cambiar fecha de campaña:**
  si `fecha_inicio_campania`/`fecha_fin_campania` de verdad cambian respecto al valor
  guardado (no basta con reenviarlas, el front siempre lo hace), el `PUT` exige
  `motivo_cambio_fecha` (transitorio, un solo motivo cubre ambas) y audita cada campo
  que cambió en `LogCambioParametro` (`entidad="OrdenCliente"`) — mismo criterio que
  `TarifaPlazaUpdate.motivo_cambio` (ADR-099), pero auditado con `log_cambio_parametro`
  DIRECTO (sin pasar por `field_permissions.verificar`, que bloquearía a Ventas, única
  área que edita OC). El frontend (`OrdenClienteForm.tsx`) lo captura con un select
  poblado desde Constantes del Sistema (grupo `MotivoCambio`, clave `CambioFecha*` —
  ADR-178), deshabilitado hasta que alguna de las dos fechas cambie; cae a texto libre si
  el catálogo no tiene opciones. `GET .../historial-comisiones` (que filtra por
  `entidad_id`, no por campo) ahora también devuelve estas entradas — el panel de
  detalle renombra su sección a "Historial de cambios" (ya no "... de comisión").
- **ADR-181 (petición del usuario) — "Facturación a la Agencia" (antes "Afiliado factura
  directo al cliente"):** solo cambia la etiqueta/descripción visible del radio
  (ADR-141) — la columna `afiliado_factura_directo_al_cliente` NO se renombra. Al
  elegirlo, "Dirección de facturación" se autocompleta con el domicilio estructurado de
  la Agencia (ADR-175, vía `formatDomicilio`) si lo tiene capturado; **si NO lo tiene (o
  no hay Agencia ligada), VACÍA el campo** a propósito, para que el usuario la capture a
  mano (corrección explícita del usuario — la primera versión dejaba el campo intacto en
  ese caso). Al volver a "Facturación directa al cliente", siempre regresa a la
  identidad del Anunciante (`nombre_fiscal · RFC`), igual que desde el principio.
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

- (Resuelto ADR-169) `OrdenEstacionForm.tsx` ya conecta `producto_tarifa`/`duracion_spot`
  al catálogo Producto Duración, igual que Tarifa (ADR-166) y "Orden de Servicio"
  (ADR-167/168) — las 3 pantallas que usan producto/duración ya están conectadas.
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
