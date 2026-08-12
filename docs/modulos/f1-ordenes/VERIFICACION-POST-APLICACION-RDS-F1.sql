-- ============================================================================
-- Verificación post-aplicación — migración F1 (73fa97f9e718) contra AWS RDS
-- ============================================================================
-- SOLO LECTURA. Ninguna consulta de este archivo modifica datos ni esquema.
-- Pensado para pegarse en SQL Server Management Studio (SSMS), sección por
-- sección, después de correr `alembic upgrade head` contra RDS.
--
-- Cada sección trae el resultado ESPERADO al lado — compara contra eso, no
-- interpretes a ojo. Si algo no cuadra, DETENTE antes de continuar con el resto
-- del plan (sembrar datos, avisar al equipo, etc.) e investiga esa sección.
-- ============================================================================


-- ── 1. Las 6 tablas de F1 existen ───────────────────────────────────────────
-- Esperado: 6 filas, una por tabla, todas con schema_name = 'dbo'.
SELECT
    t.name AS tabla,
    s.name AS esquema,
    t.create_date,
    t.modify_date
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE t.name IN (
    'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
    'orden_estacion_dia', 'verificacion', 'incidencia'
)
ORDER BY t.name;


-- ── 2a. Tipos DATE/TIME reales (no DATETIME legado) ─────────────────────────
-- Esperado: 7 filas con DATA_TYPE = 'date' (fecha_venta, fecha_inicio_campania,
-- fecha_fin_campania, fecha_cierre de orden_cliente; fecha_transmision de
-- orden_estacion_dia; fecha_verificacion de verificacion; fecha_incidencia de
-- incidencia) y 2 filas con DATA_TYPE = 'time' (hora_inicio, hora_fin de
-- orden_estacion_dia). Ninguna debe salir como 'datetime' ni 'datetime2'.
SELECT
    TABLE_NAME AS tabla,
    COLUMN_NAME AS columna,
    DATA_TYPE AS tipo
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN (
        'orden_cliente', 'orden_estacion_dia', 'verificacion', 'incidencia'
    )
    AND COLUMN_NAME IN (
        'fecha_venta', 'fecha_inicio_campania', 'fecha_fin_campania', 'fecha_cierre',
        'fecha_transmision', 'hora_inicio', 'hora_fin',
        'fecha_verificacion', 'fecha_incidencia'
    )
ORDER BY TABLE_NAME, COLUMN_NAME;


-- ── 2b. Texto largo es NVARCHAR(MAX), no NTEXT ──────────────────────────────
-- Esperado: 7 filas, TODAS con DATA_TYPE = 'nvarchar' y
-- CHARACTER_MAXIMUM_LENGTH = -1 (el -1 es como SQL Server representa "MAX").
-- Si alguna sale como DATA_TYPE = 'ntext', el tipo explícito no se aplicó.
SELECT
    TABLE_NAME AS tabla,
    COLUMN_NAME AS columna,
    DATA_TYPE AS tipo,
    CHARACTER_MAXIMUM_LENGTH AS longitud_max
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('orden_cliente', 'orden_estacion', 'verificacion', 'incidencia')
    AND COLUMN_NAME IN (
        'direccion_facturacion', 'observaciones_predefinidas', 'observaciones_libres',
        'observaciones_estacion', 'notas_transmision',
        'notas_verificacion',
        'descripcion_incidencia'
    )
ORDER BY TABLE_NAME, COLUMN_NAME;


-- ── 2c. Montos: NUMERIC con precisión y escala correctas ───────────────────
-- Esperado: NUMERIC_SCALE = 2 en todas. NUMERIC_PRECISION = 12 en precio_unitario/
-- precio_spot (tarifas); 14 en subtotal/iva/total/importe_*/iva_*/total_*/
-- monto_ajuste (montos de factura); 5 en porcentaje_comision_*/
-- porcentaje_participacion_oir (porcentajes).
SELECT
    TABLE_NAME AS tabla,
    COLUMN_NAME AS columna,
    DATA_TYPE AS tipo,
    NUMERIC_PRECISION AS precision_,
    NUMERIC_SCALE AS escala
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME IN ('orden_cliente', 'orden_estacion', 'incidencia')
    AND DATA_TYPE IN ('numeric', 'decimal')
ORDER BY TABLE_NAME, COLUMN_NAME;


-- ── 3a. Conteo de CHECK constraints — total y por tabla ─────────────────────
-- Esperado TOTAL: 39.
-- Por tabla: orden_cliente = 15, orden_cliente_vobo_item = 1, orden_estacion = 14,
-- orden_estacion_dia = 5, verificacion = 0, incidencia = 4.
SELECT
    OBJECT_NAME(cc.parent_object_id) AS tabla,
    COUNT(*) AS total_check
FROM sys.check_constraints cc
WHERE OBJECT_NAME(cc.parent_object_id) IN (
    'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
    'orden_estacion_dia', 'verificacion', 'incidencia'
)
GROUP BY cc.parent_object_id
ORDER BY tabla;

