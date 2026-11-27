# F4 — Reportes: plan completo (tandas) + detalle de Tanda 1 (v2, tras pull de main)

## Contexto

F0–F3 están completas en `main`. La ficha `docs/modulos/f4-reportes/f4-reportes.md`
(refinada 2026-11-26, aún no commiteada) resolvió casi todas las reglas de negocio de
F4: Estado de Resultados (P&L) sin IVA + 3 dashboards (Comercial, Cobranza, Operativo),
solo lectura, sin cierre/snapshots, exportable a Excel/CSV. Este plan traduce esa ficha
a archivos concretos, verificada contra el código REAL (no solo la spec BD v2 — el
docx de referencia describe `requisicion_comision_vendedor`/`orden_id`, que ADR-219 ya
desactualizó) y contra una revisión fresca de `origin/main` pedida explícitamente antes
de cerrar el plan.

### Qué cambió al bajar `origin/main` (y cómo afecta el plan)

La rama `feature/f4-reportes` estaba exactamente en el mismo commit que `main` cuando
se creó (`3be80cb`, mi commit de auditoría de documentación), así que el `git merge
--ff-only origin/main` fue limpio, sin conflictos ni pérdida de trabajo local. Trajo
**6 commits / PR #75 — ADR-293: Notas de Crédito en Facturas al cliente**, que SÍ
afecta directamente a F4 (toca `FacturaCliente`/`CobranzaFactura`, las dos entidades
centrales de Ingresos):

- Una Nota de Crédito **no es una entidad nueva**: es una `FacturaCliente` con
  `tipo_comprobante == "E"`, **sin órdenes propias**, con `subtotal_factura`/
  `iva_factura`/`total_factura` persistidos en **NEGATIVO** (CHECK constraint
  condicional por `tipo_comprobante`, única forma de garantizarlo a nivel de esquema).
- Al timbrarse, dispara un `PagoCliente` **SINTÉTICO** (`PagoCliente.factura_egreso_id`
  FK, `UNIQUE`, no nulo) sobre la `CobranzaFactura` de la **factura de origen** —
  `monto_aplicado` = el valor **absoluto** (positivo) del total de la NC.
- **Efecto en el plan de Tanda 1 (confirmado contigo con AskUserQuestion):**
  - *Facturado en el periodo* ya **neta la NC automáticamente**: como su
    `subtotal_factura` vive negativo, un `SUM()` normal sobre `FacturaCliente` ya la
    resta sin ningún filtro ni caso especial por `tipo_comprobante`.
  - *Cobrado en el periodo* **debe excluir** el `PagoCliente` sintético de la NC
    (`factura_egreso_id IS NOT NULL`) — no es efectivo real cobrado, es un ajuste
    contable cuyo efecto YA se reconoció al reducir Facturado. Incluirlo duplicaría el
    efecto de la NC en el P&L.

Repasé también los demás ADRs nuevos de `main` desde la última vez que leí la ficha
(284-292) y ya estaban contemplados en la versión anterior de este plan; ADR-293 es el
único cambio con impacto real en las fórmulas. Confirmé además que cancelar una Nota de
Crédito SÍ marca `estado_facturacion = 'cancelada'` en esa misma fila (mismo mecanismo
que cualquier `FacturaCliente`), así que el filtro de "Facturado" la excluye igual que a
cualquier factura cancelada, sin caso especial.

## Decisiones de negocio confirmadas (AskUserQuestion, dos rondas)

