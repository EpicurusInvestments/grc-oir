# Guion de regresión manual — F0 (Catálogos), tras el trabajo de F1

> Motivo: la fase F1 modificó 6 archivos de `core/` (compartidos por TODO el backend),
> movió 4 archivos de infraestructura CRUD de `catalogos/` a `app/shared/` (ADR-032), y
> tocó los 14 archivos de `catalogos/` para importar desde la nueva ubicación. La
> migración de esquema es aditiva y no toca F0; **el código sí lo toca**, y F0 ya estaba
> validado y en uso. Los 235 pytest en verde prueban que el código sigue haciendo lo que
> las pruebas automatizadas revisan — no prueban que la experiencia real en pantalla
> siga intacta. Este guion es esa segunda verificación.
>
> Arranca en `http://localhost:5173/catalogos`. Ejecuta las secciones en el orden en que
> aparecen — están ordenadas por riesgo, de mayor a menor. **Si el tiempo apremia, A y B
> no se omiten; C y D se pueden posponer.**

**Formato de cada caso:**

```
### CP-XX · Título corto
**Pantalla:** ...
**Precondición:** ...
**Pasos:** ...
**Resultado esperado:** ...
**Estado:** ⬜ Pendiente
```

---

## A. Máxima prioridad — lo que más cambió y lo que más cuesta si falla

### CP-01 · Editar un campo sensible con motivo, y verlo en el historial
**Pantalla:** Catálogos → Agencias → detalle de cualquier agencia → "% comisión por defecto"
**Precondición:** Ninguna. Este campo pasa por `audit.py`/`field_permissions.py` (ambos
modificados en esta fase).
**Pasos:**
  1. Abre el detalle de una agencia y localiza "% comisión por defecto" (tiene el tag de
     campo auditado).
  2. Clic en editar ese campo. Debe aparecer el campo obligatorio **"Motivo del cambio"**
     (placeholder "Requerido al modificar el valor…").
  3. Intenta guardar SIN llenar el motivo.
  4. Llena un motivo de prueba (p.ej. "Prueba de regresión F0 tras cambios de F1") y
     guarda con un valor nuevo.
  5. Baja a la sección **"Historial de cambios"** del mismo panel.
**Resultado esperado:** Paso 3 bloquea el guardado y exige el motivo. Paso 4 guarda sin
error. Paso 5 muestra una fila nueva con el formato `% comisión por defecto: {valor
anterior} → {valor nuevo}` seguida de `{fecha} · {usuario} · {tu motivo}` — la fila más
reciente arriba.
**Estado:** ⬜ Pendiente

### CP-02 · Subir, ver y borrar un adjunto de contrato (S3)
**Pantalla:** Catálogos → Contratos → detalle de un contrato → sección de adjuntos
**Precondición:** Confirma primero con qué `STORAGE_BACKEND` está corriendo el backend
(revisa tu `.env`: `local` guarda en disco del servidor, `s3` sube al bucket real
`S3_BUCKET_CONTRATOS` — confírmalo tú mismo, no lo imprimas en ningún log compartido).
Si es `s3`, este caso sube un archivo real al bucket compartido del equipo — usa un PDF
de prueba pequeño y bórralo al final (paso 4).
**Pasos:**
  1. Sube un PDF de prueba al contrato.
  2. Refresca el detalle y confirma que aparece en la lista de adjuntos.
  3. Ábrelo/descárgalo desde la lista.
  4. Bórralo desde la misma pantalla.
**Resultado esperado:** Sube sin error, aparece en la lista con nombre y tamaño
correctos, se abre/descarga con el mismo contenido que subiste, y desaparece de la lista
tras borrarlo. Si `STORAGE_BACKEND=s3`: confirma que YA NO aparece en un segundo refresh
(no solo optimista en el cliente).
**Estado:** ⬜ Pendiente

### CP-03 · Máquina de estados de Contrato — transición válida
**Pantalla:** Catálogos → Contratos → detalle → sección "Cambiar estado"
**Precondición:** Un contrato en estado `vigente`.
**Pasos:**
  1. Abre un contrato `vigente`. Deben verse los botones "Suspender", "Finalizar",
     "Cancelar" (este último en rojo).
  2. Clic en "Suspender".
  3. Vuelve a abrir el mismo contrato: deben verse "Reactivar" y "Cancelar" (ya no
     "Finalizar" ni "Suspender" otra vez).
