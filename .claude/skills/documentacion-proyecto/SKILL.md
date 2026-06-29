---
name: documentacion-proyecto
description: >
  Mantiene actualizada la documentación viva del Sistema GRC-OIR en docs/ (arquitectura,
  API-CONTRACT, GITHUB_WORKFLOW, glosario, fichas de módulo). Úsala SIEMPRE al terminar
  cualquier tarea de desarrollo (endpoint nuevo o modificado, entidad o migración,
  pantalla, integración, decisión técnica), antes de abrir un PR, o cuando el equipo
  pida "actualiza la documentación", "documenta esto" o "deja registro". Regla del
  proyecto: un cambio sin su documentación actualizada NO está terminado; el código y
  su documentación viajan en el mismo PR.
---

# Skill: documentacion-proyecto

La documentación de este proyecto es **viva**: se actualiza a la par del código, no al
final. Esta skill define QUÉ documento tocar según el tipo de cambio y CÓMO escribirlo.

## Mapa: tipo de cambio → documento a actualizar

| Si el cambio es... | Actualiza... |
|---|---|
| Endpoint nuevo, modificado o eliminado | `docs/API-CONTRACT.md` (usar la plantilla del propio documento: permiso, reglas, ejemplos, errores) |
| Entidad nueva, campo nuevo, migración | `docs/modulos/<modulo>.md` (sección de entidades y estados) |
| Cambio de estados o transiciones | `docs/modulos/<modulo>.md` + nota en `docs/API-CONTRACT.md` si afecta endpoints |
| Pantalla nueva o rediseñada | `docs/modulos/<modulo>.md` (sección pantallas: qué muestra, qué roles la usan) |
| Decisión técnica o de arquitectura | `docs/arquitectura.md` como nuevo **ADR** (contexto → decisión → consecuencias), numerado consecutivo |
| Integración nueva o cambiada (timbrador, NOI, bancos...) | `docs/arquitectura.md` (ADR si hubo decisión) + `docs/modulos/<modulo>.md` |
| Término de negocio nuevo o aclarado | `docs/glosario.md` |
| Cambio al flujo de trabajo Git/PRs | `docs/GITHUB_WORKFLOW.md` |
| Cambio a reglas globales del proyecto | `CLAUDE.md` raíz (¡primero!) y los `CLAUDE.md` locales si aplica |

## Cómo escribir

- **En español**, claro y breve. La documentación es para todo el equipo, incluidos
  perfiles no técnicos del lado funcional: explica el "por qué", no solo el "qué".
- No dupliques la fuente técnica: el OpenAPI de FastAPI ya documenta firmas exactas;
  `API-CONTRACT.md` agrega negocio, permisos y ejemplos. La spec BD v2 ya define campos;
  la ficha del módulo agrega decisiones, pendientes y lo aprendido al implementar.
- Marca lo no resuelto como `[[POR LLENAR: ...]]` — nunca lo inventes.
- Si detectas que el código contradice un documento (o a la spec v2), NO "corrijas" en
  silencio: repórtalo al equipo como inconsistencia a resolver.

## Checklist al cerrar una tarea (antes del PR)

1. ¿Toqué endpoints? → `API-CONTRACT.md` actualizado.
2. ¿Toqué modelo de datos? → ficha del módulo actualizada (y migración referida).
3. ¿Tomé una decisión técnica con alternativas? → ADR nuevo en `arquitectura.md`.
4. ¿Apareció vocabulario nuevo? → `glosario.md`.
5. ¿La ficha `docs/modulos/<modulo>.md` refleja el estado real del módulo?
6. Incluir los archivos de `docs/` modificados EN EL MISMO PR que el código.