| # | Pregunta | Decisión |
|---|---|---|
| 1 | `CostoAdicional.monto_costo` (Nóminas/Overhead) ¿incluye IVA? | **No.** Se resta directo, sin prorrateo. |
| 2 | `Requisicion.monto_requisicion` ¿incluye IVA? | **Confirmado: SÍ incluye IVA** (confirmado con el equipo el 2026-11-26, tras bajar a producción con el supuesto documentado). El prorrateo implementado en Tanda 1 (`monto_requisicion × monto_factura_* / total_factura_*`) ya es correcto tal cual, sin cambios de código. |
| 3 | Vendedor secundario en el dashboard comercial (Tanda 2) | **Corregido tras tu aclaración:** "principal"/"secundario" es un rol POR ORDEN, no una identidad fija del vendedor — la misma persona puede ser principal en una orden y secundario en otra. En el corte "por vendedor", cada `Vendedor` es UNA fila que suma su comisión ganada en AMBOS roles (comisión como principal en las órdenes donde lo fue + comisión como secundario en las que lo fue), para no volverlo invisible si solo participó como secundario. "Ventas" (el monto de la orden) se sigue atribuyendo una sola vez por orden — no se duplica el total de la orden por tener dos vendedores — así que la columna "Ventas" del corte por vendedor representa específicamente sus órdenes como PRINCIPAL, mientras que "Comisión total" sí suma ambos roles. El KPI global de Ventas (suma de `OrdenCliente.total`) no cambia. Se detalla con precisión de SQL cuando se planee Tanda 2 a fondo. |
| 4 | Dependencia para `.xlsx` | `openpyxl` (no hay ninguna instalada hoy). |
| 5 | Pago sintético de una Nota de Crédito, ¿cómo se trata en "Cobrado"? | **Se excluye** (`PagoCliente.factura_egreso_id IS NULL` en la suma de Cobrado). |

### Hallazgos informativos (no requieren decisión, solo que los conozcas)

- **Fecha de emisión real de `FacturaCliente`:** es `fecha_factura` (NOT NULL, se
  captura una sola vez al alta). Confirmado con evidencia de código, no solo por
  nombre: es el mismo valor que se manda como `fecha_emision` al archivo plano del PAC
  (`factura_cliente.py:1628`, `fecha_emision=datetime.combine(obj.fecha_factura, ...)`).
  `fecha_timbrado`/`fecha_entrega_factura` son eventos posteriores (cuándo respondió el
  PAC, cuándo se entregó al cliente), no la fecha de emisión. Es la que usa el plan.
- **Moneda:** solo `FacturaCliente` tiene un campo de moneda (`moneda_sat`, metadato
  fiscal para el CFDI, catálogo `MonedaSAT`, default implícito `"MXN"` si es `NULL`).
  Ninguna otra entidad del P&L (`FacturaAfiliado/Agencia/Vendedor`, `Requisicion`,
  `CostoAdicional`, `OrdenCliente`) tiene campo de moneda, y **el sistema no implementa
  conversión de divisa en ningún punto** (sin tasa de cambio, sin lógica de
  conversión). En la BD de desarrollo (`DEMO-GRC-OIR`), las 100% de las facturas tienen
  `moneda_sat IS NULL` (⇒ MXN). El P&L asume MXN consistente con el resto del sistema;
  si algún día se captura una factura en otra moneda sin conversión, el monto se
  sumaría tal cual — es una limitación preexistente de todo el sistema, no algo que F4
  deba resolver por su cuenta.

## Plan completo por tandas (resumen)

| Tanda | Contenido |
|---|---|
| **1** | Utilidad de exportación (`app/shared/exportacion.py`) + Estado de resultados (back+front) + activar F4 en `phaseRegistry` |
| **2** | Dashboard comercial + Dashboard de cobranza (back+front) |
| **3** | Dashboard operativo (back+front) + cierre de documentación |

Cada tanda: plan breve → aprobación → código → validación manual (Swagger/SSMS/navegador)
→ commits por capa → docs. Este documento detalla **Tanda 1**; Tandas 2–3 se planean
con el mismo nivel de detalle cuando toquen.

---

## Tanda 1 — Detalle

### A. Archivos a crear/modificar

**Backend — módulo nuevo `backend/app/modules/reportes/`:**
- `__init__.py`
- `schemas.py` — DTOs de salida, sin `Create`/`Update` (F4 es 100% lectura).
- `repository.py` — consultas agregadas y las consultas "crudas acotadas" que el
  service prorratea (ver C). Recibe `db: Session` + rangos de fecha ya resueltos.
