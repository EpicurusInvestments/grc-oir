---
name: nuevo-modulo
description: >
  Crea el ANDAMIAJE (esqueleto) de un módulo nuevo del Sistema GRC-OIR, en backend
  (Python/FastAPI) y frontend (React/TypeScript), siguiendo las convenciones del
  proyecto y la especificación de BD v2. Úsala SIEMPRE que el equipo pida "agregar un
  módulo", "empezar la fase X", "crear la sección/pantalla de Y" o iniciar cualquier
  parte nueva (catálogos, usuarios, órdenes, facturación, cobranza, pagos, requisiciones,
  conciliación, reportes, seguridad). Genera estructura y plantillas con TODOs, NO la
  lógica de negocio: su propósito es avanzar ordenado, por partes.
---

# Skill: nuevo-modulo

Genera el esqueleto de un módulo, parejo en backend y frontend, listo para que el
equipo (con las skills `backend-fastapi` y `frontend-react`) implemente la lógica
después. **No implementa reglas de negocio.**

## Antes de generar nada

1. Ubica el módulo en el **mapa fases → módulos** del `CLAUDE.md` raíz (sección 4) y
   confirma su nombre en `snake_case` (igual en back y front).
2. Identifica las **entidades de la especificación BD v2** que cubre el módulo (los
   nombres de entidades, campos y estados vienen de ahí; NO se inventan ni renombran).
3. Lee `docs/modulos/<modulo>.md`; si no existe, créalo desde
   `docs/modulos/_plantilla.md` pre-llenando lo que la spec ya dice (entidades, estados,
   relaciones) y marca `[[POR LLENAR]]` lo que falte. Pide al equipo completarlo.
4. **Presenta un plan corto** (lista de archivos a crear) y espera el visto bueno.

## Qué crea

### Backend — `backend/app/modules/<modulo>/`

Archivos con plantillas mínimas y `# TODO` claros:

- `__init__.py`
- `models.py` — una clase SQLAlchemy por entidad de la spec, con: PK
  `UNIQUEIDENTIFIER` (`<entidad>_id`), columnas `created_at`/`updated_at`, y
  `# TODO(equipo)` por cada campo de la spec (nombre y tipo exactos como referencia
  en comentario). Estados como `VARCHAR` + comentario del CHECK pendiente.
- `schemas.py` — `XxxCreate`, `XxxUpdate`, `XxxRead` (Pydantic) con los campos como
  `# TODO`. Los campos de origen "Calculado" SOLO van en `XxxRead`.
- `enums.py` — un `StrEnum` por campo de estado, con los valores EXACTOS de la spec.
- `repository.py` — firmas de `get`, `list`, `create`, `update`, `delete` con `# TODO`.
- `service.py` — clase servicio con métodos espejo + esqueleto de la **máquina de
  estados** (diccionario de transiciones permitidas con `# TODO: validar con equipo`).
- `router.py` — `APIRouter` con endpoints CRUD declarados, cada uno con
  `Depends(requiere_permiso("<modulo>:<accion>"))` (nombre de permiso según la matriz
  RBAC; si hay duda, `# TODO`), delegando al servicio. Sin lógica.
- `tests/test_<modulo>.py` con esqueleto.

### Frontend — `frontend/src/modules/<modulo>/`

- `types.ts` — tipos espejo de los schemas (con `// TODO`; ideal generarlos de OpenAPI).
- `api.ts` — funciones CRUD apuntando a `/api/v1/<modulo>`.
- `hooks.ts` — esqueleto de queries/mutations.
- `components/index.ts` vacío.
- `pages/<Modulo>ListPage.tsx` — esqueleto del patrón **lista + panel de detalle
  (~480px)** con toolbar (búsqueda, filtros pills, contador) según la propuesta.
- `pages/<Modulo>FormPage.tsx` — esqueleto de formulario; si la entidad es compleja
  (p.ej. OrdenCliente, FacturaCliente) usar **full-screen con secciones**; si es un
  catálogo simple, panel lateral.

## Después de crear (NO hacerlo en automático, listarlo como pendiente)

- Registrar router en `app/main.py` y rutas/menú (con su área RBAC) en el front.
- Crear la migración con la skill `migraciones-sqlserver`.
- Completar `docs/modulos/<modulo>.md` y registrar endpoints previstos en
  `docs/API-CONTRACT.md` (skill `documentacion-proyecto`).

## Reglas

- **Cero lógica de negocio**: solo esqueleto y TODOs.
- Nombres de entidades, campos y valores de estado = los de la spec BD v2, sin cambios.
- Respetar la regla de espejo back/front y la estructura del `CLAUDE.md` raíz.
- Todo endpoint nace con su dependencia de permiso.
- Al terminar, entregar al equipo la lista de pasos manuales pendientes.
