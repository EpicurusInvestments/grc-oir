# Informe de migración a AWS RDS — F1 (Órdenes)

> Migración auditada: `73fa97f9e718` (`f1 ordenes orden_cliente orden_estacion
> verificacion incidencia`), `down_revision = 'b6d9f2a4c817'` (F0-05, último head de F0).
> **Esta migración NUNCA se ejecutó contra RDS** — se generó, auditó y corrigió en 7
> pasadas, siempre contra SQLite local (ADR-028) o en modo offline (sin conexión). Nadie
> distinto del desarrollador humano ha aplicado nada contra RDS a partir de este
> trabajo.

## Resumen ejecutivo

- **6 tablas nuevas:** `orden_cliente`, `orden_cliente_vobo_item`, `orden_estacion`,
  `orden_estacion_dia`, `verificacion`, `incidencia`.
- **118 columnas** en total, contadas directamente del DDL (44 + 8 + 32 + 10 + 11 + 13
  — ver detalle por tabla; `verificacion` ganó `updated_at` en la Tanda 4b).
- **16 índices `ix_*`** (contados directamente del DDL: 20 en la Tanda 2, −1 en la
  Tanda 4 por `ix_orden_cliente_vobo_item_orden_id` redundante, −1 en la Tanda 4b por
  `ix_verificacion_orden_estacion_dia_id` redundante con su nuevo `UNIQUE`, −2 en la
  Tanda 4c por `ix_orden_estacion_dia_orden_estacion_id` (redundante con el `UNIQUE`
  compuesto) y `ix_orden_estacion_dia_fecha_transmision` (sin filtro real que lo
  respalde)), 2 de ellos únicos sobre folio (`orden_cliente.folio_orden`,
  `orden_estacion.folio_orden_estacion`).
- **25 llaves foráneas**, todas con `ondelete='NO ACTION'` explícito.
- **39 `CHECK` constraints** (18 originales + 9 en la Tanda 4 + 1 en la Tanda 4b:
  `spots_asignados <= spots_solicitados` + 8 en la Tanda 4c: no-negatividad de los 8
  montos de `orden_estacion` + 3 en la Tanda 4d: invariantes de suma exacta, envueltas
  en `ROUND(x, 2)` — ver ADR-039), todas con nombre explícito. Además,
  `ck_orden_estacion_dia_spots_solicitados` pasó de `>= 0` a `> 0` en la Tanda 4d.
- **3 `UNIQUE` constraints** declaradas como constraint de tabla (no vía
  `CREATE UNIQUE INDEX`): `uq_orden_cliente_vobo_item_orden_clave`
  (`orden_id`+`item_clave`), `uq_orden_estacion_dia_oe_fecha_hora`
  (`orden_estacion_id`+`fecha_transmision`+`hora_inicio`, Tanda 4b), y
  `uq_verificacion_orden_estacion_dia` (`orden_estacion_dia_id`, Tanda 4b).
- **Ninguna tabla de F0 se toca** — confirmado más abajo.
- Auditoría en 7 pasadas: (1) verificación previa + primera pasada de compatibilidad
  contra el modelo Python; (2) correcciones (nombres de FK, `ondelete`, índices,
  columnas de auditoría faltantes) + prueba de ciclo completo en SQLite; (3) SQL
  offline real contra el dialecto `mssql+pyodbc` + lectura línea por línea; (4)
  revisión externa del informe → tipos explícitos de fecha/hora/texto largo, CHECK de
  montos/cantidades, índice redundante eliminado, invariante de `Incidencia`
  documentada; (5) segunda revisión externa → 3 `UNIQUE`/`CHECK` adicionales
  aplicados, `Verificacion.reconciliada` identificado como campo muerto
  (`updated_at` agregado, pregunta de negocio documentada), ciclo completo repetido;
  (6) tercera revisión externa (Tanda 4c) → 8 `CHECK` de no-negatividad en
  `orden_estacion` (omisión de la Tanda 4), 2 índices redundantes/sin uso más
  eliminados en `orden_estacion_dia`, comentarios auto-generados obsoletos corregidos,
  lectura completa final del archivo sin hallazgos nuevos, ciclo completo repetido;
  (7) cuarta revisión externa (Tanda 4d) → segundo incidente de contraseña expuesta
  corregido de raíz (guard de `seed_dev.py` endurecido y probado), `spots_solicitados`
  cambiado a `> 0`, 3 CHECK de suma exacta agregados en `orden_estacion` y ajustados
  con `ROUND(x, 2)` tras descubrir en la re-siembra que SQLite no tiene tipo decimal de
  punto fijo (ADR-039), ciclo completo repetido.

## 1. Verificación previa

- **¿El esquema de SQLite se creó con la migración de Alembic o con
  `metadata.create_all()`?** Con la migración — confirmado leyendo directamente
  `dev_ordenes.db`: existe la tabla `alembic_version` con `version_num = '73fa97f9e718'`
  (el head). No hay rastro de `create_all()`.
- **Cadena de revisiones** (las 8 migraciones del proyecto, leídas sin conectarse a
  nada):

  ```
  7300e6f940a3 (F0-01, down_revision=None)
    → b73f13de1b80 (F0-02)
    → c4e7a1b93f20 (F0-03a)
    → d5b8c2a71f36 (F0-03b)
    → e7f2a9c14b58 (F0-03c)
    → f1a4d0c25e63 (F0-04)
    → b6d9f2a4c817 (F0-05)
    → 73fa97f9e718 (F1)  ← head
  ```

  Lineal, sin bifurcaciones, sin `down_revision` duplicados. `down_revision` de F1 =
  `b6d9f2a4c817`, que sí es el head real de F0.
- **Lo que este informe NO puede confirmar por sí mismo:** en qué revisión está RDS
  físicamente. Eso requiere `alembic current`/`alembic heads` corridos por el
  desarrollador humano contra RDS — la Tanda 2 entregó `scripts/verificar_config_bd.py`
  precisamente para eliminar la ambigüedad de a qué base apuntan esos comandos antes de
  correrlos (ver sección 10).

## 2. Auditoría de compatibilidad — los 16 puntos, contra el T-SQL REAL (ya corregido)

Confirmado contra el DDL generado en modo offline (sección 7), no solo contra el
modelo de Python — varios de estos puntos solo son visibles ahí.

| # | Punto | Veredicto |
|---|---|---|
| 1 | `ON DELETE RESTRICT` | ✅ No aparece. Las 25 FK muestran `ON DELETE NO ACTION` explícito en el T-SQL real. |
| 2 | Rutas de cascada múltiples | ✅ N/A — cero `CASCADE`/`SET NULL` en el esquema completo. |
| 3 | FK con nombre explícito, sin choque con F0 | ✅ Las 25 tienen `CONSTRAINT fk_<tabla>_<columna>` explícito; verificado sin colisión contra los nombres de F0. |
| 4 | `Unicode()` sin longitud | ✅ Todas con longitud explícita (`NVARCHAR(N)`); los campos de texto largo usan `NVARCHAR(max)` explícito (ver hallazgo A, ya corregido). |
| 5 | `NVARCHAR(MAX)`/texto largo en índice o unique | ✅ Ningún campo de texto largo participa en un índice o constraint único. |
| 6 | `DATETIME2` consistente | ✅ Las 11 columnas `created_at`/`updated_at`/`fecha_completado` compilan a `DATETIME2` sin excepción. |
| 7 | `Uuid()` → `UNIQUEIDENTIFIER`, default Python no `NEWID()` | ✅ Las 6 PK y las 25 FK son `UNIQUEIDENTIFIER`; cero `DEFAULT` de servidor en todo el DDL — todos los UUID se generan en Python (`uuid4`). |
| 8 | `Numeric(p,s)` explícito | ✅ `NUMERIC(12,2)`/`NUMERIC(14,2)`/`NUMERIC(5,2)` exactos, sin excepciones. |
| 9 | `Boolean` → `BIT`, sin `server_default TRUE/FALSE` | ✅ Los 8 booleanos son `BIT NOT NULL` sin `DEFAULT` de servidor — se envían desde Python en cada INSERT. |
| 10 | `CHECK` con nombre + SQL válido en T-SQL | ✅ Las 39 `CHECK` tienen nombre y compilan a sintaxis T-SQL válida (incluidas las 3 con `ROUND(x, 2)` de la Tanda 4d — `ROUND` es una función T-SQL estándar). |
| 11 | Nombres únicos sin choque con F0 | ✅ Verificado contra las 8 migraciones — sin colisiones. |
| 12 | Índices en FK y campos de filtro real | ✅ 4 índices agregados en la Tanda 2 (justificados contra `_apply_filters` real); 1 índice redundante quitado en la Tanda 4 (`orden_cliente_vobo_item`), 1 más en la Tanda 4b (`verificacion`), 2 más en la Tanda 4c (`orden_estacion_dia`) — total 16 `ix_*` (ver sección 5). |
| 13 | `op.batch_alter_table` | ✅ N/A — no se usa en esta migración. |
| 14 | `server_default` con funciones (`CURRENT_TIMESTAMP`/`SYSUTCDATETIME()`) | ✅ N/A — cero `server_default` en todo el DDL. |
| 15 | Palabras reservadas de T-SQL | ✅ Cerrado. La columna `total` compila **sin corchetes** — no es reservada del *core* T-SQL. **No se renombra.** |
| 16 | `downgrade()` completo y funcional | ✅ Probado CINCO veces (Tanda 2, Tanda 4, Tanda 4b, Tanda 4c y Tanda 4d, tras cada tanda de correcciones): ciclo completo `upgrade → downgrade → upgrade` en SQLite, con re-siembra y pytest en verde después de las cinco — ver sección 9. |

### Hallazgos — historial completo (A y B corregidos en la Tanda 4; 3 nuevos agregados)