- `service.py` — arma el P&L: ventanas mensuales, llama al repository, aplica
  fórmulas (prorrateo, utilidad bruta/neta, márgenes, tendencia), resuelve "mes en
  curso" con zona horaria correcta.
- `router.py` — `APIRouter(prefix="/reportes", tags=["reportes"])`, 2 endpoints.
- `tests/test_f4_01_estado_resultados.py`

**Backend — archivos existentes:**
- `app/main.py` — montar `reportes_router` en `api_v1`.
- `app/core/security.py` — agregar las 4 claves RBAC de F4 (ver C).
- `pyproject.toml` — `openpyxl>=3.1`.
- `app/shared/exportacion.py` (**nuevo**, transversal) — neutralización
  CSV/formula-injection + builders `.xlsx`/`.csv` (ver C).
- `app/core/security_log.py` — agregar `EventoSeguridad.EXPORTACION_REPORTE`.

**Frontend — módulo nuevo `frontend/src/modules/reportes/`:**
- `types.ts`, `api.ts`, `hooks.ts`
- `components/` — tarjetas KPI, tabla del P&L (3 secciones + totales), tabla "Detalle
  histórico mensual", botón Exportar.
- `pages/EstadoResultadosPage.tsx` — selector de mes.
- `reportesRegistry.tsx` + `pages/ReportesExplorerPage.tsx` — mismo patrón que
  `cobranzaRegistry.tsx`, PERO con una pieza nueva que ningún otro explorador tiene hoy
  (ver punto de "Acceso" en C): filtra sus propias entradas por permiso real, y si el
  usuario no tiene NINGUNA de las 4 claves `reportes_*`, muestra un estado vacío
  explícito ("No tienes acceso a ningún reporte") en vez de una pantalla en blanco.
- `__tests__/` — qué ve cada área; el estado vacío cuando no hay ninguna vista
  permitida.

**Frontend — archivos existentes:**
- `src/shared/phases/phaseRegistry.ts` — entrada `f4`: `enabled: true`,
  `route: "/reportes"`; corrige el comentario obsoleto de la línea 4 y la descripción
  de F4 (quita "cierre mensual", que la ficha decidió no construir). Se agrega UN campo
  opcional nuevo a la interfaz `PhaseEntry`: `visibleParaArea?: (area: Area) =>
  boolean` (si no se define, se comporta EXACTAMENTE igual que hoy para F0/F1/F2/F3/F5
  — visible para todos). Solo la entrada `f4` lo define, devolviendo `true` si el área
  aparece en alguna de las 4 listas de `RBAC.reportes_*` (más `admin`, siempre). Esto
  es nuevo porque hoy NINGUNA fase oculta su tarjeta/entrada de menú por permiso — F4
  es la primera con vistas tan restringidas (Dirección-only) que vale la pena no
  mostrar la tarjeta a quien de todas formas no podría ver nada adentro.
- `src/modules/dashboard/components/PhaseCard.tsx` y
  `src/shared/ui/AppNavDrawer.tsx` — ambos ya iteran `phaseRegistry`; se les agrega UN
  `if (entry.visibleParaArea && !entry.visibleParaArea(usuario.area)) return null`
  antes de decidir si la tarjeta/ítem se renderiza como activa o "Próximamente" —
  cuando no está definido (todas las fases salvo F4), el comportamiento no cambia en
  absoluto.
- `src/app/router.tsx` — montar `/reportes`; cada sub-ruta de vista usa
  `RequireArea` con la lista de áreas correspondiente (igual patrón que la única
  existencia hoy, `areas={["admin"]}` para usuarios) — en Tanda 1 solo
  `areas={["admin","direccion"]}` para Estado de resultados.
- `docs/modulos/transversal/dashboard-navegacion.md` — ajustar la frase "solo F4
  (Reportes) se muestra 'Próximamente'" (con esta tanda deja de ser cierto).

### B. Migración

