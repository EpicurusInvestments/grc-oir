# Plan de pruebas — F1 (Órdenes) contra AWS RDS, primera vez con datos reales

> Contexto: esta migración nunca sembró datos en RDS a propósito (decisión aparte,
> documentada en el informe de migración). Esto significa que las 6 tablas de F1 estarán
> VACÍAS al terminar `alembic upgrade head` — todo lo que se vea aquí lo capturas tú a
> mano, por la UI o por la API directamente.
>
> **Convención de datos de prueba (obligatoria):** cada `OrdenCliente` de prueba lleva el
> prefijo **`PRUEBA F1 — `** al inicio del campo `producto` (es texto libre, visible en
> listas y en el detalle). Cada `OrdenEstacion` de prueba lleva el mismo prefijo al
> inicio de `observaciones_estacion`. Es la única forma de identificar a simple vista, en
> una base compartida sin `activo`, qué es tuyo y qué no. La consulta de la sección 6
> lista todo lo marcado así.

---

## 1. Humo

- Backend arriba apuntando a RDS (ver instrucciones de cambio de modo, mensaje aparte),
  `GET /docs` responde con la página de Swagger.
- `GET /api/v1/ordenes/clientes` (lista de OC) responde **200 con lista vacía**, no un
  error. Un error aquí (500, timeout) antes de crear nada ya te dice que el problema es
  de conexión/esquema, no de datos.
- `GET /health/db` responde `{"status": "ok", "db": "reachable"}`.

## 2. Primera captura — aquí es donde falla `created_by` si el usuario no existe

Crea una `OrdenCliente` mínima por la UI (con el prefijo `PRUEBA F1 —` en "Producto").

**Si falla con un error 404 mencionando "No existe un Usuario con nombre_usuario=..."**:
es exactamente el caso que revisamos antes de aplicar — el usuario configurado en
`VITE_DEV_USER` (`frontend/.env`) no tiene fila en la tabla `usuario` de RDS. No es un
bug de esta migración; es una discrepancia de configuración entre el frontend (pensado
para SQLite, donde `seed_dev.py` sí siembra ese usuario) y RDS (donde el único usuario
sembrado por una migración real es `dev.admin`, vía F0-04). Solución: cambia
`VITE_DEV_USER=dev.admin` y `VITE_DEV_AREA=admin` en `frontend/.env`, reinicia `npm run
dev` (Vite no recarga `.env` en caliente), y reintenta.

**Si falla con cualquier otro 500/error crudo:** copia el mensaje completo — no es un
caso ya anticipado en este documento, hay que investigarlo antes de seguir.

## 3. Flujo completo

Con la primera OC ya creada (paso 2), continúa el ciclo entero, marcando cada
`OrdenEstacion` que crees con el prefijo en `observaciones_estacion`:

1. Completa el checklist de Vo.Bo. (los 10 ítems) y da Vo.Bo. a la OC.
2. Deriva una `OrdenEstacion` (elige una `Estacion`/plaza real de las que existan en
   RDS — ver sección 5 para confirmar cuáles hay).
3. Avanza esa OE a programados (2.2).
4. Avanza a reales (2.3) — este paso genera `Verificacion` y, si hay diferencia,
   `Incidencia` automáticamente.
5. Cierra la OC.

**Qué mirar en cada paso:** que el estado visual (badge) en pantalla corresponda al
paso — usa esta tabla como referencia exacta (mapeo backend→pantalla,
`frontend/src/modules/ordenes/adapters/vocabulario.ts`):

| Paso | `estatus_orden`/`estatus` real (backend) | Etiqueta que debe verse en pantalla |
|---|---|---|
| OC recién creada | `recibida` | "1 · Orden cliente" (sin Vo.Bo.) |
| Vo.Bo. completo | `capturada` | "1 · Orden cliente" (con Vo.Bo.) |
| OE creada | `asignada` | "Asignada / afiliado" |
| OE en programados | `en_transmision` | "Programados conciliados" |
| OE en reales / cerrada | `cerrada` | "Reales conciliados" |
| OC cerrada | `orden_cerrada` | "Orden cerrada" |