**A) `UnicodeText()` compilaba a `NTEXT`, no a `NVARCHAR(MAX)`. → CORREGIDO.**
Afectaba 7 columnas de F1 (`orden_cliente.direccion_facturacion`/
`observaciones_predefinidas`/`observaciones_libres`,
`orden_estacion.observaciones_estacion`/`notas_transmision`,
`verificacion.notas_verificacion`, `incidencia.descripcion_incidencia`). Corregido con
un helper explícito `texto_largo()` en `core/db.py`
(`UnicodeText().with_variant(mssql.NVARCHAR(None), 'mssql')`, mismo patrón que
`datetime2()`). Verificado en el SQL regenerado: **0 `NTEXT`, 7 `NVARCHAR(max)`**.
Detalle completo y por qué F0 (`Categoria`, `EmpresaFacturadora`) se queda sin corregir
por ahora: **ADR-036** (`docs/arquitectura.md`).

**B) Las columnas `Date`/`Time` planas compilaban a `DATETIME` en modo offline. →
CORREGIDO.** Afectaba 9 columnas. La causa era la falta de detección de versión del
servidor en modo `--sql` sin conexión — el diagnóstico original (limitación del modo
offline, no un defecto) era correcto, pero dejaba el SQL offline como un preview NO
fiel para cualquier revisor futuro, y el tipo real quedaba dependiendo de que SIEMPRE
hubiera una conexión viva al generar SQL — el mismo tipo de comportamiento implícito
que ya costó el bug de ADR-014 (`.is_(True)` sobre `BIT`). Corregido con helpers
explícitos `fecha_sql()`/`hora_sql()` en `core/db.py`
(`.with_variant(mssql.DATE()/TIME(), 'mssql')`). Verificado en el SQL regenerado: **0
`DATETIME` espurio, 7 `DATE`, 2 `TIME` nativos** — ahora el SQL offline SÍ es un
preview fiel, sin importar si quien lo genera tiene una conexión abierta. Detalle
completo: **ADR-036**.

**C) Índice redundante `ix_orden_cliente_vobo_item_orden_id`. → CORREGIDO.** El
`UNIQUE(orden_id, item_clave)` ya sirve como índice para consultas por `orden_id` solo
(columna líder de un índice compuesto). El índice suelto no aportaba nada y sí costaba
en cada escritura. Quitado del modelo y de la migración.

**D) `Incidencia` tiene dos caminos de FK al mismo padre (`verificacion_id` y
`orden_estacion_id` denormalizado), sin garantía a nivel de esquema de que ambos
resuelvan a la misma `OrdenEstacion`. → NO se cambia el modelo, se documenta la
garantía real.** El único punto de creación de `Incidencia`
(`OrdenEstacionService.avanzar_reales`) construye ambos valores a partir del mismo
`orden_estacion_id` que procesa la llamada — verificado leyendo el código, no por
suposición. La garantía hoy es real pero vive en el servicio, no en el esquema (SQL
Server no puede expresar una validación cruzada entre tablas sin un trigger). Detalle
completo, incluida la invariante que debe revalidar cualquier alta manual futura de
`Incidencia` o carga de datos: **ADR-037**.

**E) `CHECK (hora_fin > hora_inicio)` rechaza ventanas de transmisión que cruzan
medianoche (23:00–01:00). → Investigado, CHECK sin tocar, pregunta llevada al área
usuaria.** Esta restricción **no la inventó el backend**: el prototipo de frontend ya
aprobado (`PeriodoTransmisionGrid.tsx`, anterior a todo el trabajo de F1 backend) tiene
la validación idéntica ("La hora de inicio debe ser antes que la de término"), sin
manejo de cruce de medianoche. Además, cada fila de `OrdenEstacionDia` está anclada a
UNA `fecha_transmision` (un solo día calendario) — una ventana 23:00–01:00
genuinamente pertenece a dos fechas distintas, así que modelarla en una sola fila con
`hora_inicio > hora_fin` sería ambiguo por diseño (¿de qué día son los spots?), más
allá del `CHECK`. Si GRC programa pautas de madrugada, la solución correcta es
capturarlas como DOS filas (23:00–23:59 del día N, 00:00–01:00 del día N+1), no
relajar el `CHECK`. Queda como pregunta para el área usuaria, no como defecto.

## 3. Tablas — columnas, tipo exacto SQL Server, nulabilidad, default (ya corregido)

### `orden_cliente` (44 columnas)

| Columna | Tipo SQL Server | Nula | Origen del default |
|---|---|---|---|
| orden_id | UNIQUEIDENTIFIER | NO | Python (`uuid4`) |
| folio_orden | NVARCHAR(20) | NO | servicio (folio correlativo) |
| numero_orden_cliente | NVARCHAR(50) | NO | — |
| fecha_venta | DATE | NO | — |
| anio_venta | INTEGER | NO | servicio (calculado) |
| mes_venta | INTEGER | NO | servicio (calculado) |
| empresa_facturadora_id | UNIQUEIDENTIFIER | NO | FK |
| vendedor_principal_id | UNIQUEIDENTIFIER | NO | FK |
| vendedor_secundario_id | UNIQUEIDENTIFIER | SÍ | FK |
| anunciante_id | UNIQUEIDENTIFIER | NO | FK |
| agencia_id | UNIQUEIDENTIFIER | SÍ | FK |
| contrato_id | UNIQUEIDENTIFIER | SÍ | FK |
| marca_id | UNIQUEIDENTIFIER | SÍ | FK |
| categoria_id | UNIQUEIDENTIFIER | SÍ | FK |
| producto | NVARCHAR(200) | SÍ | — |
| direccion_facturacion | NVARCHAR(max) | SÍ | — |
| facturacion_directa_cliente | BIT | NO | Python (`False`) |
| afiliado_factura_directo_al_cliente | BIT | NO | Python (`False`) |
| fecha_inicio_campania | DATE | NO | — |
| fecha_fin_campania | DATE | NO | — |
| total_dias_campania | INTEGER | NO | servicio (calculado) |
| duracion_spot | NVARCHAR(10) | NO | — |
| precio_unitario | NUMERIC(12,2) | NO | — |
| total_spots | INTEGER | NO | — |
| subtotal | NUMERIC(14,2) | NO | servicio (calculado) |
| iva | NUMERIC(14,2) | NO | servicio (calculado) |
| total | NUMERIC(14,2) | NO | servicio (calculado) |
| observaciones_predefinidas | NVARCHAR(max) | SÍ | — |
| observaciones_libres | NVARCHAR(max) | SÍ | — |
| estatus_orden | NVARCHAR(20) | NO | Python (`recibida`) |
| estatus_pago_afiliado | NVARCHAR(20) | NO | Python (`pendiente`) |
| estatus_pago_agencia | NVARCHAR(20) | NO | Python (`pendiente`) |
| archivo_orden_original_path | NVARCHAR(500) | SÍ | — |
| created_by | UNIQUEIDENTIFIER | NO | FK |
| created_at | DATETIME2 | NO | Python (`datetime.now`) |
| updated_at | DATETIME2 | SÍ | Python (`onupdate`) |
| porcentaje_comision_vendedor_principal_snap | NUMERIC(5,2) | SÍ | — (PARÁMETRO SENSIBLE, auditado) |
| porcentaje_comision_vendedor_secundario_snap | NUMERIC(5,2) | SÍ | — (PARÁMETRO SENSIBLE, auditado) |
| porcentaje_comision_agencia_snap | NUMERIC(5,2) | SÍ | — (PARÁMETRO SENSIBLE, auditado) |
| odc_cerrada_ref | NVARCHAR(500) | SÍ | — |
| carta_conciliacion_ref | NVARCHAR(500) | SÍ | — |
| cierre_sin_odc_cerrada | BIT | NO | Python (`False`) |
| cierre_sin_carta_conciliacion | BIT | NO | Python (`False`) |
| fecha_cierre | DATE | SÍ | servicio (al cerrar) |

### `orden_cliente_vobo_item` (8 columnas)

| Columna | Tipo | Nula | Origen |
|---|---|---|---|
| orden_cliente_vobo_item_id | UNIQUEIDENTIFIER | NO | Python (`uuid4`) |
| orden_id | UNIQUEIDENTIFIER | NO | FK |
| item_clave | NVARCHAR(30) | NO | — (10 valores fijos, `CHECK`) |
| completado | BIT | NO | Python (`False`) |
| usuario_id | UNIQUEIDENTIFIER | SÍ | FK |
| fecha_completado | DATETIME2 | SÍ | — |
| created_at | DATETIME2 | NO | Python |
| updated_at | DATETIME2 | SÍ | Python (`onupdate`) |

### `orden_estacion` (32 columnas)