**Ninguna esperada.** `PeriodoResultados` no se persiste (desviación consciente de la
spec, se documenta como ADR nuevo en el cierre de Tanda 3). Repository solo hace
`SELECT`/`SUM`/`GROUP BY` sobre tablas existentes. Si la validación contra SQL Server
real sugiriera un índice (`fecha_factura`, `fecha_pago_cliente`,
`fecha_pago_requisicion`, `periodo_contable`), se genera el archivo de migración, se
muestra, y se **detiene** ahí — sin `alembic upgrade`.

### C. Reglas exactas, RBAC, endpoints, exportación

#### Ventana de tiempo y "mes en curso"

Usuario elige un mes `M` (`YYYY-MM`; default: mes en curso). "Mes en curso" se calcula
con la hora de **México** (`America/Mexico_City`), nunca UTC — mismo error de fondo que
ADR-261 (entre 18:00 y medianoche, UTC ya es el día/mes siguiente). El service usa
`zoneinfo.ZoneInfo("America/Mexico_City")` para obtener "hoy" antes de derivar el
default; el resto de la ventana (los 6 meses, el rango `[inicio, fin_exclusivo)` de
cada uno) se deriva en Python sobre fechas naive, sin `EXTRACT`/`DATEPART` en SQL
(familia de riesgos ADR-014/036).

El query param `periodo` se valida con un patrón **estricto** `^\d{4}-(0[1-9]|1[0-2])$`
(Pydantic `Field(pattern=...)` en el schema de query, o un validador explícito en el
router) — rechaza meses inválidos (`"2026-13"`, `"2026-2"`) con **422**, antes de que el
valor llegue a construirse en el nombre del archivo de exportación.

#### Dónde vive el prorrateo a "sin IVA" (service, no SQL)

Para Cobrado y los 4 "Pagado" de costos directos: el **repository** trae, en UNA
consulta por renglón (JOIN acotado a la ventana del mes, nunca todo el histórico), las
filas crudas con las columnas necesarias; el **service** calcula
`ROUND(monto × razon, 2)` **fila por fila** con `Decimal.quantize(Decimal("0.01"))` y
SUMA los resultados ya redondeados — no se redondea el total al final. Esto es
deliberado para que la consulta SQL de validación (sección D) pueda reproducir el
mismo número exacto: redondear después de sumar puede diferir en centavos de redondear
antes.

#### Renglón por renglón

**INGRESOS**
- *Facturado en el periodo* = `SUM(FacturaCliente.subtotal_factura)` WHERE
  `fecha_factura` en la ventana **AND `estado_facturacion IN ('timbrada',
  'entregada', 'cobrada')`** (ajuste de esta ronda: antes decía solo "sin canceladas";
  ahora excluye también `preparada`/`enviada_a_timbrado`, un borrador no es un CFDI
  emitido — la orden solo pasa a `facturada` al timbrar, ADR-072). Las Notas de Crédito
  (`tipo_comprobante='E'`) entran en el MISMO `SUM`, sin filtro aparte: su
  `subtotal_factura` ya es negativo (CHECK constraint de ADR-293), así que se restan
  solas en cuanto estén `timbrada` o más adelante.
- *Cobrado en el periodo* = para cada `PagoCliente` con `fecha_pago_cliente` en la
  ventana, `estatus_pago = 'pagado'`, `cobranza_id IS NOT NULL` (sin huérfanos) **Y
  `factura_egreso_id IS NULL`** (excluye el pago sintético de una NC, ADR-293 — no es
  efectivo real), JOIN `CobranzaFactura` → `FacturaCliente`, calcular
  `ROUND(monto_aplicado × subtotal_factura / total_factura, 2)` (sin `ajuste`, por
  decisión de la ficha) y sumar. Guarda: si `total_factura = 0` para alguna fila
  (no debería ocurrir — el CHECK de `FacturaCliente` exige `total_factura >= 0` y en la
  práctica una factura con monto 0 no tiene sentido de negocio, pero el código no lo
  prohíbe explícitamente), se trata como razón `0` para esa fila (no división por cero,
  no excepción) y se reporta en el log de la app para revisión manual — nunca tumba el
  endpoint.