**Resultado esperado:** El estado cambia a `suspendido` sin error, y los botones
disponibles reflejan exactamente las transiciones permitidas desde ese nuevo estado
(`suspendido → {vigente, cancelado}`).
**Estado:** ⬜ Pendiente

### CP-04 · Máquina de estados de Contrato — estado terminal
**Pantalla:** Catálogos → Contratos → detalle de un contrato `cancelado`
**Precondición:** Un contrato ya en estado `cancelado` (o cancela uno de prueba primero
con el botón "Cancelar").
**Pasos:**
  1. Abre el detalle de ese contrato.
**Resultado esperado:** El panel muestra el mensaje `El contrato está «cancelado»
(estado terminal): no admite más transiciones.` y ningún botón de cambio de estado.
**Estado:** ⬜ Pendiente

### CP-05 · Baja con dependientes activos — el patrón "forzar"
**Pantalla:** Catálogos → Agencias → detalle de una agencia con anunciantes activos
**Precondición:** Una agencia que tenga al menos 1 `Anunciante` activo asociado.
**Pasos:**
  1. Clic en "Desactivar" sobre esa agencia.
  2. En el diálogo de confirmación, lee el mensaje.
  3. Clic en "Desactivar" (confirmar) dentro del diálogo.
  4. Refresca y vuelve a abrir la misma agencia.
**Resultado esperado:** El diálogo dice exactamente `Esta agencia tiene N anunciante(s)
activo(s). ¿Desactivarla de todos modos?` con N igual al conteo real. Tras confirmar, la
agencia queda inactiva (sin afectar el estado de sus anunciantes). Repite este mismo caso
en **Plazas** o **Afiliados** (mismo patrón de `forzar`) al menos una vez más.
**Estado:** ⬜ Pendiente

### CP-06 · Baja simple, sin dependientes
**Pantalla:** Cualquier catálogo, un registro sin dependientes activos
**Precondición:** Un registro (p.ej. un Vendedor sin órdenes/comisiones asociadas) sin
nada que dependa de él.
**Pasos:**
  1. Clic en "Desactivar".
**Resultado esperado:** Se desactiva de inmediato, SIN diálogo de confirmación de
dependientes (ese diálogo solo debe aparecer cuando de verdad hay dependientes activos).
**Estado:** ⬜ Pendiente

---

## B. Alta prioridad — CRUD genérico de los 11 catálogos (misma infraestructura movida a `app/shared/`)

Los 11 catálogos comparten la MISMA infraestructura genérica
(`BaseRepository`/`BaseService`/`crud_router`, reubicada de `catalogos/` a `app/shared/`
en esta fase — ADR-032). Si esa reubicación rompió algo, se ve igual en todos. En vez de
repetir el mismo caso 11 veces, ejecuta la plantilla completa (listar → crear → editar →
baja lógica) en **los 3 marcados con ⚠️ (mayor complejidad de datos/relaciones)** y,
para el resto, basta con **listar + abrir el detalle de 1 registro** (más rápido, sigue
detectando un router/import roto).

**Plantilla (aplícala completa a los 3 con ⚠️):**
  1. Abre el catálogo desde el sidebar. **Esperado:** la lista carga con datos reales,
     sin error en consola.
  2. Crea un registro nuevo con datos mínimos válidos. **Esperado:** aparece en la lista
     de inmediato, con folio/id si aplica.
  3. Edita un campo no sensible del registro recién creado. **Esperado:** guarda y se
     refleja en la lista/detalle sin recargar la página.
  4. Desactívalo (baja lógica). **Esperado:** desaparece de la vista "Activos" (o se
     marca como inactivo) y NO se borra físicamente (puede seguir viéndose con un
     filtro "Inactivos" si la pantalla lo ofrece).