| Columna | Tipo | Nula | Origen |
|---|---|---|---|
| orden_estacion_id | UNIQUEIDENTIFIER | NO | Python (`uuid4`) |
| folio_orden_estacion | NVARCHAR(25) | NO | servicio (folio) |
| orden_id | UNIQUEIDENTIFIER | NO | FK |
| numero_orden_estacion | NVARCHAR(50) | SÍ | — |
| contrato_id | UNIQUEIDENTIFIER | SÍ | FK (heredado de OC) |
| anunciante_id | UNIQUEIDENTIFIER | NO | FK (heredado de OC) |
| vendedor_id | UNIQUEIDENTIFIER | NO | FK |
| agencia_id | UNIQUEIDENTIFIER | SÍ | FK (heredado de OC) |
| categoria_id | UNIQUEIDENTIFIER | SÍ | FK (heredado de OC) |
| producto | NVARCHAR(200) | SÍ | — |
| estacion_id | UNIQUEIDENTIFIER | NO | FK |
| plaza_id | UNIQUEIDENTIFIER | NO | FK (heredado de Estación) |
| duracion_spot | NVARCHAR(10) | NO | heredado de OC |
| precio_spot | NUMERIC(12,2) | NO | — |
| importe_estacion | NUMERIC(14,2) | NO | servicio (calculado) |
| porcentaje_participacion_oir | NUMERIC(5,2) | NO | servicio (calculado) |
| importe_oir | NUMERIC(14,2) | NO | servicio (calculado) |
| iva_oir | NUMERIC(14,2) | NO | servicio (calculado) |
| total_oir | NUMERIC(14,2) | NO | servicio (calculado) |
| importe_emisora | NUMERIC(14,2) | NO | servicio (calculado) |
| iva_emisora | NUMERIC(14,2) | NO | servicio (calculado) |
| total_emisora | NUMERIC(14,2) | NO | servicio (calculado) |
| estatus | NVARCHAR(20) | NO | Python (`borrador`) |
| observaciones_estacion | NVARCHAR(max) | SÍ | — |
| created_by | UNIQUEIDENTIFIER | NO | FK |
| created_at | DATETIME2 | NO | Python |
| updated_at | DATETIME2 | SÍ | Python (`onupdate`) |
| testigos_url | NVARCHAR(500) | SÍ | — |
| testigos_ubicacion_alterna | NVARCHAR(300) | SÍ | — |
| notas_transmision | NVARCHAR(max) | SÍ | — |
| reporte_programados_ref | NVARCHAR(500) | SÍ | — |
| reporte_reales_ref | NVARCHAR(500) | SÍ | — |

### `orden_estacion_dia` (10 columnas)

| Columna | Tipo | Nula | Origen |
|---|---|---|---|
| orden_estacion_dia_id | UNIQUEIDENTIFIER | NO | Python (`uuid4`) |
| orden_estacion_id | UNIQUEIDENTIFIER | NO | FK |
| fecha_transmision | DATE | NO | — |
| hora_inicio | TIME | NO | — |
| hora_fin | TIME | NO | — |
| spots_solicitados | INTEGER | NO | — |
| spots_asignados | INTEGER | NO | — (2.1) |
| spots_programados | INTEGER | SÍ | — (2.2, NULL = sin confirmar) |
| created_at | DATETIME2 | NO | Python |
| updated_at | DATETIME2 | SÍ | Python (`onupdate`) |

### `verificacion` (11 columnas)

| Columna | Tipo | Nula | Origen |
|---|---|---|---|
| verificacion_id | UNIQUEIDENTIFIER | NO | Python (`uuid4`) |
| orden_estacion_dia_id | UNIQUEIDENTIFIER | NO | FK, `UNIQUE` (Tanda 4b) |
| spots_verificados | INTEGER | NO | — (2.3) |
| fecha_verificacion | DATE | NO | — |
| archivo_nombre | NVARCHAR(255) | SÍ | — |
| archivo_path | NVARCHAR(500) | SÍ | — |
| notas_verificacion | NVARCHAR(max) | SÍ | — |
| reconciliada | BIT | NO | Python (`True`, fijo — campo muerto, ver ADR-038) |
| created_by | UNIQUEIDENTIFIER | NO | FK |
| created_at | DATETIME2 | NO | Python |
| updated_at | DATETIME2 | SÍ | Python (`onupdate`) — agregada en Tanda 4b, sin uso hoy |

`updated_at` nulable agregada en la Tanda 4b: el argumento de "registro inmutable" solo
se sostiene mientras `reconciliada` sea un campo muerto — ver ADR-038 y la pregunta de
negocio en sección 6.

### `incidencia` (13 columnas)

| Columna | Tipo | Nula | Origen |
|---|---|---|---|
| incidencia_id | UNIQUEIDENTIFIER | NO | Python (`uuid4`) |
| verificacion_id | UNIQUEIDENTIFIER | NO | FK |
| orden_estacion_id | UNIQUEIDENTIFIER | NO | FK (denormalizado — ver ADR-037) |
| tipo_incidencia | NVARCHAR(20) | NO | — |
| spots_ordenados | INTEGER | NO | servicio (derivado) |
| spots_ejecutados | INTEGER | NO | servicio (derivado) |
| diferencia_spots | INTEGER | NO | servicio (calculado, puede ser negativo) |
| descripcion_incidencia | NVARCHAR(max) | SÍ | — |
| fecha_incidencia | DATE | NO | — |
| resolucion | NVARCHAR(20) | NO | Python (`pendiente`) |
| monto_ajuste | NUMERIC(14,2) | SÍ | servicio (autocalculado, puede ser negativo) |
| created_at | DATETIME2 | NO | Python |
| updated_at | DATETIME2 | SÍ | Python (`onupdate`) |

## 4. Relaciones (las 25 FK)

Sin cambios respecto a la Tanda 2 — las 25 apuntan como indica la spec/el modelo,
todas `ON DELETE NO ACTION`:

| FK | Tabla → Tabla referenciada |
|---|---|
| fk_orden_cliente_agencia | orden_cliente → agencia |
| fk_orden_cliente_anunciante | orden_cliente → anunciante |
| fk_orden_cliente_categoria | orden_cliente → categoria |
| fk_orden_cliente_contrato | orden_cliente → contrato |
| fk_orden_cliente_created_by | orden_cliente → usuario |
| fk_orden_cliente_empresa_facturadora | orden_cliente → empresa_facturadora |
| fk_orden_cliente_marca | orden_cliente → marca |
| fk_orden_cliente_vendedor_principal | orden_cliente → vendedor |
| fk_orden_cliente_vendedor_secundario | orden_cliente → vendedor |
| fk_orden_cliente_vobo_item_orden | orden_cliente_vobo_item → orden_cliente |
| fk_orden_cliente_vobo_item_usuario | orden_cliente_vobo_item → usuario |
| fk_orden_estacion_agencia | orden_estacion → agencia |
| fk_orden_estacion_anunciante | orden_estacion → anunciante |
| fk_orden_estacion_categoria | orden_estacion → categoria |
| fk_orden_estacion_contrato | orden_estacion → contrato |
| fk_orden_estacion_created_by | orden_estacion → usuario |
| fk_orden_estacion_estacion | orden_estacion → estacion |
| fk_orden_estacion_orden_cliente | orden_estacion → orden_cliente |
| fk_orden_estacion_plaza | orden_estacion → plaza |
| fk_orden_estacion_vendedor | orden_estacion → vendedor |
| fk_orden_estacion_dia_orden_estacion | orden_estacion_dia → orden_estacion |
| fk_verificacion_created_by | verificacion → usuario |
| fk_verificacion_orden_estacion_dia | verificacion → orden_estacion_dia |
| fk_incidencia_orden_estacion | incidencia → orden_estacion |
| fk_incidencia_verificacion | incidencia → verificacion |

Sin rutas de cascada (todas `NO ACTION`): no aplica el problema de SQL Server de
grafos con `CASCADE`/`SET NULL` convergentes. Ver ADR-037 sobre la relación entre
`fk_incidencia_orden_estacion` y `fk_incidencia_verificacion` (dos caminos al mismo
padre, consistencia garantizada por el servicio, no por el esquema).

## 5. Constraints e índices (ya corregido)

**39 `CHECK`** (todas nombradas): las 18 originales (estados/duración/rango de
porcentajes/fechas de campaña) más 9 agregadas en la Tanda 4 —
`ck_orden_cliente_precio_unitario` (`>= 0`), `ck_orden_cliente_total_spots` (`> 0`),
`ck_orden_cliente_subtotal` (`>= 0`), `ck_orden_cliente_iva` (`>= 0`),
`ck_orden_cliente_total` (`>= 0`), `ck_orden_cliente_total_dias_campania` (`>= 1`),
`ck_orden_cliente_mes_venta` (`1..12`), `ck_incidencia_spots_ordenados` (`>= 0`),
`ck_incidencia_spots_ejecutados` (`>= 0`) — más 1 agregada en la Tanda 4b:
`ck_orden_estacion_dia_asignados_max` (`spots_asignados <= spots_solicitados`,
respaldada por el texto literal de la spec) — más 8 agregadas en la Tanda 4c, todas
`>= 0` sobre `orden_estacion` (la misma omisión que la Tanda 4 sí corrigió en
`orden_cliente`/`incidencia` pero no aquí): `ck_orden_estacion_precio_spot`,
`ck_orden_estacion_importe_estacion`, `ck_orden_estacion_importe_oir`,
`ck_orden_estacion_iva_oir`, `ck_orden_estacion_total_oir`,
`ck_orden_estacion_importe_emisora`, `ck_orden_estacion_iva_emisora`,
`ck_orden_estacion_total_emisora` — más 3 agregadas en la Tanda 4d, invariantes de
SUMA EXACTA entre montos ya calculados (no de rango): `ck_orden_estacion_margen_oir_emisora`
(`ROUND(importe_oir + importe_emisora, 2) = ROUND(importe_estacion, 2)`),
`ck_orden_estacion_total_oir_suma` (`ROUND(total_oir, 2) = ROUND(importe_oir +
iva_oir, 2)`), `ck_orden_estacion_total_emisora_suma` (`ROUND(total_emisora, 2) =
ROUND(importe_emisora + iva_emisora, 2)`) — el `ROUND(x, 2)` en ambos lados es
necesario porque SQLite almacena `NUMERIC` como `float64` (sin tipo decimal de punto
fijo): sin él, la re-siembra de la demo falló para 1 de 18 `OrdenEstacion` por 1 ULP
de ruido de `float64`, aunque la aritmética `Decimal` de Python fuera exacta. En SQL
Server `ROUND` es un no-op inofensivo (`NUMERIC(14,2)` ahí es de punto fijo real, sin
este problema). Ver ADR-039 para el análisis completo y la prueba de que `ROUND` no
enmascara una violación real. Deliberadamente libres:
`diferencia_spots`/`monto_ajuste` (pueden ser negativos por diseño), y `spots_verificados`/
`spots_programados` (sin tope — ver sección 6). Además,
`ck_orden_estacion_dia_spots_solicitados` cambió de `spots_solicitados >= 0` a `> 0`
en la Tanda 4d (ver sección 6).