**COSTOS DIRECTOS** (cada uno con 2 subrenglones)
- *Pagos a afiliados — Facturado* = `SUM(FacturaAfiliado.monto_factura_afiliado)`
  WHERE `fecha_factura_afiliado` en la ventana. (El enum `EstatusFacturaProveedor`
  —`recibida|autorizada|pagada`— no tiene valor `cancelada`: una requisición cancelada
  revierte la factura a `recibida`, nunca la marca cancelada, así que no hay nada que
  excluir aquí.)
- *Pagos a afiliados — Pagado* = para cada `Requisicion` con `tipo_requisicion =
  'pago_afiliado'`, `estatus_requisicion = 'pagada'`, `fecha_pago_requisicion` en la
  ventana, JOIN `FacturaAfiliado` (vía `factura_afiliado_id`, obligatoria desde
  ADR-220), `ROUND(monto_requisicion × monto_factura_afiliado /
  total_factura_afiliado, 2)` — misma guarda de división por cero que arriba si
  `total_factura_afiliado = 0`.
- *Pagos a agencias* — mismo patrón, `tipo_requisicion='pago_agencia'`, JOIN
  `FacturaAgencia` (`monto_factura_agencia`/`total_factura_agencia`).
- *Comisiones a vendedores* — mismo patrón, `tipo_requisicion='comision_vendedor'`,
  JOIN `FacturaVendedor` vía `factura_vendedor_id` (reemplaza a `orden_id` desde
  ADR-219; la columna `orden_id` sigue en el modelo pero ya no se captura para este
  tipo).
- *Comisiones a agencias (req.)* — `tipo_requisicion='comision_agencia'`, sin factura
  ligada (usa `orden_id` directo). Se prorratea contra la `OrdenCliente` referenciada:
  `ROUND(monto_requisicion × OrdenCliente.subtotal / OrdenCliente.total, 2)`. Solo se
  muestra en la UI si > 0.

**COSTOS INDIRECTOS**
- *Nóminas* = `SUM(CostoAdicional.monto_costo)` WHERE `tipo_costo='nomina' AND
  periodo_contable = 'YYYY-MM'` (comparación de texto exacta, no rango de fechas). Sin
  IVA, sin prorrateo (confirmado).
- *Overhead* — igual, `tipo_costo='overhead'`.

**Totales y márgenes:**
`utilidad_bruta = Cobrado − (Pagado afiliados + Pagado agencias + Pagado comisiones
vendedores + Pagado comisiones agencias)`; `utilidad_neta = utilidad_bruta − Nóminas −
Overhead`; márgenes y % con guarda explícita contra división por cero (`None`, nunca
excepción); tendencia `M` vs `M-1` para ingresos_cobrado/utilidad_bruta/utilidad_neta.

#### RBAC

```python
"reportes_financiero": {Area.DIRECCION: Acceso.READ},
"reportes_comercial": {Area.DIRECCION: Acceso.READ, Area.VENTAS: Acceso.READ},
"reportes_cobranza": {
    Area.DIRECCION: Acceso.READ, Area.FACTURACION: Acceso.READ,
    Area.TESORERIA: Acceso.READ, Area.CXC: Acceso.READ, Area.CXP: Acceso.READ,
},
"reportes_operativo": {a: Acceso.READ for a in Area if a is not Area.ADMIN},
```

Ninguna lista `Area.ADMIN` (ADR-040). Se agregan las 4 de una vez en esta tanda aunque
solo `reportes_financiero` tenga endpoint todavía. También se actualiza `CLAUDE.md`
raíz §4 (la fila de F4 hoy solo dice `` `reportes` ``; se lista las 4 claves, igual que
ya hacen F2/F3).

#### Endpoints (Tanda 1)

- `GET /api/v1/reportes/estado-resultados?periodo=YYYY-MM` —
  `requiere_permiso("reportes_financiero:leer")`. Responde el periodo pedido (todos
  los renglones), el periodo anterior, la tendencia ya calculada, y el histórico de 6
  meses.
