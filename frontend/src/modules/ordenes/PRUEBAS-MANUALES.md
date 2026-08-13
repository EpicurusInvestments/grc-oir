# Guion de pruebas manuales — Demo F1 Órdenes

> Archivo local, no versionado como parte del producto (vive junto al código de la demo).
> Doble propósito: validar la demo antes de presentarla **y** servir de guion de
> presentación. Ejecútalo de arriba a abajo — el orden ya es un recorrido lógico.
>
> Arranca en `http://localhost:5173/ordenes`. 

**Formato de cada caso:**

```
### CP-01 · Título corto del caso
**Pantalla:** ...
**Precondición:** ...
**Pasos:** ...
**Resultado esperado:** ...
**Estado:** ⬜ Pendiente
```

---

## A. Camino feliz — Órdenes del cliente (1.1 → 1.2)

### CP-01 · Crear una OC nueva
**Pantalla:** Órdenes del cliente → "+ Nueva orden"
**Precondición:** Ninguna.
**Pasos:**
  1. Clic en "+ Nueva orden".
  2. Llena Identificación: no. de orden, fecha de venta, empresa facturadora.
  3. Elige un Anunciante (p.ej. "Televisa Publicidad").
  4. Llena Campaña y montos: fechas, duración de spot, total de spots, precio unitario.
  5. Elige Vendedor principal.
  6. Clic en "Guardar como recibida".
**Resultado esperado:** Vuelve a la lista con la nueva OC seleccionada, folio `OC-2026-00XX`
en formato monoespaciado, estado "1 · Orden cliente" (badge rojo, 1.1 sin Vo.Bo.).
**Estado:** ⬜ Pendiente

### CP-02 · Los cálculos se actualizan mientras se escribe
**Pantalla:** Formulario de OC (nueva o edición)
**Precondición:** Formulario abierto.
**Pasos:**
  1. Escribe "Total de spots" = 100 y observa el panel "Cálculos en vivo".
  2. Cambia "Precio unitario" a 1000 sin salir del campo (blur) y observa de nuevo.
  3. Cambia la fecha de fin de campaña a un día antes de la fecha de inicio.
**Resultado esperado:** Subtotal/IVA/Total se recalculan en cada cambio sin recargar nada.
Al invertir las fechas aparece el error "La fecha de fin debe ser mayor o igual que la de
inicio." bajo el campo de fin.
**Estado:** ⬜ Pendiente

### CP-03 · Cascada anunciante → contrato/marca (y su limpieza)
**Pantalla:** Formulario de OC
**Precondición:** Formulario abierto.
**Pasos:**
  1. Elige Anunciante = "Televisa Publicidad". Observa que Contrato solo ofrece "Campaña
     Verano 2025" (no aparece el contrato finalizado "Anual 2024") y Marca solo ofrece
     "Televisa Deportes"/"Televisa Novelas".
  2. Elige un Contrato y una Marca.
  3. Cambia Anunciante a "Grupo Bimbo".
**Resultado esperado:** Al cambiar de anunciante, Contrato y Marca vuelven a "Sin
contrato"/"Sin marca" (no se queda pegada una referencia del anunciante anterior) y las
opciones se refrescan a las de Bimbo.
**Estado:** ⬜ Pendiente

### CP-04 · Snapshot de comisión: sugerido vs. sobrescrito
**Pantalla:** Formulario de OC
**Precondición:** Formulario abierto.
**Pasos:**
  1. Elige Vendedor principal = "Renata Aguilar". El % se auto-llena en 5 con la etiqueta
     "del catálogo".
  2. Cambia el valor a 8.
  3. Elige Anunciante = "Televisa Publicidad" (agencia sugerida "Mindshare México").
**Resultado esperado:** Tras el paso 2, la etiqueta cambia a "sobrescrito (cat: 5%)". Tras
el paso 3, la Agencia se auto-llena a "Mindshare México" y la Dirección de facturación se
hereda del anunciante — ambas solo porque estaban vacías (no fuerza si ya elegiste algo).
**Estado:** ⬜ Pendiente