-- Total general (debe dar 39):
SELECT COUNT(*) AS total_check_f1
FROM sys.check_constraints cc
WHERE OBJECT_NAME(cc.parent_object_id) IN (
    'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
    'orden_estacion_dia', 'verificacion', 'incidencia'
);


-- ── 3b. Conteo de FOREIGN KEY constraints — total y por tabla ──────────────
-- Esperado TOTAL: 25.
-- Por tabla: orden_cliente = 9, orden_cliente_vobo_item = 2, orden_estacion = 9,
-- orden_estacion_dia = 1, verificacion = 2, incidencia = 2.
SELECT
    OBJECT_NAME(fk.parent_object_id) AS tabla,
    COUNT(*) AS total_fk
FROM sys.foreign_keys fk
WHERE OBJECT_NAME(fk.parent_object_id) IN (
    'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
    'orden_estacion_dia', 'verificacion', 'incidencia'
)
GROUP BY fk.parent_object_id
ORDER BY tabla;

SELECT COUNT(*) AS total_fk_f1
FROM sys.foreign_keys fk
WHERE OBJECT_NAME(fk.parent_object_id) IN (
    'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
    'orden_estacion_dia', 'verificacion', 'incidencia'
);


-- ── 3c. UNIQUE compuestas (constraint de tabla, no índice único de 1 columna) ──
-- Esperado: 3 filas — uq_orden_cliente_vobo_item_orden_clave,
-- uq_orden_estacion_dia_oe_fecha_hora, uq_verificacion_orden_estacion_dia.
SELECT
    kc.name AS nombre_constraint,
    OBJECT_NAME(kc.parent_object_id) AS tabla
FROM sys.key_constraints kc
WHERE kc.type = 'UQ'
    AND OBJECT_NAME(kc.parent_object_id) IN (
        'orden_cliente_vobo_item', 'orden_estacion_dia', 'verificacion'
    )
ORDER BY tabla;


-- ── 3d. Índices ix_* — total y lista completa ───────────────────────────────
-- Esperado TOTAL: 16 (excluye PK y las 3 UNIQUE de 3c, cuenta solo los que
-- empiezan con 'ix_'). Por tabla: orden_cliente = 7, orden_estacion = 7,
-- incidencia = 2. orden_estacion_dia y verificacion = 0 (sus únicos índices son
-- las UNIQUE de 3c, ya contadas ahí).
SELECT
    OBJECT_NAME(i.object_id) AS tabla,
    i.name AS nombre_indice,
    i.is_unique
FROM sys.indexes i
WHERE OBJECT_NAME(i.object_id) IN (
        'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
        'orden_estacion_dia', 'verificacion', 'incidencia'
    )
    AND i.name LIKE 'ix\_%' ESCAPE '\'
ORDER BY tabla, nombre_indice;

SELECT COUNT(*) AS total_ix_f1
FROM sys.indexes i
WHERE OBJECT_NAME(i.object_id) IN (
        'orden_cliente', 'orden_cliente_vobo_item', 'orden_estacion',
        'orden_estacion_dia', 'verificacion', 'incidencia'
    )
    AND i.name LIKE 'ix\_%' ESCAPE '\';


-- ── 4. Ninguna tabla de F0 fue tocada por esta migración ───────────────────
-- Esperado: NINGUNA fila (0 resultados). Esta migración solo debería haber
-- tocado las 6 tablas de F1 (arriba) — si sale alguna fila aquí, algo alteró el
-- esquema de F0 al mismo tiempo que se aplicó 73fa97f9e718, lo cual NO debería
-- pasar (la migración no tiene ningún alter_table/drop_table sobre F0).
-- `modify_date` en sys.tables se actualiza cuando cambia el ESQUEMA de la tabla
-- (no con INSERT/UPDATE de filas), así que es un proxy razonable de "¿se tocó
-- la estructura de esta tabla recientemente?".
-- Lista de las 15 tablas de F0 que existen HOY en el modelo (confirmado por
-- `__tablename__` en el código — `metodo_pago`/`layout_factura` de la spec v2
-- todavía no se han construido, no aplican a este chequeo).
SELECT
    t.name AS tabla_f0,
    t.modify_date
FROM sys.tables t
WHERE t.name IN (
        'agencia', 'anunciante', 'marca', 'categoria', 'contrato', 'plaza',
        'afiliado', 'estacion', 'tarifa_plaza', 'cuenta_contable',
        'empresa_facturadora', 'vendedor', 'usuario',
        'constantes_sistema', 'log_cambio_parametro'
    )
    AND t.modify_date > DATEADD(MINUTE, -30, SYSUTCDATETIME());
-- Ajusta la ventana de -30 minutos si la aplicación de la migración tardó más.


-- ── 5. Revisión que quedó registrada en alembic_version ─────────────────────
-- Esperado: EXACTAMENTE 1 fila, version_num = '73fa97f9e718'.
SELECT version_num
FROM alembic_version;