- `GET /api/v1/reportes/estado-resultados/exportar?periodo=YYYY-MM&formato=xlsx|csv` —
  mismo permiso. Llama `registrar_evento_seguridad(evento=EXPORTACION_REPORTE,
  actor=usuario, objetivo="estado_resultados", detalle=f"periodo={periodo}
  formato={formato}")`.

#### `app/shared/exportacion.py`

```python
_CARACTERES_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")

def neutralizar_formula(valor: str) -> str:
    """CSV/formula-injection (ADR-025): si el texto empieza con alguno de estos
    caracteres, Excel/Sheets podría interpretarlo como fórmula o usarlo para
    manipular la celda destino al pegar/importar."""
    if valor and valor[0] in _CARACTERES_PELIGROSOS:
        return "'" + valor
    return valor

def construir_xlsx(hojas: dict[str, tuple[list[str], list[list[Any]]]]) -> bytes:
    """openpyxl. Encabezados en negritas. Celdas de TEXTO que empiecen con un
    caracter peligroso se fuerzan con `cell.data_type = 's'` (tipo string explícito
    de openpyxl) en vez de dejar un apóstrofe visible en el valor — el apóstrofe
    antepuesto es el mecanismo de CSV, no hace falta (ni se ve bien) en xlsx. Celdas
    numéricas (Decimal/int/float) se escriben como número real con
    number_format='#,##0.00', nunca como texto."""

def construir_csv(encabezados: list[str], filas: list[list[Any]]) -> bytes:
    """csv.writer, BOM utf-8-sig. Celdas de texto SÍ llevan el apóstrofe de
    `neutralizar_formula` (aquí si es el mecanismo correcto: Excel/Sheets lo
    interpretan como "fuerza texto" al abrir el CSV)."""
```

### D. Pruebas

**Backend (`tests/test_f4_01_estado_resultados.py`)** — una consulta SQL independiente
**por cada renglón** (no solo Facturado), escrita a mano, NUNCA copiada del
repository. En los renglones prorrateados, la consulta hace el `ROUND` por fila antes
del `SUM`, para poder comparar al centavo:

```sql
-- Facturado clientes del mes (neta Notas de Crédito automáticamente)
SELECT SUM(subtotal_factura) FROM factura_cliente
WHERE estado_facturacion IN ('timbrada','entregada','cobrada')
  AND fecha_factura >= '2026-11-01' AND fecha_factura < '2026-12-01';

-- Cobrado del mes (excluye huérfanos y el pago sintético de Notas de Crédito)
SELECT SUM(ROUND(pc.monto_aplicado * fc.subtotal_factura / fc.total_factura, 2))
FROM pago_cliente pc
JOIN cobranza_factura cf ON cf.cobranza_id = pc.cobranza_id
JOIN factura_cliente fc ON fc.factura_id = cf.factura_id
WHERE pc.estatus_pago = 'pagado' AND pc.cobranza_id IS NOT NULL
  AND pc.factura_egreso_id IS NULL
  AND pc.fecha_pago_cliente >= '2026-11-01' AND pc.fecha_pago_cliente < '2026-12-01';

-- Pagado a afiliados del mes
SELECT SUM(ROUND(r.monto_requisicion * fa.monto_factura_afiliado /
                  fa.total_factura_afiliado, 2))
FROM requisicion r
JOIN factura_afiliado fa ON fa.factura_afiliado_id = r.factura_afiliado_id
WHERE r.tipo_requisicion = 'pago_afiliado' AND r.estatus_requisicion = 'pagada'
  AND r.fecha_pago_requisicion >= '2026-11-01'
  AND r.fecha_pago_requisicion < '2026-12-01';

-- (equivalentes para pago_agencia/comision_vendedor con sus respectivas facturas,
--  comision_agencia contra orden_cliente, nóminas/overhead directo sobre
--  costo_adicional por periodo_contable)
```

Casos:
1. Mes con datos de los 3 tipos de costo, comparado renglón por renglón contra SSMS.
2. Factura de cliente `preparada`/`enviada_a_timbrado` (borrador) → excluida de
   Facturado (ajuste de esta ronda).