### CP-05 · Completar el checklist y dar Vo.Bo. (1.1 → 1.2)
**Pantalla:** Órdenes del cliente → detalle de `OC-2025-0041` → "Editar"
**Precondición:** `OC-2025-0041` (Soriana) — checklist en 4/10, sin Vo.Bo.
**Pasos:**
  1. Abre el detalle de `OC-2025-0041`, clic en "Editar".
  2. Observa el checklist "Checklist de revisión (PO §2)" con 4/10 marcados y el botón
     "Dar Vo.Bo." deshabilitado.
  3. Marca los 6 ítems restantes.
  4. Clic en "Dar Vo.Bo. y capturar →".
**Resultado esperado:** El botón se habilita solo al llegar a 10/10. Tras confirmar, la OC
pasa a "1 · Orden cliente" con sub-estado 1.2 (badge ámbar en el detalle) y ya permite
"+ Asignar estaciones".
**Estado:** ⬜ Pendiente

### CP-06 · Asignar la primera estación (deriva a estado 2)
**Pantalla:** Detalle de `OC-2025-0042` → "+ Asignar estaciones"
**Precondición:** `OC-2025-0042` (Grupo Modelo) — con Vo.Bo., sin ninguna OI todavía.
**Pasos:**
  1. Abre el detalle de `OC-2025-0042`, clic en "+ Asignar estaciones".
  2. Elige una estación, captura tarifa y al menos un día de transmisión.
  3. Clic en "Guardar orden interna".
**Resultado esperado:** Se crea `OE-2025-0042A`, la OC pasa a estado raíz "2 · Orden
interna" (ya no aparece en "Órdenes del cliente" como 1.x).
**Estado:** ⬜ Pendiente

---

## B. Camino feliz — Órdenes internas (2.1 → 2.2 → 2.3)

### CP-07 · Alta de OI con balance de spots en vivo
**Pantalla:** Órdenes internas → "+ Nueva orden interna"
**Precondición:** Alguna OC en 1.2 o en estado 2 (p.ej. `OC-2025-0044`, ya sobre-asignada;
usa otra si quieres ver el balance limpio).
**Pasos:**
  1. Elige la OC de origen.
  2. Observa "Distribución de spots por estación" antes de capturar nada (ya refleja lo
     asignado por las OI existentes de esa OC, no arranca en 0).
  3. Agrega días de transmisión y ve el contador "Spots en esta OI" subir en vivo.
