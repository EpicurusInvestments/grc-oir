# GITHUB_WORKFLOW — Sistema GRC-OIR

> Repositorio oficial: https://github.com/EpicurusInvestments/grc-oir.git

> Cómo trabajamos con Git/GitHub en este proyecto. Documento VIVO.

## Ramas

- `main` — protegida. Solo recibe merges por Pull Request aprobado. Siempre desplegable.
- `feature/f<fase>-<modulo>-<descripcion>` — una rama por tarea.
  Ejemplos: `feature/f0-catalogos-agencia`, `feature/f1-ordenes-derivacion-oe`.
- `fix/<modulo>-<descripcion>` — correcciones.
- [[POR LLENAR: ¿rama develop/qa intermedia? ¿ramas de release por entrega?]]

## Commits (Conventional Commits, en español)

Formato: `tipo(modulo): descripción breve en infinitivo`
- `feat(ordenes): derivar OrdenEstacion desde OrdenCliente`
- `fix(cobranza): corregir cálculo de importe_pendiente_cobro`
- `docs(api): documentar endpoints de catálogo Agencia`
- `chore(docker): actualizar driver ODBC a 18.x`
Tipos permitidos: feat, fix, docs, test, refactor, chore, perf.

## Pull Requests

- Un PR por tarea, pequeño y enfocado a UNA fase/módulo.
- El PR incluye SIEMPRE: código + pruebas + **documentación actualizada** (`docs/`).
  Un PR sin su documentación no se aprueba (regla de oro 7 del CLAUDE.md).
- Descripción del PR: qué cambia, por qué, cómo probarlo, capturas si hay UI.
- Revisores requeridos: [[POR LLENAR: cuántos y quiénes]].
- El PR debe pasar: pruebas, lint, mypy/tsc [[POR LLENAR: pipeline CI definitivo]].
  En el backend (`.github/workflows/backend.yml`, ADR-255), Ruff y Pytest SÍ bloquean el
  pipeline; Mypy sigue en `continue-on-error` (335 avisos preexistentes, limpieza
  pendiente — ver `docs/arquitectura.md`, ADR-255). El backend corre CI con la MISMA
  versión de Python que producción (`backend/.python-version` = `3.12`, fijada desde
  ADR-262 — antes `uv` resolvía lo que encontrara en el runner, una versión distinta a
  la del `Dockerfile`). Los archivos de referencia de sistemas externos
  (`docs/referencias/*.txt`) van con `eol=crlf` forzado en `.gitattributes` (ADR-262) —
  necesitan ese final de línea exacto para las pruebas que los comparan byte a byte,
  sin importar el `core.autocrlf` de quien clona.

## Versionado y entregas

- [[POR LLENAR: esquema de tags/releases por entrega (E1..E4), changelog]]