3. Factura de cliente `cancelada` → excluida.
4. **Nota de crédito timbrada** → reduce Facturado automáticamente (verificar signo);
   su pago sintético NO aparece en Cobrado.
5. `PagoCliente` `cancelado` → excluido del Cobrado.
6. `PagoCliente` huérfano (`cobranza_id IS NULL`) → excluido.
7. Factura con varias órdenes (N:M) → `subtotal_factura` entra UNA sola vez.
8. Mes sin ningún dato → todos los renglones en 0, márgenes `None`.
9. Mes con utilidad negativa → signos correctos, sin `abs()` accidental.
10. Factura de afiliado con montos manuales (ADR-290) → el prorrateo usa esos valores.
11. **Pago/factura en el primer y último día del mes** → confirma que el rango
    `[inicio, fin_exclusivo)` no se come ni duplica el límite.
12. **Redondeo acumulado de varias filas** → suma de N filas redondeadas
    individualmente vs. una sola fila con el monto total (deben poder diferir en
    centavos de forma esperada y documentada, no ser un bug).
13. **Requisición `pagada` con `total_factura_*` = 0** → no truena, se reporta en vez
    de dividir por cero (conté **0 casos actuales** en `DEMO-GRC-OIR` con
    `estatus_requisicion='pagada' AND fecha_pago_requisicion IS NULL`, y 0 facturas de
    proveedor en `total=0` con requisición pagada ligada — la prueba cubre el caso
    aunque hoy no exista dato real).
14. **"Mes en curso" cerca de medianoche:** congelar el reloj a, por ejemplo, 23:30
    UTC del día 30 (= 17:30 hora CDMX, mismo día) y a 05:30 UTC del día 1 (= 23:30 CDMX
    del día ANTERIOR) — confirmar que el periodo default no se adelanta de mes por
    usar UTC en vez de `America/Mexico_City` (mismo bug que ADR-261).
15. RBAC: Ventas (sin `reportes_financiero`) → 403; Dirección → 200; Admin → 200.
16. Exportación: celda que empieza con `=`/`\t`/`\r` llega neutralizada en ambos
    formatos (apóstrofe en CSV, tipo string forzado en xlsx); montos en `.xlsx` son
    número real, no texto; `periodo` inválido (`"2026-13"`, `"26-11"`) → 422 en el
    endpoint de exportación ANTES de tocar el nombre del archivo.

**Frontend** — qué ve cada área (Dirección ve "Estado de resultados", Ventas no);
tarjeta/entrada de F4 oculta para áreas sin ninguna clave `reportes_*` (Nóminas, por
ejemplo); estado vacío del Explorer si por algún motivo se navega directo a `/reportes`
sin ningún permiso; botón Exportar; selector de mes.

### E. Dudas — todas resueltas (ver tabla de decisiones arriba)

## Verificación end-to-end (Tanda 1)

1. `cd backend && .venv/Scripts/python.exe -m uv sync` (agrega openpyxl) →
   `uv run pytest app/tests/test_f4_01_estado_resultados.py -v` en verde.
2. `uv run mypy app/modules/reportes/` y `uv run ruff check app/modules/reportes/`
   limpios.
3. Levantar backend+frontend, `/docs`, probar el endpoint con header de Dirección (200)
   y de Ventas (403).
4. Correr las ~6-8 consultas SQL independientes de la sección D contra la BD de
   desarrollo (SQL Server vía túnel) y comparar número por número con Swagger,
   incluyendo el caso de Nota de Crédito.
5. Navegar `/reportes` → "Estado de resultados": cambiar de mes, verificar tendencia y
   tabla histórica; exportar `.xlsx` y `.csv`, abrir el archivo y confirmar celdas
   numéricas reales y ninguna fórmula "viva". Confirmar que un usuario de Nóminas NO ve
   la tarjeta F4 en el Dashboard ni en el drawer.
6. `cd frontend && npm run test -- reportes && npx tsc --noEmit && npm run lint`.
7. Confirmar que `phaseRegistry.ts` enciende F4 y que ninguna fase sigue mostrándose
   como "Próximamente" salvo las que de verdad no están construidas.