**Resultado esperado:** La barra pasa de ámbar ("faltan N por asignar") a verde ("✓ 100%
asignado") o roja ("⚠ excedente…") según lo que captures, sin recargar.
**Estado:** ⬜ Pendiente

### CP-08 · Capturar programados (2.1 → 2.2)
**Pantalla:** Detalle de `OE-2025-0044A` → "Capturar programados (2.2)"
**Precondición:** `OE-2025-0044A` en 2.1 (asignada al afiliado).
**Pasos:**
  1. Abre el detalle de `OE-2025-0044A`, clic en "→ Capturar programados (2.2)".
  2. Edita el horario de un día (p.ej. cambia los spots de 10 a 8) y confirma esa fila.
  3. Clic en "Avanzar a 2.2 →".
**Resultado esperado:** El contador "N modificado(s)" refleja solo la fila tocada. Al
avanzar, la OI pasa a "2.2 Programados conciliados".
**Estado:** ⬜ Pendiente

### CP-09 · Capturar reales con diferencia → incidencia automática (2.2 → 2.3)
**Pantalla:** Detalle de `OE-2025-0043B` → "Capturar reales (2.3)"
**Precondición:** `OE-2025-0043B` en 2.2 (tiene un override de programados: 12 spots el
2025-06-11).
**Pasos:**
  1. Abre el detalle, clic en "→ Capturar reales (2.3)".
  2. En la fila del 2025-06-11, captura un real de 15 spots (recuerda: se compara contra
     el PROGRAMADO EFECTIVO = 12, no contra el original de 10).
  3. Observa el panel "Al avanzar a 2.3 se generarán" antes de confirmar.
  4. Clic en "Avanzar a 2.3 →".
**Resultado esperado:** El panel previo anuncia "1 bonificación(es)" con el monto correcto
(+3 spots × precio_spot). Al avanzar, la OI pasa a 2.3 y la incidencia aparece en su
detalle y en la pantalla "Incidencias".
**Estado:** ⬜ Pendiente

### CP-10 · Ver la Verificación derivada
**Pantalla:** Verificaciones
**Precondición:** Cualquier OI en 2.3 (p.ej. la del CP-09, o `OE-2025-0043C` ya precargada
con un descuento).
**Pasos:**
  1. Entra a "Verificaciones" desde el menú lateral.
  2. Busca el folio de la OI y selecciónala.
**Resultado esperado:** Tabla día a día programado vs. real, con el aviso "vista derivada
de la orden interna…". Las OI en 2.1/2.2 NO aparecen en esta lista.
**Estado:** ⬜ Pendiente

### CP-11 · Ver la Incidencia generada
**Pantalla:** Incidencias
**Precondición:** Al menos una incidencia (las 3 precargadas, o la del CP-09).
**Pasos:**
  1. Entra a "Incidencias".
  2. Filtra por "Bonificaciones" y luego por "Descuentos".
  3. Selecciona una y usa "Ver orden interna →".
**Resultado esperado:** El filtro reduce la lista correctamente; el detalle muestra
asignados/reales/diferencia/monto con signos coherentes (bonificación = monto positivo en
verde, descuento = negativo en rojo).
**Estado:** ⬜ Pendiente

---

## C. Cierre de la OC (estado 2 → 3)

### CP-12 · Cerrar una OC con todas sus OI en 2.3
**Pantalla:** Detalle de `OC-2025-0045` → "Cerrar orden →"
**Precondición:** `OC-2025-0045` (Marinela) — 3 OI, las 3 en 2.3, 120/120 exacto.
**Pasos:**
  1. Abre el detalle de `OC-2025-0045` (verifica que el botón "Cerrar orden →" SÍ aparece).
  2. Clic en "Cerrar orden →".
  3. Revisa "Transmitido vs. vendido" y "Ajuste por incidencias" (una de sus OI tiene una
     bonificación).
  4. Adjunta los 2 documentos simulados, marca "Confirmo…" y clic en "Cerrar orden →
     Estado 3".
**Resultado esperado:** La OC pasa a "3 · Orden cerrada"; ya no ofrece "+ Asignar
estaciones" ni "Cerrar orden" de nuevo.
**Estado:** ⬜ Pendiente

### CP-13 · Cerrar sin uno de los documentos (se permite, con advertencia)
**Pantalla:** Formulario de cierre
**Precondición:** Cualquier OC lista para cerrar.
**Pasos:**
  1. Abre el formulario de cierre.
  2. Adjunta solo la Carta de Conciliación (deja sin subir la ODC cerrada).
  3. Marca "Confirmo…" y cierra.
**Resultado esperado:** Aparece la advertencia ámbar "Se cerrará sin la ODC cerrada…" pero
el botón de cierre NO se bloquea por eso (solo el checkbox de confirmación lo controla).
Referencia ya cerrada así en la demo: `OC-2025-0046`, cuyo detalle muestra la Carta pero no
la ODC.
**Estado:** ⬜ Pendiente

---

## D. Casos de error y de borde

### CP-14 · Fechas de campaña invertidas
Cubierto en **CP-02**, paso 3.

### CP-15 · Checklist incompleto bloquea el Vo.Bo.
Cubierto en **CP-05**, paso 2 (9/10 o menos deja el botón deshabilitado).

### CP-16 · Sobre-asignación de spots (barra roja)
**Pantalla:** Detalle de `OC-2025-0043`
**Precondición:** Ninguna — ya viene sobre-asignada a propósito (155 de 150 spots).
**Pasos:**
  1. Abre el detalle de `OC-2025-0043`.
**Resultado esperado:** La barra de "Distribución de spots" se ve roja, con "⚠ excedente de
5 spots".
**Estado:** ⬜ Pendiente

### CP-17 · El botón "Cerrar orden" no aparece si no se cumple la condición
**Pantalla:** Detalle de `OC-2025-0043` y `OC-2025-0044`
**Precondición:** `OC-2025-0043` tiene una OI todavía en 2.1; `OC-2025-0044` tiene sus 2 OI
en 2.1 y ni siquiera están todos los spots asignados.
**Pasos:**
  1. Abre el detalle de cada una.
**Resultado esperado:** El botón "Cerrar orden →" NO aparece en ninguna de las dos (solo
sale cuando la OC está en estado 2 y TODAS sus OI llegaron a 2.3 — el reducer además lo
hace cumplir aunque alguien lo intente sin pasar por el botón).
**Estado:** ⬜ Pendiente

### CP-18 · Campos obligatorios vacíos
**Pantalla:** Formulario de alta de OC y de OI
**Precondición:** Formularios en blanco.
**Pasos:**
  1. En "+ Nueva orden", deja vacío "No. de orden del cliente" e intenta guardar.
  2. En "+ Nueva orden interna", elige una OC pero no captures tarifa ni periodo.
**Resultado esperado:** (1) Mensaje "El no. de orden del cliente es obligatorio." bajo el
campo, no se guarda. (2) El panel "Antes de guardar" lista "Captura una tarifa por spot
mayor a 0." y "Captura al menos un día de transmisión."; el botón "Guardar orden interna"
permanece deshabilitado hasta resolver ambos.
**Estado:** ⬜ Pendiente

### CP-19 · Motivo del cambio obligatorio al modificar una comisión, y su historial
**Pantalla:** Editar `OC-2025-0043` (no congelada)
**Precondición:** OC en `orden_interna`, no congelada.
**Pasos:**
  1. Edítala y cambia el % de comisión del vendedor principal.
  2. Deja vacío "Motivo del cambio" e intenta "Guardar cambios".
  3. Ahora captura un motivo (p.ej. "Ajuste de prueba") y vuelve a guardar.
  4. Vuelve a abrir el detalle de `OC-2025-0043` y busca "Historial de cambios de
     comisión".
**Resultado esperado:** Paso 2 bloquea el guardado con "El motivo es obligatorio al cambiar
un % de comisión." (el campo es uno solo, compartido para los 3 %, ya no aparece solo junto
al de agencia). Paso 3 sí guarda. En el paso 4, el cambio aparece en el historial con el
valor anterior, el nuevo, tu usuario y el motivo capturado.
**Estado:** ⬜ Pendiente

