---
name: frontend-react
description: >
  Convenciones para implementar pantallas del Sistema GRC-OIR con React y TypeScript.
  Úsala SIEMPRE que se vaya a escribir o modificar código de frontend: pantallas,
  componentes, formularios, tablas, bandejas, tableros, panel de detalle, llamadas a la
  API, tipos, hooks o visibilidad por área/rol. Aplica el patrón de pantalla definido en
  la propuesta (lista + panel de detalle, forms full-screen, tags de campo, color por
  fase) y el tipado estricto alineado a la API.
---

# Skill: frontend-react

Cómo construir pantallas consistentes con el patrón de la propuesta Pointwise (sección 7).

## Estructura del módulo (espeja al backend)

```
src/modules/<modulo>/
├── types.ts        # tipos alineados a los DTOs del backend (ideal: generados de OpenAPI)
├── api.ts          # llamadas a /api/v1/<modulo>
├── hooks.ts        # queries / mutations
├── components/
└── pages/
```

Lo reutilizable va a `src/shared/ui` y se construye UNA vez: layout (header + sidebar),
tabla con toolbar, **panel de detalle (~480px)**, badges de estado, **tags de campo**,
modal de confirmación, exportar a Excel.

## Patrón de pantalla (aplicarlo siempre)

1. **Lista + detalle**: tabla a la izquierda (búsqueda local, filtros rápidos tipo
   pills, filtros avanzados, contador de resultados); al seleccionar un renglón se abre
   el panel de detalle a la derecha (~480px) para ver/editar sin perder el contexto.
   Es el patrón por defecto de catálogos y bandejas.
2. **Form full-screen**: para capturas complejas (OrdenCliente, preparación de
   FacturaCliente): pantalla completa con secciones (identificación, comercial,
   programación, financiera...), navegación por anclas y guardado por etapa.
3. **Bandejas**: listas operativas con filtros por estatus (p.ej. bandeja de órdenes:
   borrador │ asignada │ verificada │ cerrada; bandeja de facturas por preparar:
   órdenes en `orden_cerrada` sin factura). Acciones por lote donde la propuesta lo pide.
4. **Tableros**: dashboard operativo (F1) y de Dirección (F4) con KPIs y filtros.

## Convenciones visuales (de la propuesta)

- **Color por fase**: F0 morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo —
  centralizado en el tema.
- **Tags de campo**: «Catálogo», «Heredado», «Calculado», «Derivado», «Audit log»,
  «Timbrado». Los campos *Calculado* se muestran de solo lectura; los *Heredado*
  indican el origen (p.ej. valores que vienen de la OrdenCliente).
- **Campos obligatorios** con asterisco rojo.
- Tipografía IBM Plex Sans; IBM Plex Mono para folios, RFC, claves y datos técnicos.
- Estados con badges legibles; los valores son los EXACTOS de la spec BD v2 (el front
  nunca inventa ni renombra estados).
- Toda lista/reporte ofrece **exportación a Excel/CSV**.

## Reglas

- TypeScript estricto; nada de `any` sin justificación escrita.
- Tipos idealmente generados desde OpenAPI (`[[POR LLENAR: openapi-typescript]]`) para
  no desincronizarse del backend.
- RBAC en el front = solo UX (mostrar/ocultar/deshabilitar según área); el backend
  valida siempre. Campos con permiso a nivel de campo → deshabilitados si el usuario
  no puede editarlos, con tag «Audit log» visible.
- Manejo explícito de carga / error / vacío en cada pantalla.
- Textos es-MX; moneda MXN; los actores externos NO tienen pantallas (no crear portales).
- Invalida queries tras cada mutación; deshabilita submit mientras envía; muestra
  errores del servidor (incluido 409 por transición de estado inválida, con mensaje claro).

## Cierre

`tsc --noEmit`, lint y pruebas pasan; actualizar la ficha del módulo en
`docs/modulos/` (skill `documentacion-proyecto`); luego `revision-modulo`.
