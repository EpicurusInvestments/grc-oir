# Fase 0 — Catálogos · Índice de módulos

> Fase base del sistema (Entrega 1, junto con F1). 15 entidades de catálogo + las
> constantes del sistema. Color de fase: **morado**. Toda la captura es interna; los
> actores externos no acceden. Referencias: especificación BD v2 y la pantalla aprobada
> `docs/referencias/pantallas/Fase_0_-_Catalogos.html`.

## Por qué se divide en módulos

La pantalla de F0 es un solo "explorador de catálogos" (sidebar con 9 grupos + panel
lista/detalle), pero construirla de un golpe haría difícil probar. Se parte en **6
módulos** agrupando catálogos por afinidad (dependencias de datos y reglas comunes),
de menor a mayor complejidad, de modo que cada uno se pueda programar, probar y validar
por separado. El orden respeta las dependencias: lo que otros catálogos referencian se
construye primero.

## Lista de módulos de F0 (orden de desarrollo)

| # | Módulo (archivo .md) | Entidades que cubre | Por qué juntas |
|---|---|---|---|
| 0 | `f0-00-fundamentos-catalogos.md` | (transversal, sin entidad propia) | Base técnica compartida por todos los catálogos: layout del explorador, patrón lista+detalle, toolbar/filtros, badges activo/inactivo, endpoints CRUD genéricos, RBAC de catálogos. Se hace primero para no repetirlo. |
| 1 | `f0-01-catalogos-operativos.md` | Plaza, Afiliado, Estacion | Núcleo operativo de la transmisión; encadenados (Estacion → Afiliado → Plaza con inferencia automática). Sin dependencias externas. |
| 2 | `f0-02-tarifas.md` | TarifaPlaza | Depende de Plaza. Incluye campo calculado `tarifa_neta` y vigencias; conviene aislarlo. |
| 3 | `f0-03-catalogos-comerciales.md` | Agencia, Anunciante, Marca, Contrato | Cadena comercial encadenada (Agencia → Anunciante → Marca/Contrato). Incluye **parámetros sensibles** (% comisión, días de crédito) con permiso por campo + audit log. |
| 4 | `f0-04-catalogos-facturacion-finanzas.md` | EmpresaFacturadora, Vendedor, Categoria, MetodoPago, CuentaContable, LayoutFactura | Catálogos de apoyo a facturación/finanzas; CRUD simple. Vendedor incluye % comisión (sensible). |
| 5 | `f0-05-constantes-sistema.md` | (catálogos SAT/timbrador; entidad de configuración) | Pantalla "Constantes del sistema" (solo lectura para operadores): TipoComprobante, Serie, RegimenFiscal, ClaveProdServ, ClaveUnidad, UsoCFDI, FormaPago, MetodoPago, MonedaSAT. Las consume F2. |

> Nota: **Usuario** (entidad de F0 en la spec) se administra desde la pantalla de F5
> ("Usuarios y áreas"). En F0 se crea solo el modelo/seed mínimo necesario para el RBAC;
> la pantalla de administración de usuarios pertenece al módulo de F5. Se documenta en
> `f0-04` el modelo, y la pantalla en F5.

## Definición de "Entrega 1" respecto a F0

F0 debe quedar **completa** (los 6 módulos) antes de cerrar la Entrega 1, porque F1
(Órdenes) consume prácticamente todos estos catálogos. Orden sugerido: 0 → 1 → 2 → 3 →
4 → 5. Los módulos 1 y 4 pueden avanzar en paralelo si hay dos personas, pero 0 va
siempre primero.

## Decisiones / pendientes de F0 (CONFIRMADAS)

- **Edición de catálogos:** por ahora **solo Admin (IT)** puede editar todos los
  catálogos de F0. En una versión posterior, Ventas podrá capturar/editar
  afiliados/estaciones (ver F0-01).
- **Constantes del sistema:** edición solo Admin; **sin seed automático** — la carga inicial
  es manual y la **carga masiva CSV** se usará cuando exista la lista oficial del SAT. Ver `f0-05`.
- **Marca:** no tiene pantalla propia; **se gestiona anidada dentro de Anunciante**. Ver `f0-03`.
- **Paginación:** las listas usan **paginación por página** (no scroll infinito).
- **Plaza de la estación (Opción A):** la estación **hereda la plaza de su afiliado**;
  un afiliado opera en una sola plaza por ahora. Ver F0-01 y ADR-005.
- **Campo `venta_directa_carmen_aristegui_cdmx`:** se **omite** deliberadamente respecto
  a la spec BD v2. Registrado como desviación en `docs/arquitectura.md` (ADR-006).
