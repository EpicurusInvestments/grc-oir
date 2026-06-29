---
name: revision-modulo
description: >
  Checklist de "Definición de Terminado" para revisar un módulo del Sistema GRC-OIR
  antes de darlo por cerrado o abrir su Pull Request. Úsala SIEMPRE que el equipo diga
  que un módulo "ya está", "lo terminé", "voy a hacer el PR", "revisa el módulo" o al
  cerrar cualquier fase/entidad antes de pasar a la siguiente. Verifica capas, fidelidad
  a la spec BD v2, seguridad, permisos por campo, auditoría, pruebas, migraciones y
  documentación viva actualizada.
---

# Skill: revision-modulo

Recorrer el módulo contra esta lista y reportar cada punto como **OK / Falta / N/A**,
señalando exactamente qué corregir (archivo/línea cuando se pueda). No marcar
"terminado" si algo crítico (seguridad, auditoría, migraciones, documentación) falta.

## Fidelidad a la especificación BD v2
- [ ] Nombres de entidades y campos EXACTOS a la spec (snake_case en español).
- [ ] Estados con los valores exactos y CHECK constraints nombrados.
- [ ] Campos "Calculado" implementados con la fórmula de la spec, solo escribibles por
      el servicio (rechazados si vienen en el request).
- [ ] Campos "Heredado/Derivado" se copian de su origen según la spec.
- [ ] Transiciones de estado validadas (máquina de estados); reglas de cierre clave
      respetadas (p.ej. `orden_cerrada` solo con todas las OE reconciliadas).

## Arquitectura y capas
- [ ] `router` sin lógica ni SQL; `service` con reglas y transacciones; `repository`
      único acceso a BD; respuestas con schemas `XxxRead` (nunca entidades crudas).
- [ ] Frontend espeja la estructura; usa los componentes compartidos del patrón
      (lista + panel detalle, tags de campo, badges de estado).

## Seguridad (no negociable)
- [ ] Cada endpoint con autenticación + `requiere_permiso(...)` según la matriz RBAC.
- [ ] Área resuelta del token, nunca del cliente.
- [ ] Campos sensibles: verificación de permiso por campo ANTES de modificar.
- [ ] Entradas validadas; sin PII/datos fiscales en logs; secretos solo en entorno.
- [ ] Sin pantallas/endpoints para actores externos.

## Auditoría
- [ ] Cambios a parámetros sensibles registran en `LogCambioParametro` (usuario, fecha,
      valor anterior, valor nuevo, ip).

## Datos / migraciones
- [ ] Esquema solo por migraciones Alembic revisadas (downgrade correcto).
- [ ] NVARCHAR para textos, DECIMAL para montos, UNIQUEIDENTIFIER para PKs.
- [ ] FKs explícitas + índices en FKs y columnas de bandejas/filtros.

## Integraciones (si aplica)
- [ ] Todo formato externo pasa por `app/integrations/` (port/adapter/mapper).
- [ ] El sistema NO timbra; SAP solo como referencia capturada.
- [ ] Cargas de archivo con validación y errores claros; idempotencia donde aplica.

## Pruebas y calidad
- [ ] Backend: pruebas de casos felices, validaciones y transiciones de estado; `mypy`
      y lint sin errores nuevos.
- [ ] Frontend: `tsc --noEmit`, lint y pruebas; sin `any` injustificado; estados de
      carga/error/vacío manejados.

## Documentación viva (bloqueante)
- [ ] `docs/API-CONTRACT.md` actualizado con los endpoints del módulo.
- [ ] `docs/modulos/<modulo>.md` refleja el estado real (entidades, estados, pantallas).
- [ ] Decisiones técnicas registradas como ADR en `docs/arquitectura.md`.
- [ ] Términos nuevos en `docs/glosario.md`.

## Pasos finales
- [ ] Router registrado en `app/main.py`; rutas y menú (por área) en el front.
- [ ] PR pequeño, enfocado, con descripción clara y la documentación INCLUIDA.

## Salida esperada
Resumen con: qué está OK, qué falta y un veredicto: **listo para PR** o
**bloqueado por: ...**.