---

## E. Congelamiento y cambio de usuario de demo

### CP-20 · Editar una orden congelada sin `admin_parametros`
**Pantalla:** Editar `OC-2025-0046` (orden_cerrada)
**Precondición:** Usuario de demo por default ("Ventas · sin permisos especiales").
**Pasos:**
  1. Abre el detalle de `OC-2025-0046`, clic en "Editar".
**Resultado esperado:** Aviso ámbar "🔒 Orden congelada: el formulario completo es de solo
lectura." **Todos** los campos están deshabilitados, incluyendo los que no son de
comisión (p.ej. "Total de spots").
**Estado:** ⬜ Pendiente

### CP-21 · Cambiar a un usuario con `admin_parametros`
**Pantalla:** Selector "DEMO" en el header + mismo formulario del CP-20
**Precondición:** Formulario del CP-20 abierto.
**Pasos:**
  1. En el selector "DEMO" del header, cambia a "Ventas · con admin_parametros" o "Admin".
**Resultado esperado:** Los 3 campos de % de comisión se habilitan; el resto del
formulario sigue de solo lectura (el permiso es solo para comisiones, no para reabrir todo
el pedido).
**Estado:** ⬜ Pendiente

---

## F. Las 4 vistas operativas

### CP-22 · Pendientes de asignar
**Pantalla:** Sidebar → "Pendientes de asignar"
**Precondición:** `OE-2025-0044A` y `OE-2025-0044B` en 2.1.
**Pasos:** Clic en "Pendientes de asignar".
**Resultado esperado:** Filtro de "Órdenes internas" en "2.1 Asignadas"; el contador del
sidebar coincide con la cantidad listada. Chip "Filtro activo" removible.
**Estado:** ⬜ Pendiente