**2 `UNIQUE` de una columna vía `CREATE UNIQUE INDEX`** (`folio_orden`,
`folio_orden_estacion`) **+ 3 `UNIQUE` compuestas declaradas como constraint de
tabla:** `uq_orden_cliente_vobo_item_orden_clave` (`orden_id`+`item_clave`),
`uq_orden_estacion_dia_oe_fecha_hora` (`orden_estacion_id`+`fecha_transmision`+
`hora_inicio`, Tanda 4b), `uq_verificacion_orden_estacion_dia`
(`orden_estacion_dia_id`, Tanda 4b).

**16 índices `ix_*` en total** (20 en la Tanda 2, −1 en la Tanda 4 por
`ix_orden_cliente_vobo_item_orden_id` redundante, −1 en la Tanda 4b por
`ix_verificacion_orden_estacion_dia_id` redundante con su nuevo `UNIQUE`, −2 en la
Tanda 4c sobre `orden_estacion_dia`) — cada uno justificado por un filtro REAL de
`OrdenClienteRepository`/`OrdenEstacionRepository._apply_filters` o por navegación
directa de FK necesaria para `JOIN`/lecturas por padre.

**Los 2 índices quitados en la Tanda 4c, aplicados:**
- `ix_orden_estacion_dia_orden_estacion_id` — redundante tras `uq_orden_estacion_dia_oe_fecha_hora`
  (mismo patrón que el índice ya quitado de `orden_cliente_vobo_item`: la columna
  líder del `UNIQUE` ya sirve para consultas por `orden_estacion_id` solo). Este era
  el "hallazgo menor, sin aplicar" que quedó pendiente de la Tanda 4b — ya se aplicó.
- `ix_orden_estacion_dia_fecha_transmision` — verificado en el código que ningún
  endpoint filtra por `fecha_transmision` sola: `OrdenEstacionRepository.listar_dias()`
  siempre filtra primero por `orden_estacion_id` (recibe la fecha, si acaso, como
  filtro secundario dentro de esa OE). Mismo criterio de "¿hay un filtro real?" ya
  usado en la Tanda 2 para no indexar `fecha_inicio_campania`/`fecha_fin_campania`.

## 6. Preguntas respondidas (revisión externa, Tandas 4, 4b, 4c y 4d)

**¿`Verificacion.reconciliada` se fija al crear el registro, o se actualiza después?**
Se fija al crear, verificado en el código: el único lugar donde se asigna es dentro
del `Verificacion(...)` que construye `OrdenEstacionService.avanzar_reales` —
`reconciliada=True`, literal, siempre. Ningún otro método la lee para modificarla
después. Nunca se crea con `False` en la práctica. **Consecuencia identificada en la
revisión de la Tanda 4b: el campo es hoy MUERTO** (siempre `True`, nada lo consulta) —
`updated_at` se agregó de todos modos, ver ADR-038 y la pregunta de negocio abierta al
final de esta sección.

**`Verificacion` es 1:N sobre `orden_estacion_dia` sin `UNIQUE` — ¿puede haber más de
una por día? → APLICADO.** En el esquema no lo impedía; en la práctica no ocurre
(`avanzar_reales` solo corre una vez por OE, guard de estado). Se agregó
`UNIQUE(orden_estacion_dia_id)` (`uq_verificacion_orden_estacion_dia`) para que el
esquema lo garantice también, no solo la máquina de estados del servicio. Verificado:
la re-siembra de la demo no viola esta constraint (ninguna OE de la demo tiene más de
una verificación por día).

**`orden_estacion_dia` sin `UNIQUE` — ¿un duplicado rompería el balance en silencio? →
APLICADO.** Confirmado que `create()` no valida fechas duplicadas en el request. Se
agregó `UNIQUE(orden_estacion_id, fecha_transmision, hora_inicio)`
(`uq_orden_estacion_dia_oe_fecha_hora`) — con `hora_inicio` porque el prototipo de
frontend permite legítimamente dos franjas horarias distintas el mismo día. Verificado:
la re-siembra de la demo no viola esta constraint.

**¿`spots_asignados` puede exceder `spots_solicitados`? → APLICADO.** La spec lo dice
literal: *"Puede ser menor o igual a los solicitados."* Se agregó
`CHECK (spots_asignados <= spots_solicitados)` (`ck_orden_estacion_dia_asignados_max`).
Verificado: la re-siembra de la demo no lo viola.

**¿Debería haber un `CHECK` equivalente para `spots_programados <= spots_asignados`? →
NO aplicado, sin respaldo.** A diferencia de `spots_asignados`/`spots_solicitados`, ni
la spec (que ni siquiera define `spots_programados` — es una extensión aditiva de
ADR-030, "puede ser igual al efectivo, no un delta") ni el prototipo de frontend
(`ProgramadosForm.tsx` permite el override libre, sin límite superior ni inferior)
respaldan una restricción así. Sobre-restringir aquí sería inventar una regla de
negocio que nadie pidió. Y **`spots_verificados` (2.3) NUNCA debe llevar tope** — el
tipo de incidencia `excedente` existe precisamente porque lo real puede superar lo
programado; un `CHECK` ahí rompería el flujo de incidencias automáticas.

**Re-siembra tras aplicar las 3 constraints nuevas:** verificada explícitamente,
CERO violaciones — ninguno de los 10 `OrdenCliente`/18 `OrdenEstacion` de la demo
repite día/hora en la misma OE, ninguna OE tiene más de una `Verificacion` por día, y
ningún día tiene `spots_asignados > spots_solicitados`.

**¿`spots_solicitados >= 0` debería ser `> 0`, en paralelo con `total_spots > 0` de
`orden_cliente`? → APLICADO (Tanda 4d).** `total_spots > 0` existe porque una OC con
cero spots totales no tendría razón de existir. El mismo argumento aplica a nivel de
día: el prototipo de frontend exige `spots_diarios > 0` por fila
(`PeriodoTransmisionGrid.tsx`: *"Los spots del día deben ser mayores a 0."*) — un
`OrdenEstacionDia` con `spots_solicitados = 0` no representa nada. Se cambió el CHECK a
`> 0` y, en el schema Pydantic (`OrdenEstacionDiaCreate`), `spots_solicitados` pasó de
`ge=0` a `gt=0`; además se agregó una validación a nivel de modelo para el caso en que
el cliente omite `spots_solicitados` (cae a `spots_asignados` por default) y
`spots_asignados` es 0 — sin esa validación, ese caso hubiera producido un 500 del
CHECK en vez de un 422 claro. Verificado: la re-siembra de la demo no lo viola.

**¿`importe_oir + importe_emisora == importe_estacion` debería ser un `CHECK` de BD o
un invariante de servicio + prueba automatizada? → APLICADO como CHECK de BD (Tanda
4d), y extendido a las otras dos sumas exactas.** Verificado en
`OrdenEstacionService.create()`: `importe_emisora` no se calcula con una fórmula
independiente que redondee por su cuenta — es `importe_estacion - importe_oir`, una
resta pura entre dos `Decimal` que YA se redondearon (`.quantize(CENTAVOS)`) antes de
la resta. Eso significa que el invariante se cumple EXACTO por construcción, no de
forma aproximada. El mismo razonamiento se extiende a `total_oir = importe_oir +
iva_oir` y `total_emisora = importe_emisora + iva_emisora` (ambas también sumas de
montos ya redondeados, no un segundo cálculo independiente) — se agregaron los 3 como
CHECK. **Hallazgo de la verificación:** al re-sembrar la demo en SQLite, 1 de 18
`OrdenEstacion` violó `ck_orden_estacion_total_emisora_suma` — no porque el dato fuera
incorrecto, sino porque SQLite almacena `NUMERIC` como `float64` (sin tipo decimal de
punto fijo) y `44478.00 + 7116.48` da un resultado en `float64` que no coincide bit a
bit con el `float64` del total guardado por separado, aunque en `Decimal` ambos son
exactamente `51594.48`. Se envolvieron los 3 CHECK en `ROUND(x, 2)` en ambos lados —
neutraliza el ruido de `float64` de SQLite sin enmascarar una violación real (probado
con una diferencia de 1 centavo completo, que sigue siendo rechazada), y es un no-op
inofensivo en SQL Server (`NUMERIC(14,2)` ahí es de punto fijo real). Ver ADR-039.
Verificado: la re-siembra de la demo ya no viola ninguno de los 3.

## 7. Qué NO se toca

**Confirmado: ninguna tabla de F0 se modifica ni se elimina.** La migración solo tiene
`create_table`/`create_index` sobre las 6 tablas nuevas de F1; cero `alter_table`/
`drop_table`/`drop_column` sobre `agencia`, `anunciante`, `categoria`, `contrato`,
`empresa_facturadora`, `estacion`, `marca`, `plaza`, `tarifa_plaza`, `usuario`,
`vendedor`, `constantes_sistema`, `cuenta_contable`, `log_cambio_parametro`.

**`TarifaPlaza` no requiere cambios** — confirmado: F1 adoptó los 4 valores de
`duracion_spot` de la spec (`20s`/`30s`/`60s`/`mencion`), los mismos que ya usa
`TarifaPlaza` desde F0-02. Sin divergencia de vocabulario, sin necesidad de migrar
datos existentes de tarifas.

## 8. SQL completo generado en modo offline (ya corregido)

Regenerado con `alembic upgrade b6d9f2a4c817:73fa97f9e718 --sql` (sin conexión — log
de Alembic confirmó `Context impl MSSQLImpl`, `Will assume transactional DDL`, nunca
`Connected`) tras aplicar las correcciones de la Tanda 4d. Verificado con `grep` que no
contiene ningún secreto, que ya no aparece `NTEXT`, que las columnas de fecha/hora son
`DATE`/`TIME` nativos incluso generadas sin conexión, y que los conteos cuadran contra
el archivo real: 39 `CHECK`, 25 FK, 3 `UNIQUE` compuestas, 16 índices `ix_*`, 6
`CREATE TABLE`.

