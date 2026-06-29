# CLAUDE.md — Frontend (React + TypeScript)

> Reglas locales del frontend. Hereda y no contradice el `CLAUDE.md` raíz.
> El patrón de pantallas viene de la sección 7 de la propuesta Pointwise.

## Stack

- **React + TypeScript** (`strict: true`). Bundler: **Vite**.
- Estado de servidor: **TanStack Query**.
- Formularios + validación: **React Hook Form + Zod**.
- Librería de componentes: **PrimeReact** — soporta bien tabla densa + panel
  lateral + formularios largos por secciones.
- Tipografía: **IBM Plex Sans** (texto general) e **IBM Plex Mono** (folios, claves,
  RFC, datos técnicos). <!-- Definido en la propuesta; da identidad consistente. -->
- Corre en contenedor Docker con hot-reload (ver `docker-compose.yml`).

## Estructura por módulo (espeja al backend)

```
src/modules/<modulo>/
├── types.ts        # tipos alineados a los DTOs del backend (ideal: generados de OpenAPI)
├── api.ts          # llamadas a /api/v1/<modulo>
├── hooks.ts        # data fetching (queries/mutations)
├── components/     # piezas de UI del módulo
└── pages/          # pantallas registradas en el router
```

Lo reutilizable va a `src/shared/` — en particular los componentes del patrón general
de pantalla (abajo), que se construyen UNA vez y se usan en todos los módulos.

## Patrón general de pantalla (de la propuesta — aplicar consistentemente)

| Zona | Contenido |
|---|---|
| **Header** | Logo · fase/módulo actual · buscador global · usuario activo |
| **Sidebar** | Menú lateral con módulos agrupados por área; indicadores de pendientes |
| **Cat-header** | Título del módulo, subtítulo, acciones principales (Nuevo, Exportar) |
| **Toolbar** | Búsqueda local, filtros rápidos (pills), filtros avanzados, contador de resultados |
| **Lista + detalle** | Tabla a la izquierda; **panel de detalle a la derecha (~480px)** al seleccionar un renglón — edición rápida sin perder el contexto de la lista |
| **Forms full-screen** | Para capturas complejas (OrdenCliente, preparación de factura): pantalla completa con secciones, navegación por anclas y guardado por etapa |

### Convenciones visuales (de la propuesta)

- **Color por fase**: F0 morado · F1 teal · F2 azul · F3 ámbar · F4 gris · F5 rojo.
  Centralizar en el tema, no hardcodear por pantalla.
- **Tags de campo**: «Catálogo», «Heredado», «Calculado», «Derivado», «Audit log»,
  «Timbrado» — el usuario siempre sabe el origen del dato. Componente compartido.
  <!-- Importante: los campos "Calculado" se muestran de solo lectura; los "Heredado"
       indican que el valor viene de la OrdenCliente u otra entidad padre. -->
- **Campos obligatorios** con asterisco rojo.
- Iconografía sobria; preferir tags sobre íconos cuando el significado es operativo.
- Exportación a Excel/CSV disponible en todas las listas y reportes.

## Reglas

- TypeScript estricto; nada de `any` sin justificación escrita.
- Nombres de campos consistentes con la API (que sigue la spec BD v2); idealmente tipos
  generados desde OpenAPI con **openapi-typescript**.
- Estados (estatus_orden, estatus_cobro, etc.) se muestran con badges legibles y sus
  valores son los EXACTOS de la spec; el front nunca inventa estados.
- El RBAC del front (mostrar/ocultar acciones según área) es solo UX; el backend valida
  siempre. Los campos con permiso a nivel de campo se muestran deshabilitados si el
  usuario no puede editarlos.
- Manejo explícito de estados de carga / error / vacío en cada pantalla.
- Textos de UI en español (es-MX); moneda MXN; fechas formato local.
- Accesibilidad básica: labels en inputs, foco visible, navegación por teclado.

## Calidad

- `tsc --noEmit`, lint **eslint**, pruebas **vitest**.