### CP-23 · Pendientes de verificar
**Pantalla:** Sidebar → "Pendientes de verificar"
**Precondición:** `OE-2025-0043B` en 2.2.
**Pasos:** Clic en "Pendientes de verificar".
**Resultado esperado:** Filtro en "2.2 Programados"; aparece esa OI.
**Estado:** ⬜ Pendiente

### CP-24 · Listas para cerrar
**Pantalla:** Sidebar → "Listas para cerrar"
**Precondición:** `OC-2025-0045` (orden_interna, todas sus OI en 2.3).
**Pasos:** Clic en "Listas para cerrar".
**Resultado esperado:** Aparece `OC-2025-0045` (y solo OC que cumplan la condición).
**Estado:** ⬜ Pendiente

### CP-25 · Listas para facturar
**Pantalla:** Sidebar → "Listas para facturar"
**Precondición:** `OC-2025-0046` en `orden_cerrada`.
**Pasos:** Clic en "Listas para facturar".
**Resultado esperado:** Aparece `OC-2025-0046`.
**Estado:** ⬜ Pendiente

---

## G. Que cada estado se vea al menos una vez

### CP-26 · Orden cancelada
**Pantalla:** Detalle de `OC-2025-0050`
**Resultado esperado:** Badge de estado "Cancelada" (gris), sin órdenes internas, sin
botones de acción activos más que ver el detalle.
**Estado:** ⬜ Pendiente

### CP-27 · Órdenes facturadas (4.1 y 4.2 — fuera de alcance, solo lectura)
**Pantalla:** Detalle de `OC-2025-0047` (archivo plano) y `OC-2025-0048` (timbrada)
**Resultado esperado:** Ambas se ven congeladas (solo lectura total); el botón "Generar
archivo plano (4.1)" aparece deshabilitado con el tooltip "Fase 2 — fuera de alcance de
esta demo".
**Estado:** ⬜ Pendiente

### CP-28 · Orden cobrada, con historial de comisión previo a la demo
**Pantalla:** Detalle de `OC-2025-0049`
**Resultado esperado:** Badge "5 · Cobrada"; esta OC tiene vendedor principal Y secundario
(único caso en la demo) — el detalle muestra ambos. Su "Historial de cambios de comisión"
ya trae 1 entrada precargada (renegociación del % de agencia posterior al cierre). También
revisa `OC-2025-0047` y `OC-2025-0048`: cada una trae su propia entrada precargada.
**Estado:** ⬜ Pendiente

---

## H. Detalles de presentación (a simple vista)

### CP-29 · Consistencia visual
**Pantalla:** Cualquiera
**Pasos:** Recorre 3-4 pantallas distintas fijándote en:
  - Campos vacíos muestran "—", nunca "null"/"undefined"/vacío en blanco.
  - Folios (`OC-...`, `OE-...`) siempre en tipografía monoespaciada.
  - Montos siempre en formato `$X,XXX.XX` (moneda MXN), nunca un número crudo.
  - Los badges de un mismo estado usan siempre el mismo color en toda la app.
**Resultado esperado:** Sin inconsistencias visuales entre pantallas.
**Estado:** ⬜ Pendiente

---

## Datos de la demo (para no tener que buscar en vivo)