```sql
BEGIN TRANSACTION;

-- Running upgrade b6d9f2a4c817 -> 73fa97f9e718

CREATE TABLE orden_cliente (
    orden_id UNIQUEIDENTIFIER NOT NULL, 
    folio_orden NVARCHAR(20) NOT NULL, 
    numero_orden_cliente NVARCHAR(50) NOT NULL, 
    fecha_venta DATE NOT NULL, 
    anio_venta INTEGER NOT NULL, 
    mes_venta INTEGER NOT NULL, 
    empresa_facturadora_id UNIQUEIDENTIFIER NOT NULL, 
    vendedor_principal_id UNIQUEIDENTIFIER NOT NULL, 
    vendedor_secundario_id UNIQUEIDENTIFIER NULL, 
    anunciante_id UNIQUEIDENTIFIER NOT NULL, 
    agencia_id UNIQUEIDENTIFIER NULL, 
    contrato_id UNIQUEIDENTIFIER NULL, 
    marca_id UNIQUEIDENTIFIER NULL, 
    categoria_id UNIQUEIDENTIFIER NULL, 
    producto NVARCHAR(200) NULL, 
    direccion_facturacion NVARCHAR(max) NULL, 
    facturacion_directa_cliente BIT NOT NULL, 
    afiliado_factura_directo_al_cliente BIT NOT NULL, 
    fecha_inicio_campania DATE NOT NULL, 
    fecha_fin_campania DATE NOT NULL, 
    total_dias_campania INTEGER NOT NULL, 
    duracion_spot NVARCHAR(10) NOT NULL, 
    precio_unitario NUMERIC(12, 2) NOT NULL, 
    total_spots INTEGER NOT NULL, 
    subtotal NUMERIC(14, 2) NOT NULL, 
    iva NUMERIC(14, 2) NOT NULL, 
    total NUMERIC(14, 2) NOT NULL, 
    observaciones_predefinidas NVARCHAR(max) NULL, 
    observaciones_libres NVARCHAR(max) NULL, 
    estatus_orden NVARCHAR(20) NOT NULL, 
    estatus_pago_afiliado NVARCHAR(20) NOT NULL, 
    estatus_pago_agencia NVARCHAR(20) NOT NULL, 
    archivo_orden_original_path NVARCHAR(500) NULL, 
    created_by UNIQUEIDENTIFIER NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NULL, 
    porcentaje_comision_vendedor_principal_snap NUMERIC(5, 2) NULL, 
    porcentaje_comision_vendedor_secundario_snap NUMERIC(5, 2) NULL, 
    porcentaje_comision_agencia_snap NUMERIC(5, 2) NULL, 
    odc_cerrada_ref NVARCHAR(500) NULL, 
    carta_conciliacion_ref NVARCHAR(500) NULL, 
    cierre_sin_odc_cerrada BIT NOT NULL, 
    cierre_sin_carta_conciliacion BIT NOT NULL, 
    fecha_cierre DATE NULL, 
    PRIMARY KEY (orden_id), 
    CONSTRAINT ck_orden_cliente_duracion_spot CHECK (duracion_spot IN ('20s', '30s', '60s', 'mencion')), 
    CONSTRAINT ck_orden_cliente_estatus_orden CHECK (estatus_orden IN ('recibida', 'capturada', 'en_transmision', 'en_verificacion', 'orden_cerrada', 'facturada', 'cobrada', 'cancelada')), 
    CONSTRAINT ck_orden_cliente_estatus_pago_afiliado CHECK (estatus_pago_afiliado IN ('pendiente', 'en_revision', 'pagado')), 
    CONSTRAINT ck_orden_cliente_estatus_pago_agencia CHECK (estatus_pago_agencia IN ('pendiente', 'en_revision', 'pagado')), 
    CONSTRAINT ck_orden_cliente_fechas_campania CHECK (fecha_fin_campania >= fecha_inicio_campania), 
    CONSTRAINT ck_orden_cliente_comision_ag_snap CHECK (porcentaje_comision_agencia_snap IS NULL OR (porcentaje_comision_agencia_snap >= 0 AND porcentaje_comision_agencia_snap <= 100)), 
    CONSTRAINT ck_orden_cliente_comision_vp_snap CHECK (porcentaje_comision_vendedor_principal_snap IS NULL OR (porcentaje_comision_vendedor_principal_snap >= 0 AND porcentaje_comision_vendedor_principal_snap <= 100)), 
    CONSTRAINT ck_orden_cliente_comision_vs_snap CHECK (porcentaje_comision_vendedor_secundario_snap IS NULL OR (porcentaje_comision_vendedor_secundario_snap >= 0 AND porcentaje_comision_vendedor_secundario_snap <= 100)), 
    CONSTRAINT ck_orden_cliente_precio_unitario CHECK (precio_unitario >= 0), 
    CONSTRAINT ck_orden_cliente_total_spots CHECK (total_spots > 0), 
    CONSTRAINT ck_orden_cliente_subtotal CHECK (subtotal >= 0), 
    CONSTRAINT ck_orden_cliente_iva CHECK (iva >= 0), 
    CONSTRAINT ck_orden_cliente_total CHECK (total >= 0), 
    CONSTRAINT ck_orden_cliente_total_dias_campania CHECK (total_dias_campania >= 1), 
    CONSTRAINT ck_orden_cliente_mes_venta CHECK (mes_venta >= 1 AND mes_venta <= 12), 
    CONSTRAINT fk_orden_cliente_agencia FOREIGN KEY(agencia_id) REFERENCES agencia (agencia_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_anunciante FOREIGN KEY(anunciante_id) REFERENCES anunciante (anunciante_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_categoria FOREIGN KEY(categoria_id) REFERENCES categoria (categoria_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_contrato FOREIGN KEY(contrato_id) REFERENCES contrato (contrato_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_created_by FOREIGN KEY(created_by) REFERENCES usuario (usuario_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_empresa_facturadora FOREIGN KEY(empresa_facturadora_id) REFERENCES empresa_facturadora (empresa_facturadora_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_marca FOREIGN KEY(marca_id) REFERENCES marca (marca_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_vendedor_principal FOREIGN KEY(vendedor_principal_id) REFERENCES vendedor (vendedor_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_vendedor_secundario FOREIGN KEY(vendedor_secundario_id) REFERENCES vendedor (vendedor_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_orden_cliente_agencia_id ON orden_cliente (agencia_id);

GO

CREATE INDEX ix_orden_cliente_anunciante_id ON orden_cliente (anunciante_id);

GO

CREATE INDEX ix_orden_cliente_contrato_id ON orden_cliente (contrato_id);

GO

CREATE INDEX ix_orden_cliente_empresa_facturadora_id ON orden_cliente (empresa_facturadora_id);

GO

CREATE INDEX ix_orden_cliente_estatus_orden ON orden_cliente (estatus_orden);

GO

CREATE UNIQUE INDEX ix_orden_cliente_folio_orden ON orden_cliente (folio_orden);

GO

CREATE INDEX ix_orden_cliente_vendedor_principal_id ON orden_cliente (vendedor_principal_id);

GO

CREATE TABLE orden_cliente_vobo_item (
    orden_cliente_vobo_item_id UNIQUEIDENTIFIER NOT NULL, 
    orden_id UNIQUEIDENTIFIER NOT NULL, 
    item_clave NVARCHAR(30) NOT NULL, 
    completado BIT NOT NULL, 
    usuario_id UNIQUEIDENTIFIER NULL, 
    fecha_completado DATETIME2 NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NULL, 
    PRIMARY KEY (orden_cliente_vobo_item_id), 
    CONSTRAINT ck_orden_cliente_vobo_item_clave CHECK (item_clave IN ('razon_social', 'plaza', 'emisora', 'duracion', 'tarifa', 'distribucion', 'horario', 'importes', 'audio', 'odc_firmada')), 
    CONSTRAINT fk_orden_cliente_vobo_item_orden FOREIGN KEY(orden_id) REFERENCES orden_cliente (orden_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_cliente_vobo_item_usuario FOREIGN KEY(usuario_id) REFERENCES usuario (usuario_id) ON DELETE NO ACTION, 
    CONSTRAINT uq_orden_cliente_vobo_item_orden_clave UNIQUE (orden_id, item_clave)
);

GO

CREATE TABLE orden_estacion (
    orden_estacion_id UNIQUEIDENTIFIER NOT NULL, 
    folio_orden_estacion NVARCHAR(25) NOT NULL, 
    orden_id UNIQUEIDENTIFIER NOT NULL, 
    numero_orden_estacion NVARCHAR(50) NULL, 
    contrato_id UNIQUEIDENTIFIER NULL, 
    anunciante_id UNIQUEIDENTIFIER NOT NULL, 
    vendedor_id UNIQUEIDENTIFIER NOT NULL, 
    agencia_id UNIQUEIDENTIFIER NULL, 
    categoria_id UNIQUEIDENTIFIER NULL, 
    producto NVARCHAR(200) NULL, 
    estacion_id UNIQUEIDENTIFIER NOT NULL, 
    plaza_id UNIQUEIDENTIFIER NOT NULL, 
    duracion_spot NVARCHAR(10) NOT NULL, 
    precio_spot NUMERIC(12, 2) NOT NULL, 
    importe_estacion NUMERIC(14, 2) NOT NULL, 
    porcentaje_participacion_oir NUMERIC(5, 2) NOT NULL, 
    importe_oir NUMERIC(14, 2) NOT NULL, 
    iva_oir NUMERIC(14, 2) NOT NULL, 
    total_oir NUMERIC(14, 2) NOT NULL, 
    importe_emisora NUMERIC(14, 2) NOT NULL, 
    iva_emisora NUMERIC(14, 2) NOT NULL, 
    total_emisora NUMERIC(14, 2) NOT NULL, 
    estatus NVARCHAR(20) NOT NULL, 
    observaciones_estacion NVARCHAR(max) NULL, 
    created_by UNIQUEIDENTIFIER NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NULL, 
    testigos_url NVARCHAR(500) NULL, 
    testigos_ubicacion_alterna NVARCHAR(300) NULL, 
    notas_transmision NVARCHAR(max) NULL, 
    reporte_programados_ref NVARCHAR(500) NULL, 
    reporte_reales_ref NVARCHAR(500) NULL, 
    PRIMARY KEY (orden_estacion_id), 
    CONSTRAINT ck_orden_estacion_duracion_spot CHECK (duracion_spot IN ('20s', '30s', '60s', 'mencion')), 
    CONSTRAINT ck_orden_estacion_estatus CHECK (estatus IN ('borrador', 'asignada', 'en_transmision', 'en_revision', 'cerrada', 'cancelada')), 
    CONSTRAINT ck_orden_estacion_pct_oir CHECK (porcentaje_participacion_oir >= 0 AND porcentaje_participacion_oir <= 100), 
    CONSTRAINT ck_orden_estacion_precio_spot CHECK (precio_spot >= 0), 
    CONSTRAINT ck_orden_estacion_importe_estacion CHECK (importe_estacion >= 0), 
    CONSTRAINT ck_orden_estacion_importe_oir CHECK (importe_oir >= 0), 
    CONSTRAINT ck_orden_estacion_iva_oir CHECK (iva_oir >= 0), 
    CONSTRAINT ck_orden_estacion_total_oir CHECK (total_oir >= 0), 
    CONSTRAINT ck_orden_estacion_importe_emisora CHECK (importe_emisora >= 0), 
    CONSTRAINT ck_orden_estacion_iva_emisora CHECK (iva_emisora >= 0), 
    CONSTRAINT ck_orden_estacion_total_emisora CHECK (total_emisora >= 0), 
    CONSTRAINT ck_orden_estacion_margen_oir_emisora CHECK (ROUND(importe_oir + importe_emisora, 2) = ROUND(importe_estacion, 2)), 
    CONSTRAINT ck_orden_estacion_total_oir_suma CHECK (ROUND(total_oir, 2) = ROUND(importe_oir + iva_oir, 2)), 
    CONSTRAINT ck_orden_estacion_total_emisora_suma CHECK (ROUND(total_emisora, 2) = ROUND(importe_emisora + iva_emisora, 2)), 
    CONSTRAINT fk_orden_estacion_agencia FOREIGN KEY(agencia_id) REFERENCES agencia (agencia_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_anunciante FOREIGN KEY(anunciante_id) REFERENCES anunciante (anunciante_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_categoria FOREIGN KEY(categoria_id) REFERENCES categoria (categoria_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_contrato FOREIGN KEY(contrato_id) REFERENCES contrato (contrato_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_created_by FOREIGN KEY(created_by) REFERENCES usuario (usuario_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_estacion FOREIGN KEY(estacion_id) REFERENCES estacion (estacion_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_orden_cliente FOREIGN KEY(orden_id) REFERENCES orden_cliente (orden_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_plaza FOREIGN KEY(plaza_id) REFERENCES plaza (plaza_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_orden_estacion_vendedor FOREIGN KEY(vendedor_id) REFERENCES vendedor (vendedor_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_orden_estacion_anunciante_id ON orden_estacion (anunciante_id);

GO

CREATE INDEX ix_orden_estacion_estacion_id ON orden_estacion (estacion_id);

GO

CREATE INDEX ix_orden_estacion_estatus ON orden_estacion (estatus);

GO

CREATE UNIQUE INDEX ix_orden_estacion_folio_orden_estacion ON orden_estacion (folio_orden_estacion);

GO

CREATE INDEX ix_orden_estacion_orden_id ON orden_estacion (orden_id);

GO

CREATE INDEX ix_orden_estacion_plaza_id ON orden_estacion (plaza_id);

GO

CREATE INDEX ix_orden_estacion_vendedor_id ON orden_estacion (vendedor_id);

GO

CREATE TABLE orden_estacion_dia (
    orden_estacion_dia_id UNIQUEIDENTIFIER NOT NULL, 
    orden_estacion_id UNIQUEIDENTIFIER NOT NULL, 
    fecha_transmision DATE NOT NULL, 
    hora_inicio TIME NOT NULL, 
    hora_fin TIME NOT NULL, 
    spots_solicitados INTEGER NOT NULL, 
    spots_asignados INTEGER NOT NULL, 
    spots_programados INTEGER NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NULL, 
    PRIMARY KEY (orden_estacion_dia_id), 
    CONSTRAINT ck_orden_estacion_dia_horas CHECK (hora_fin > hora_inicio), 
    CONSTRAINT ck_orden_estacion_dia_spots_asignados CHECK (spots_asignados >= 0), 
    CONSTRAINT ck_orden_estacion_dia_asignados_max CHECK (spots_asignados <= spots_solicitados), 
    CONSTRAINT ck_orden_estacion_dia_spots_programados CHECK (spots_programados IS NULL OR spots_programados >= 0), 
    CONSTRAINT ck_orden_estacion_dia_spots_solicitados CHECK (spots_solicitados > 0), 
    CONSTRAINT fk_orden_estacion_dia_orden_estacion FOREIGN KEY(orden_estacion_id) REFERENCES orden_estacion (orden_estacion_id) ON DELETE NO ACTION, 
    CONSTRAINT uq_orden_estacion_dia_oe_fecha_hora UNIQUE (orden_estacion_id, fecha_transmision, hora_inicio)
);

GO

CREATE TABLE verificacion (
    verificacion_id UNIQUEIDENTIFIER NOT NULL, 
    orden_estacion_dia_id UNIQUEIDENTIFIER NOT NULL, 
    spots_verificados INTEGER NOT NULL, 
    fecha_verificacion DATE NOT NULL, 
    archivo_nombre NVARCHAR(255) NULL, 
    archivo_path NVARCHAR(500) NULL, 
    notas_verificacion NVARCHAR(max) NULL, 
    reconciliada BIT NOT NULL, 
    created_by UNIQUEIDENTIFIER NOT NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NULL, 
    PRIMARY KEY (verificacion_id), 
    CONSTRAINT fk_verificacion_created_by FOREIGN KEY(created_by) REFERENCES usuario (usuario_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_verificacion_orden_estacion_dia FOREIGN KEY(orden_estacion_dia_id) REFERENCES orden_estacion_dia (orden_estacion_dia_id) ON DELETE NO ACTION, 
    CONSTRAINT uq_verificacion_orden_estacion_dia UNIQUE (orden_estacion_dia_id)
);

GO

CREATE TABLE incidencia (
    incidencia_id UNIQUEIDENTIFIER NOT NULL, 
    verificacion_id UNIQUEIDENTIFIER NOT NULL, 
    orden_estacion_id UNIQUEIDENTIFIER NOT NULL, 
    tipo_incidencia NVARCHAR(20) NOT NULL, 
    spots_ordenados INTEGER NOT NULL, 
    spots_ejecutados INTEGER NOT NULL, 
    diferencia_spots INTEGER NOT NULL, 
    descripcion_incidencia NVARCHAR(max) NULL, 
    fecha_incidencia DATE NOT NULL, 
    resolucion NVARCHAR(20) NOT NULL, 
    monto_ajuste NUMERIC(14, 2) NULL, 
    created_at DATETIME2 NOT NULL, 
    updated_at DATETIME2 NULL, 
    PRIMARY KEY (incidencia_id), 
    CONSTRAINT ck_incidencia_resolucion CHECK (resolucion IN ('pendiente', 'aceptada', 'credito_cliente', 'descuento_afiliado', 'sin_resolucion')), 
    CONSTRAINT ck_incidencia_tipo CHECK (tipo_incidencia IN ('faltante', 'excedente', 'cambio_horario', 'cambio_fecha', 'spot_no_emitido')), 
    CONSTRAINT ck_incidencia_spots_ordenados CHECK (spots_ordenados >= 0), 
    CONSTRAINT ck_incidencia_spots_ejecutados CHECK (spots_ejecutados >= 0), 
    CONSTRAINT fk_incidencia_orden_estacion FOREIGN KEY(orden_estacion_id) REFERENCES orden_estacion (orden_estacion_id) ON DELETE NO ACTION, 
    CONSTRAINT fk_incidencia_verificacion FOREIGN KEY(verificacion_id) REFERENCES verificacion (verificacion_id) ON DELETE NO ACTION
);

GO

CREATE INDEX ix_incidencia_orden_estacion_id ON incidencia (orden_estacion_id);

GO

CREATE INDEX ix_incidencia_verificacion_id ON incidencia (verificacion_id);

GO

UPDATE alembic_version SET version_num='73fa97f9e718' WHERE alembic_version.version_num = 'b6d9f2a4c817';

GO

COMMIT;

GO
```