| # | Catálogo | Sidebar | Cobertura mínima | Estado |
|---|---|---|---|---|
| CP-07 | Anunciante ⚠️ (tiene Marca anidada) | Comerciales → Anunciantes | Plantilla completa, incluida 1 Marca anidada | ⬜ |
| CP-08 | Agencia | Comerciales → Agencias | Listar + abrir 1 detalle | ⬜ |
| CP-09 | Contrato ⚠️ (ya cubierto por A, marca solo "listar" aquí) | Comerciales → Contratos | Listar + abrir 1 detalle | ⬜ |
| CP-10 | Afiliado (con Estaciones) ⚠️ | Operación → Afiliados y estaciones | Plantilla completa, incluida 1 Estación anidada | ⬜ |
| CP-11 | Plaza | Operación → Plazas | Listar + abrir 1 detalle | ⬜ |
| CP-12 | TarifaPlaza ⚠️ (anti-solapamiento, ADR-015) | Operación → Tarifas por plaza | Plantilla completa + intenta crear una tarifa que se solape con una vigente | ⬜ |
| CP-13 | Vendedor | Soporte → Vendedores | Listar + abrir 1 detalle | ⬜ |
| CP-14 | Categoria | Soporte → Categorías | Listar + abrir 1 detalle | ⬜ |
| CP-15 | EmpresaFacturadora | Soporte → Empresas facturadoras | Listar + abrir 1 detalle | ⬜ |
| CP-16 | CuentaContable | Soporte → Cuentas contables | Listar + abrir 1 detalle | ⬜ |
| CP-17 | ConstantesSistema | Configuración → Constantes del sistema | Listar + abrir 1 detalle (la carga CSV tiene su propio caso, C-18) | ⬜ |

**Resultado esperado (CP-12, caso especial):** al intentar crear una tarifa que se
solape en fechas con una vigente de la misma combinación plaza/duración, debe rechazarse
con 409 y un mensaje claro — NO debe crearse silenciosamente una tarifa duplicada.

---

## C. Prioridad media

### CP-18 · Carga masiva CSV de ConstantesSistema — dry-run y confirmación
**Pantalla:** Catálogos → Constantes del sistema → botón "Importar CSV"
**Precondición:** Un archivo CSV pequeño de prueba con 2-3 filas válidas.
**Pasos:**
  1. Clic en "Importar CSV" → se abre "Importar constantes desde CSV".
  2. Selecciona el archivo, deja "Duplicados" en su default, clic en "Previsualizar".
  3. Lee el banner de previsualización y la tabla por fila.
  4. Clic en "Confirmar e importar (N)".
  5. Refresca la lista de Constantes del sistema.
**Resultado esperado:** Paso 3 muestra `Previsualización (aún no se aplica nada) · N
fila(s))` con los badges Creadas/Actualizadas/Omitidas/Rechazadas y SIN que nada se haya
guardado todavía (verificable refrescando la lista antes del paso 4: no debe aparecer
nada nuevo). Paso 4 cambia el banner a "Importación aplicada". Paso 5 sí muestra las
filas nuevas/actualizadas.
**Estado:** ⬜ Pendiente

### CP-19 · Dashboard y navegación entre fases
**Pantalla:** `/` (Home)
**Precondición:** Ninguna.
**Pasos:**
  1. Abre la raíz del sitio.
  2. Observa las 6 tarjetas de fase (F0 Catálogos, F1 Órdenes, F2 Facturación, F3
     Cobranza y Pagos, F4 Reportes, F5 Seguridad).
  3. Clic en la tarjeta de F0.
  4. Regresa al Home y clic en la tarjeta de F1.
  5. Intenta clic en F2/F3/F4/F5.
**Resultado esperado:** Las 6 tarjetas se ven con su color de fase correcto (F0 morado,
F1 teal). F0 navega a `/catalogos`, F1 navega a `/ordenes`. F2-F5 se muestran como
"Próximamente", NO navegables (sin romper el layout ni tirar un error de ruta).
**Estado:** ⬜ Pendiente

---

## D. Registro de resultados

Al terminar, cuenta cuántos casos quedaron ⬜/✅/❌ y anota aquí cualquier ❌ con el
caso, lo que pasó, y si bloquea la aplicación de F1 en RDS o puede resolverse después:

```
CP-__ · [descripción de la falla]
```
