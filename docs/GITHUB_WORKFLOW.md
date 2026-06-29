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

## Versionado y entregas

- [[POR LLENAR: esquema de tags/releases por entrega (E1..E4), changelog]]