## 9. Plan de reversa (`downgrade()`)

Probado CINCO veces (Tanda 2, Tanda 4, Tanda 4b, Tanda 4c y Tanda 4d, cada vez tras
nuevas correcciones): ciclo completo `upgrade → downgrade → upgrade` en SQLite, con
re-siembra y pytest después en las cinco ocasiones — la última re-siembra (Tanda 4d) se
verificó explícitamente sin violar ninguna de las 11 `CHECK` nuevas sobre
`orden_estacion` (las 8 de no-negatividad de la Tanda 4c más las 3 de suma exacta de la
Tanda 4d, estas últimas envueltas en `ROUND(x, 2)` — ver ADR-039) ni el nuevo
`spots_solicitados > 0`. El `downgrade()` elimina las 6 tablas en orden inverso exacto al
`upgrade()` (`incidencia` → `verificacion` → `orden_estacion_dia` → `orden_estacion` →
`orden_cliente_vobo_item` → `orden_cliente`), con sus índices, respetando el orden por
FK:

```python
def downgrade() -> None:
    # ### editado a mano para reflejar cada corrección de upgrade() — mantener en
    # espejo exacto (orden inverso) cada vez que upgrade() cambie ###
    op.drop_index(op.f('ix_incidencia_verificacion_id'), table_name='incidencia')
    op.drop_index(op.f('ix_incidencia_orden_estacion_id'), table_name='incidencia')
    op.drop_table('incidencia')
    op.drop_table('verificacion')
    op.drop_table('orden_estacion_dia')
    op.drop_index(op.f('ix_orden_estacion_vendedor_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_plaza_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_orden_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_folio_orden_estacion'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_estatus'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_estacion_id'), table_name='orden_estacion')
    op.drop_index(op.f('ix_orden_estacion_anunciante_id'), table_name='orden_estacion')
    op.drop_table('orden_estacion')
    op.drop_table('orden_cliente_vobo_item')
    op.drop_index(op.f('ix_orden_cliente_vendedor_principal_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_folio_orden'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_estatus_orden'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_empresa_facturadora_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_contrato_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_anunciante_id'), table_name='orden_cliente')
    op.drop_index(op.f('ix_orden_cliente_agencia_id'), table_name='orden_cliente')
    op.drop_table('orden_cliente')
    # ### end Alembic commands ###
```