Si alguna etiqueta no corresponde a esta tabla con datos reales, es el primer caso real
de la limitación conocida del adaptador (documentada en `vocabulario.ts`) — repórtamelo
con el estado real (columna izquierda) y lo que se vio en pantalla.

## 4. Aritmética decimal — primera vez sobre `NUMERIC` real, no sobre `float64` de SQLite

Con al menos una `OrdenEstacion` ya creada (paso 3.2), corre en SSMS:

```sql
SELECT
    orden_estacion_id,
    folio_orden_estacion,
    importe_estacion,
    importe_oir,
    importe_emisora,
    importe_oir + importe_emisora AS suma_oir_mas_emisora,
    (importe_oir + importe_emisora) - importe_estacion AS diferencia_margen,
    total_oir,
    importe_oir + iva_oir AS suma_total_oir,
    total_emisora,
    importe_emisora + iva_emisora AS suma_total_emisora
FROM orden_estacion
WHERE observaciones_estacion LIKE 'PRUEBA F1 — %'
ORDER BY created_at DESC;
```

**Esperado:** `diferencia_margen = 0.00` en todas las filas; `total_oir` idéntico a
`suma_total_oir`; `total_emisora` idéntico a `suma_total_emisora`. Si alguna fila
muestra una diferencia distinta de cero, es la primera evidencia real de que el
invariante NO se cumple en SQL Server como predice ADR-039 — deja de capturar y
repórtamelo con la fila exacta, es una alarma seria (el análisis dice que esto no debería
pasar nunca en `NUMERIC` real).

## 5. Los 3 CHECK con `ROUND` — nunca han corrido en un motor real

Confirmar que rechazan de verdad (no solo que existen) requiere provocar una violación a
propósito. Esto es un intento de escritura que **debe fallar** — no se hace por la API
(el servicio nunca produce un dato inconsistente, así que la API no tiene forma de
mandar uno) y no persiste nada si el CHECK funciona:

```sql
-- Debe FALLAR con un error mencionando ck_orden_estacion_margen_oir_emisora.
-- Si "tiene éxito" (0 rows affected sin error, o commit exitoso), es grave: el CHECK
-- no está activo. Repórtamelo de inmediato, sin seguir capturando.
UPDATE orden_estacion
SET importe_emisora = importe_emisora + 1
WHERE observaciones_estacion LIKE 'PRUEBA F1 — %';
```

Repite el mismo patrón (sumar 1 a `total_oir` o `total_emisora` directamente) para
confirmar los otros dos CHECK si quieres verificarlos por separado. Después de cada
intento, un `SELECT` rápido sobre esa fila confirma que el valor NO cambió (la
transacción falló completa, no a medias).

## 6. Listar todo lo creado como prueba (para limpiar/reportar después)

```sql
SELECT orden_id, folio_orden, producto, estatus_orden, created_at
FROM orden_cliente
WHERE producto LIKE 'PRUEBA F1 — %'
ORDER BY created_at DESC;

SELECT orden_estacion_id, folio_orden_estacion, observaciones_estacion, estatus, created_at
FROM orden_estacion
WHERE observaciones_estacion LIKE 'PRUEBA F1 — %'
ORDER BY created_at DESC;
```

Recuerda: no hay forma de desactivar/cancelar estas órdenes hoy (ver ADR-035 — hueco de
implementación, no de esquema). Van a quedar visibles en `recibida`/`capturada`/etc. para
todo el equipo hasta que exista un endpoint de cancelación. El prefijo es lo que permite
que, cuando ese endpoint exista, cualquiera pueda identificar y limpiar exactamente estos
registros sin adivinar cuáles son de prueba.
