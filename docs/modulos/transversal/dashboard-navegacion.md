# Módulo transversal — Dashboard (Home) y navegación global entre fases

> Pieza **solo frontend** (no toca backend ni BD). Provee el Home real del sistema y la
> navegación entre las 6 fases (F0–F5). Ver ADR-026 en `docs/arquitectura.md`.

## Alcance

- **Dashboard (`/`)**: malla responsiva de hasta 6 tarjetas, una por fase, con
  ilustración, código+nombre, descripción de una línea y acento de color por fase.
  Desde F4-01 (Tanda 1 de Reportes) las **6 fases (F0–F5) están `enabled`**. La fuente
  única de qué está activa es `enabled` en `phaseRegistry.ts` — esta lista se actualiza
  cuando ese arreglo cambia.
- **Visibilidad por área (`visibleParaArea`, desde F4-01):** una fase puede, además,
  declarar `visibleParaArea?: (area: string) => boolean` — si el área actual no
  califica, su tarjeta/entrada de menú se **oculta por completo** (no "Próximamente":
  directamente no aparece). Sin esta función (todas las fases salvo F4 hoy), el
  comportamiento no cambia: visible para cualquiera con sesión. F4 la usa porque es la
  primera fase con vistas tan restringidas (Estado de resultados es exclusivo de
  Dirección) que vale la pena no mostrar la tarjeta a quien de todas formas no podría
  ver nada adentro — ver `docs/modulos/f4-reportes/f4-reportes.md`.
- **Navegación global (drawer)**: menú lateral deslizante disponible desde cualquier
  pantalla que use `AppHeader` (hamburguesa arriba a la izquierda). Contiene acceso a
  Inicio y a las 6 fases. Cierra con overlay, tecla Escape y botón de cerrar.

## Rutas

| Ruta | Pantalla |
|---|---|
| `/` | `DashboardPage` (Home) |
| `/catalogos` | `CatalogosExplorerPage` (F0, antes en `/`) |

## Archivos

| Archivo | Rol |
|---|---|
| `src/shared/phases/phaseRegistry.ts` | **Fuente única** de las 6 fases (código, nombre, descripción, acento, imágenes, ruta, `enabled`). |
| `src/modules/dashboard/pages/DashboardPage.tsx` | Pantalla Home; itera el registro. |
| `src/modules/dashboard/components/PhaseCard.tsx` | Tarjeta de fase (activa vs. "Próximamente"). |
| `src/modules/dashboard/assets/*.{webp,png}` | Ilustraciones optimizadas. |
| `src/shared/ui/AppNavDrawer.tsx` | Drawer de navegación global (compartido). |
| `src/shared/ui/AppHeader.tsx` | Header + botón hamburguesa que abre el drawer. |
| `src/shared/ui/theme.css` | Estilos del dashboard, drawer, acentos por fase y animaciones. |
| `src/app/router.tsx` | Declara `/` y `/catalogos`. |

## Cómo activar una fase futura (trivial, un solo lugar)

En `phaseRegistry.ts`, en la entrada de la fase:

1. `enabled: true`
2. `route: "/<ruta-de-la-fase>"`
3. Montar la ruta en `src/app/router.tsx`.

La tarjeta del Dashboard y el item del menú lateral se "encienden" solos (pasan de
"Próximamente" a navegables). No se edita ni el Dashboard ni el drawer.

## Color por fase

Reutiliza la paleta de `theme.css` (convención de la propuesta): F0 morado · F1 teal ·
F2 azul · F3 ámbar · F4 gris · F5 rojo. Cada tarjeta/item declara la clase `.pc-accent-*`
y consume `--acc` / `--acc-bg` / `--acc-text`.

## Estado "Próximamente" vs. activa

| | Activa | Próximamente (ninguna hoy, F0-F5 ya construidas) |
|---|---|---|
| Interacción | `<button>`, navega a su ruta | `<div aria-disabled>`, sin acción |
| Opacidad / imagen | 100% / a color | ~55% / escala de grises |
| Hover | Elevación + sombra + zoom de imagen | Sin efecto |
| Badge | — | Gris "Próximamente" |

El mecanismo sigue existiendo (no se eliminó código): la próxima fase nueva que se
agregue al registro con `enabled: false` volverá a mostrarse así automáticamente.

Animaciones sutiles (fade-in escalonado por índice; hover con elevación y zoom) con
respeto a `prefers-reduced-motion`.

## Optimización de imágenes

Origen: 6 PNG (~1–1.3 MB c/u, 6.7 MB total). Proceso (Pillow): recorte del fondo blanco,
cuadrado a lienzo, redimensión a 256px (≈2× del tamaño mostrado ~112px), export **WebP
q82** (principal) + **PNG optimizado** (fallback vía `<picture>`).

| Fase | WebP | PNG fallback |
|---|---|---|
| Catálogos | 5.3 KB | 53.5 KB |
| Órdenes | 5.2 KB | 56.6 KB |
| Facturación | 4.4 KB | 55.0 KB |
| Cobranza y Pagos | 6.2 KB | 64.3 KB |
| Reportes | 5.2 KB | 54.1 KB |
| Seguridad | 6.4 KB | 65.8 KB |
| **Total** | **32.6 KB** | **349.3 KB** |

## Calidad

`tsc --noEmit`, `eslint` y `vitest` en verde; `vite build` empaqueta los assets con hash.
Prueba: `src/modules/dashboard/__tests__/DashboardPage.test.tsx` (6 tarjetas; deriva
navegables vs. "Próximamente" de `phaseRegistry.enabled` en vivo, sin hardcodear cuántas
fases están activas — no hay que tocar la prueba cada vez que se activa una fase nueva).