**Qué NO se puede recuperar con el downgrade:** todos los datos de las 6 tablas — es
un `DROP TABLE`, no un archivado. Si esta migración llega a aplicarse en RDS con datos
reales cargados y hay que revertir, esos datos se pierden salvo que exista un backup
tomado antes del `upgrade`. Recomendación: **respaldo de RDS inmediatamente antes de
aplicar**, como con cualquier migración sobre una base compartida con datos.

## 10. Riesgos y advertencias

- **RDS es compartida por todo el equipo.** Un `upgrade` a medias bloquea a los demás
  — mitigado por transaccionalidad de SQL Server (confirmado: el log de Alembic dice
  "Will assume transactional DDL"; toda la migración corre en una sola
  `BEGIN TRANSACTION`/`COMMIT`, ver sección 8), así que un fallo a mitad de camino
  revierte solo, sin dejar estado intermedio.
- **Incidente ya cerrado (dos ocurrencias, mismo bug de fondo):** la contraseña real de
  `TESTGRCOIRDB` quedó expuesta en claro en la salida de una herramienta en dos
  momentos distintos de esta auditoría — primero durante la construcción de
  `scripts/verificar_config_bd.py` (Tanda 2), después durante el ciclo de prueba de la
  Tanda 4c al ejecutar `scripts/seed_dev.py` contra una `DATABASE_URL` sin definir (el
  script imprimía la URL cruda ANTES de validar que apuntara a SQLite). Ambas veces por
  la misma causa raíz: `URL.render_as_string(hide_password=True)` de SQLAlchemy no
  enmascara la contraseña cuando viene empaquetada dentro de un parámetro de query
  `odbc_connect=` (el formato que usa `Settings.sqlalchemy_url` en este proyecto).
  Confirmado que en ninguna de las dos veces llegó a ningún archivo del repositorio ni
  fuera de él — solo al historial de la sesión. La Tanda 4c corrigió la causa raíz de
  forma centralizada: `url_enmascarada()` en `app/core/db.py` (antes duplicada solo en
  `verificar_config_bd.py`), usada ahora por ambos scripts; además `seed_dev.py` se
  reordenó para validar `sqlite` en `DATABASE_URL` ANTES de imprimir nada. Reportado a
  TI por el equipo (fuera del alcance de este informe).
- **Hallazgo A (`NTEXT`) corregido en F1; F0 queda con el mismo patrón sin corregir**
  — ticket aparte, ver ADR-036. No bloquea esta migración.
- **Hallazgo B (`DATE`/`Time`) corregido con tipos explícitos** — el SQL offline ya es
  un preview fiel independientemente de si se aplica online o se genera sin conexión.
- **Hallazgo D (`Incidencia`, dos caminos de FK)** documentado en ADR-037 — invariante
  a revisar si se implementa alta manual de `Incidencia` o una carga de datos futura.
- **3 constraints de la sección 6 — APLICADAS y verificadas sin violación en la
  re-siembra:** `UNIQUE(orden_estacion_dia_id)` en `verificacion`,
  `UNIQUE(orden_estacion_id, fecha_transmision, hora_inicio)` en `orden_estacion_dia`,
  `CHECK(spots_asignados <= spots_solicitados)`.
- **`Verificacion.reconciliada` es un campo muerto (ADR-038)** — pregunta de negocio
  abierta, llevada al área usuaria junto con la de medianoche. `updated_at` agregada
  por el costo asimétrico, sin cambiar el flujo de `avanzar_reales`.
- **Hallazgo E (`hora_fin > hora_inicio`, cruce de medianoche)** llevado al área
  usuaria — el `CHECK` no se tocó.
- **8 `CHECK` de no-negatividad en `orden_estacion` — APLICADAS (Tanda 4c):** misma
  omisión que la Tanda 4 corrigió en `orden_cliente`/`incidencia` pero no aquí.
  Verificado sin violación en la re-siembra.
- **2 índices redundantes/sin uso en `orden_estacion_dia` — APLICADO (Tanda 4c):**
  `ix_orden_estacion_dia_orden_estacion_id` (el "hallazgo menor sin aplicar" de la
  Tanda 4b, redundante con la `UNIQUE` compuesta) y `ix_orden_estacion_dia_fecha_transmision`
  (sin filtro real que lo respalde) — ambos quitados.
- **`spots_solicitados > 0` — APLICADO (Tanda 4d):** antes `>= 0`; ver razonamiento en
  la sección 6. Espejo en el schema Pydantic (`gt=0`) y validación del caso de
  fallback a `spots_asignados`.
- **3 CHECK de suma exacta en `orden_estacion` — APLICADOS (Tanda 4d):**
  `ck_orden_estacion_margen_oir_emisora`, `ck_orden_estacion_total_oir_suma`,
  `ck_orden_estacion_total_emisora_suma` — ver sección 6.
- **Segundo incidente de contraseña expuesta — YA CORREGIDO DE RAÍZ (Tanda 4d):** el
  guard de `scripts/seed_dev.py` (validar SQLite antes de crear el engine) se aisló en
  `_verificar_solo_sqlite()`, ahora la PRIMERA instrucción de `main()`, y se agregó
  `app/tests/test_seed_dev_guard.py` (2 pruebas) que fuerza una `DATABASE_URL` no-SQLite
  y confirma que el script aborta con `SystemExit` SIN llegar a llamar `get_engine()` —
  si alguien reordena `main()` en el futuro, la prueba lo detecta. Inventario completo
  de puntos que crean un engine y podrían escribir, en la sección 12.
- **CHECK de suma exacta + SQLite = riesgo de falso positivo por `float64` (ADR-039):**
  la re-siembra reveló que SQLite no tiene tipo decimal de punto fijo — un CHECK de
  IGUALDAD entre dos sumas de `NUMERIC` calculadas por separado puede fallar
  espuriamente por 1 ULP de `float64`, aunque la aritmética `Decimal` real sea exacta.
  Los 3 CHECK nuevos se envolvieron en `ROUND(x, 2)` (no-op en SQL Server, neutraliza el
  ruido en SQLite). Cualquier CHECK futuro de este tipo (igualdad entre sumas de
  `NUMERIC`) debe usar el mismo patrón.
- **No se sembraron datos de la demo en RDS** — decisión aparte, no tomada, correcto
  no tomarla aquí.

## 11. Comandos para que el desarrollador humano ejecute (en orden)

Ninguno de estos se ejecutó en esta tanda — los ejecuta el desarrollador humano.
Secuencia final aprobada:

1. **`.venv\Scripts\python.exe -m scripts.verificar_config_bd`** — confirmar que el
   entorno apunta a SQL Server ANTES de cualquier otra cosa. Esperado:
   `✅ APUNTA A SQL SERVER (RDS)` con host/base/usuario correctos. Si dice
   `⚠️ APUNTA A SQLITE LOCAL`, hay una `DATABASE_URL` seteada en el entorno — removerla
   antes de continuar.

2. **`uv run alembic heads`** — puramente local, sin riesgo (no conecta a nada).
   Esperado: `73fa97f9e718`, un solo head.

3. **`uv run alembic current`** — conecta a RDS, SOLO LECTURA (lee `alembic_version`,
   no escribe). Esperado: `b6d9f2a4c817` (head de F0, si RDS nunca ha visto F1). Si sale
   distinto (en particular si ya muestra `73fa97f9e718`) — **detenerse, no seguir**:
   alguien ya aplicó esta migración.

4. **Solicitar a TI el snapshot de `GRC-OIR`** (permisos de snapshot en RDS no son del
   desarrollador humano — ver la petición redactada en la sección 13). Esperar
   confirmación de que el snapshot existe y es restaurable antes de continuar.

5. **Avisar al equipo antes de aplicar** — la base es compartida.

6. **`uv run alembic upgrade head`** — aplica la migración. Esperado: log de Alembic
   mostrando `Running upgrade b6d9f2a4c817 -> 73fa97f9e718`, sin errores. Ver la
   sección 14 (Plan de contingencia) si falla a medias.

7. **Verificar en SSMS** con las 8 consultas de solo lectura de
   `docs/modulos/f1-ordenes/VERIFICACION-POST-APLICACION-RDS-F1.sql` (existencia de las
   6 tablas, tipos DATE/TIME/NVARCHAR(MAX)/NUMERIC, conteos de CHECK/FK/UNIQUE/índices,
   F0 sin tocar, `alembic_version` en `73fa97f9e718`).

8. **NO sembrar datos de demo en RDS** — decisión aparte, pendiente.