| Folio OC | Estado | Nota |
|---|---|---|
| `OC-2025-0041` | 1.1 sin Vo.Bo. | Checklist 4/10 — usar para CP-05 |
| `OC-2025-0042` | 1.2 con Vo.Bo. | Sin OI todavía — usar para CP-06 |
| `OC-2025-0043` | 2 (orden interna) | **Sobre-asignada** 155/150 (CP-16); 1 OI en 2.1, 1 en 2.2 (con override), 1 en 2.3 (con descuento) |
| `OC-2025-0044` | 2 (orden interna) | **Sub-asignada** 80/100; ambas OI en 2.1 |
| `OC-2025-0045` | 2 (orden interna) | **Exacta** 120/120, las 3 OI en 2.3 — lista para cerrar (CP-12, CP-24) |
| `OC-2025-0046` | 3 (orden_cerrada) | Congelada (CP-20/21); cerrada sin ODC (CP-13); lista para facturar (CP-25) |
| `OC-2025-0047` | 4.1 archivo plano | Congelada, solo lectura total |
| `OC-2025-0048` | 4.2 timbrada | Congelada; pago a afiliado ya "pagado" |
| `OC-2025-0049` | 5 cobrada | Único caso con vendedor secundario (CP-28) |
| `OC-2025-0050` | Cancelada | Sin ninguna OI (CP-26) |

Incidencias precargadas: `in1` (descuento, en `OE-2025-0043C`), `in2` (bonificación, en
`OE-2025-0045B`), `in3` (descuento, en `OE-2025-0046B`).

Usuarios de demo (selector "DEMO" en el header): "Ventas · sin permisos especiales"
(default), "Ventas · con admin_parametros", "Admin".

---

## Errores conocidos (no corregidos — o corregidos y documentados aquí para que quede
registro)

- **`oiVentanaTipica()` usa la primera fila capturada, no la cronológicamente más
  temprana.** Sin impacto visible hoy porque nadie captura los días fuera de orden en la
  práctica. (`state/selectors.ts`)
- **`totalesOC()` no redondea a centavos internamente** — el redondeo visual solo ocurre
  al formatear con `fmtMonto()`. Sin impacto en pantalla. (`state/selectors.ts`)
- **Ningún campo de formulario tiene `<label htmlFor>` ni `aria-label`** — son
  `<div className="fl">` seguidos del input. Sin impacto visual; si alguien navega solo con
  teclado/lector de pantalla, no anunciaría qué campo es cuál. (Todos los forms de F1)
- **La línea "Tarifa de referencia" se omite por completo cuando no hay una vigente para la
  combinación plaza/tipo de señal/duración**, en vez de mostrar un "—" explícito. No rompe
  nada, solo desaparece la línea.
- **"Anunciante sin contratos/marcas vigentes"** es una rama de código real pero
  inalcanzable con los datos actuales de la demo (todos los anunciantes tienen ≥1 contrato
  vigente y ≥2 marcas, a propósito). Probada a nivel de función pura, no a nivel de pantalla.
- **La autoexclusión de una OI al editarla** (que sus propios spots no cuenten como "ya
  asignados a otras OI") no se puede probar en esta demo porque **no existe pantalla de
  edición de una OI ya creada** (solo alta). Si se agrega edición de OI más adelante, este
  es el primer caso a probar.

### Corregidos durante las pruebas (ya no aplican, se documentan como referencia)
- Una OC congelada ahora bloquea **todo** el formulario, no solo los 3 % de comisión.
- El campo "Motivo del cambio" ahora es uno solo, compartido, y **obligatorio** si cambias
  cualquiera de los 3 % de comisión al editar.
- `cerrarOC()` y `actualizarOC()` ahora hacen cumplir sus reglas de negocio (sin OI, OI no
  reconciliada, comisión de una OC congelada sin permiso) directamente en el reducer, no
  solo ocultando el botón.
- El historial de cambios de comisión ahora SÍ se muestra: nueva sección "Historial de
  cambios de comisión" en el detalle de la OC (mismo patrón que `ContratoDetailPanel` en
  F0) — ver CP-19 y CP-28.