## 12. Inventario de puntos que crean un engine y podrían escribir (Tanda 4d)

Motivado por el segundo incidente de contraseña expuesta (sección 10): `seed_dev.py`
resolvió una URL viva de RDS durante una prueba local, detenida solo por el orden de
dos líneas. Se buscó (`grep` de `get_engine()`/`get_sessionmaker()`/`create_engine()`/
`settings.sqlalchemy_url` en todo `backend/`) cada punto que pudiera crear un engine
real y escribir, para verificar cuál necesita un guard "solo SQLite" y cuál no.

| Punto | ¿Crea un engine? | ¿Escribe? | ¿Necesita guard "solo SQLite"? |
|---|---|---|---|
| `scripts/seed_dev.py` | Sí (`get_engine()`) | Sí, datos de demo | **Sí — tenía guard, ahora endurecido** (`_verificar_solo_sqlite()` es la primera instrucción de `main()`, antes de imprimir o crear el engine; probado en `test_seed_dev_guard.py`). |
| `scripts/verificar_config_bd.py` | No (`make_url()` sobre el string, nunca `.connect()`) | No | No aplica — no hay engine que guardar. |
| `app/main.py` (`/health/db`) | Sí (`get_engine().connect()`) | No (`SELECT 1`, solo lectura) | No aplica — este es el punto de conexión LEGÍTIMO de la app en producción; el objetivo es que SÍ llegue a RDS quando corresponda. |
| `app/core/db.py` (`get_db()`, usado por todos los endpoints de la API) | Sí (vía `get_engine()`) | Sí, es el camino de escritura real de toda la app | No aplica — es la app en producción; SÍ debe escribir en RDS cuando así se despliegue. Guardarlo rompería el propósito del sistema. |
| `migrations/env.py` (Alembic) | Sí (`create_engine(settings.sqlalchemy_url, ...)`) | Sí, DDL de esquema | No aplica — herramienta invocada EXPLÍCITAMENTE por el desarrollador humano (`alembic upgrade/downgrade`), nunca automática; el humano decide conscientemente el destino cada vez que la corre. |
| `app/tests/*.py`, `conftest.py` | Sí, pero con `create_engine("sqlite://", ...)` **hardcodeado** — nunca leen `settings.sqlalchemy_url` | Sí, pero siempre en SQLite en memoria, aislado por prueba | No aplica — estructuralmente no pueden resolver a RDS, no hay `settings.sqlalchemy_url` de por medio. |

**Conclusión: `seed_dev.py` era el único punto que (a) resuelve `settings.sqlalchemy_url`
en tiempo de ejecución, (b) puede escribir, y (c) no está bajo control explícito del
desarrollador en cada invocación (se corre por nombre, sin pedir confirmación del
destino) — por eso era el único que necesitaba el guard, y ya lo tiene, endurecido y
con prueba.** Se buscó también un tercer lugar que imprimiera/logueara/serializara una
URL de conexión por su cuenta (`grep` de patrones `print`/`logger`/`repr(settings)`/
`str(settings)` cerca de `url`/`settings`): no se encontró ninguno — los únicos 3
`print` que tocan la URL en todo el backend (`verificar_config_bd.py` ×3,
`seed_dev.py` ×1) ya pasan por `url_enmascarada()`.

**¿Existe un script/comando separado que borra y re-siembra `dev_ordenes.db` desde
cero?** Se buscó exhaustivamente y NO existe uno: `pyproject.toml` no tiene
`[project.scripts]`; no hay `Makefile` en el repo (el único que aparece es de una
dependencia de `node_modules`, ajeno al proyecto); no hay carpeta `.vscode/` con
`tasks.json`; `docker-compose.yml`/`Dockerfile` solo arrancan `uvicorn`/`vite`, sin
migrar ni sembrar automáticamente. Se buscó también `Base.metadata.drop_all(` en todo
`backend/` — las 13 apariciones son todas dentro de fixtures de `app/tests/`, sobre un
`engine` propio creado con `create_engine("sqlite://", ...)` hardcodeado (nunca sobre
`get_engine()`/`settings.sqlalchemy_url`). El procedimiento "empezar de cero" que existe
es el documentado en el docstring de `seed_dev.py`: **3 comandos manuales** —
`rm dev_ordenes.db` (o `Remove-Item`), `alembic upgrade head`, `python -m scripts.seed_dev`
— sin un script Python que los una. El primer paso (borrar el archivo) es una operación
de sistema de archivos, no una conexión a una base de datos: no hay código Python que
abra un engine y ejecute `DROP TABLE`/`DROP DATABASE` contra lo que resuelva
`settings.sqlalchemy_url`, así que no hay un "script de mayor riesgo" que asegurar más
allá de los 6 puntos ya inventariados — el riesgo de DROP que preocupa ya está cubierto
porque el paso 2 (`alembic upgrade head`) pasa por `migrations/env.py` (humano,
explícito) y el paso 3 por el guard ya endurecido de `seed_dev.py`.

## 13. Petición a TI

Texto sugerido para la solicitud a TI (snapshot + reporte del incidente de credencial).
Dos asuntos independientes, no mezclarlos en el mismo hilo si TI los atiende por
separado.

> **Asunto 1 — Snapshot de `GRC-OIR` antes de aplicar una migración**
>
> Vamos a aplicar una migración de esquema a la base `GRC-OIR` (instancia
> `devapps...`) para el módulo de Órdenes (F1). Es aditiva: crea 6 tablas nuevas
> (`orden_cliente`, `orden_cliente_vobo_item`, `orden_estacion`, `orden_estacion_dia`,
> `verificacion`, `incidencia`) y no modifica ni elimina ninguna tabla existente.
> Aun así, por ser una base compartida por el equipo, pedimos un snapshot restaurable
> de `GRC-OIR` inmediatamente antes de aplicarla, como respaldo estándar. Avisamos
> cuando el snapshot esté confirmado para proceder.
>
> **Asunto 2 — Reporte de credencial expuesta en logs locales**
>
> Durante el desarrollo y las pruebas de la migración anterior, la contraseña del
> usuario `TESTGRCOIRDB` se imprimió en texto plano en la salida de una herramienta de
> diagnóstico, en dos ocasiones distintas, por el mismo error de programación: la
> función de SQLAlchemy que debía ocultarla (`hide_password=True`) no cubre el caso en
> que la contraseña viaja empaquetada dentro de un parámetro de conexión (`odbc_connect=`),
> que es como este proyecto arma la cadena de conexión a SQL Server. El error ya se
> corrigió de raíz con una función de enmascarado compartida y una prueba automatizada
> que impide que se repita. La contraseña **no llegó a ningún archivo del repositorio**
> — quedó únicamente en el historial de dos sesiones de desarrollo locales. Como es una
> credencial compartida por el equipo, dejamos en sus manos la decisión de rotarla.

## 14. Plan de contingencia — si `alembic upgrade head` falla a medias

- **Qué esperar:** el log de Alembic confirmó en modo offline `Will assume
  transactional DDL` — toda la migración corre dentro de una sola
  `BEGIN TRANSACTION`/`COMMIT` (ver el SQL completo, sección 8). Si algo falla a mitad
  de camino, SQL Server revierte la transacción completa automáticamente: no debería
  quedar ninguna de las 6 tablas a medio crear, ni algunas tablas sí y otras no.
- **Cómo confirmar que efectivamente revirtió:** correr `alembic current` — debe seguir
  mostrando `b6d9f2a4c817` (el head de F0, sin avanzar). Complementar con la consulta 1
  del archivo de verificación (`VERIFICACION-POST-APLICACION-RDS-F1.sql`): debe devolver
  **0 filas** (ninguna de las 6 tablas de F1 debería existir si la transacción revirtió).
  Si `alembic current` muestra `73fa97f9e718` pero la consulta 1 no devuelve las 6
  tablas, o viceversa, hay un estado inconsistente entre `alembic_version` y el esquema
  real — no seguir, es la señal más seria de que algo salió mal fuera de lo esperado.
- **Si el fallo viene de alguno de los 3 CHECK con `ROUND`:** son los únicos elementos
  de esta migración que nunca han corrido contra un motor SQL Server real (todo lo
  demás se validó offline contra el dialecto `mssql`, pero un `CHECK` solo se evalúa de
  verdad al insertar una fila, y esta migración no inserta filas). Si el error ocurre al
  CREAR la tabla (sintaxis de `ROUND` dentro de `CHECK`), sería un error de compatibilidad
  de sintaxis T-SQL — revisar el mensaje exacto de SQL Server sobre la línea del
  `CONSTRAINT ck_orden_estacion_margen_oir_emisora`/`_total_oir_suma`/`_total_emisora_suma`
  (sección 8 de este informe tiene el texto exacto). `ROUND(numeric_expression, length)`
  es una función estándar de T-SQL desde siempre, así que un error de sintaxis ahí sería
  inesperado y señal de que algo más específico del entorno RDS no está contemplado en
  este informe — no es un error que se pueda resolver "ajustando un valor", amerita
  parar e investigar antes de reintentar.
- **Cuándo restaurar el snapshot en vez de intentar arreglar:** si la transacción NO
  revirtió limpiamente (el punto anterior detectó un estado inconsistente), o si
  después de revertir sola quedó cualquier duda sobre el estado de una tabla de F0 (la
  consulta 4 del archivo de verificación debería seguir devolviendo 0 filas incluso
  después de un fallo — si no, algo tocó F0 y eso es motivo de restaurar, no de
  depurar en caliente sobre la base compartida). Regla general: un fallo que la
  transaccionalidad ya resolvió sola (current sigue en `b6d9f2a4c817`, las 6 tablas de
  F1 no existen, F0 intacto) se investiga con calma en local antes de reintentar en RDS;
  cualquier fallo que deje la base en un estado que este informe no anticipó se
  resuelve restaurando el snapshot primero, investigando después.
