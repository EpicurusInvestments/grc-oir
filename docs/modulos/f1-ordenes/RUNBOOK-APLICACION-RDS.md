# Runbook — aplicar F1 a RDS (una página)

> Detalle completo: `INFORME-MIGRACION-RDS-F1.md`. Esto es solo la secuencia de acción.

## 1. Verificar, antes de aplicar

```powershell
cd backend
uv run alembic heads      # local, sin conexión
uv run alembic current    # RDS, SOLO LECTURA
```

| Comando | Resultado | Significa |
|---|---|---|
| `heads` | `73fa97f9e718` (uno solo) | OK, sigue. Si hay más de uno o es otro: **detente**, hay una revisión huérfana en el repo. |
| `current` | `b6d9f2a4c817` | ✅ Correcto — RDS en el head de F0, nunca vio F1. Sigue. |
| `current` | cualquier revisión **anterior** a `b6d9f2a4c817` | 🛑 **Párale.** RDS no está donde el informe asume — no apliques, investiga primero. |
| `current` | `73fa97f9e718` | 🚨 **Alarma.** Alguien ya aplicó esta migración. No la vuelvas a aplicar. Avisa al equipo de inmediato. |
| `current` | error de conexión | Revisa `.env` (host/puerto/credenciales) y que la instancia RDS esté accesible desde tu red — no es un problema de Alembic. |

Luego en SSMS (solo lectura): la consulta de `usuario` (debe existir `dev.admin`) y la de conteo de catálogos (todas ≥ 1) — están en el mensaje donde te las di.

Y en paralelo: pide a TI el snapshot de `GRC-OIR` y el reporte del incidente de credencial (texto ya redactado en la sección 13 del informe), y avisa al equipo que vas a aplicar.

## 2. Aplicar

```powershell
uv run alembic upgrade head
```
Esperado: log terminando en `Running upgrade b6d9f2a4c817 -> 73fa97f9e718`, sin errores.

**Si falla a medias:**
- **Qué esperar:** transacción única (`BEGIN TRANSACTION`/`COMMIT`) — SQL Server revierte sola, no debería quedar nada a medio crear.
- **Cómo confirmar que revirtió:** `alembic current` debe seguir en `b6d9f2a4c817`. Corre la consulta 1 de `VERIFICACION-POST-APLICACION-RDS-F1.sql` — debe devolver **0 filas** (ninguna de las 6 tablas de F1 debe existir).
- **Si ambas coinciden** (sigue en `b6d9f2a4c817` y 0 tablas): revirtió limpio. Investiga la causa en local, con calma, antes de reintentar.
- **Cuándo restaurar el snapshot en vez de seguir investigando:** si `alembic current`/la consulta 1 NO coinciden entre sí (estado inconsistente), o si la consulta 4 (F0 sin tocar) deja de devolver 0 filas. Ahí no se depura en caliente sobre la base compartida — se restaura primero.

Después: las 8 consultas de `VERIFICACION-POST-APLICACION-RDS-F1.sql`, cada una contra su resultado esperado.

## 3. Cambiar a modo RDS

```powershell
cd backend
Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
uv run python -m scripts.verificar_config_bd     # debe decir "APUNTA A SQL SERVER (RDS)"
uv run uvicorn app.main:app --reload --port 8010
```
En `frontend/.env`: `VITE_DEV_USER=dev.admin`, `VITE_DEV_AREA=admin` — `dev.admin` es el único usuario en cualquier entorno (SQLite o RDS); ya no existen personas de demo adicionales. Vite no relee `.env` en caliente: reinicia `npm run dev`.

**Confirmar antes de tocar nada:** el mensaje de `verificar_config_bd` para el backend. Para el frontend, pestaña de Red del navegador en la primera petición — `X-Dev-User: dev.admin` y URL en `localhost:8010`.

## 4. Humo (primeros 3 pasos)

1. `GET http://localhost:8010/docs` → responde la página de Swagger.
2. `GET /api/v1/ordenes/clientes` → **200 con lista vacía** (RDS no tiene datos de F1 sembrados, a propósito). Un error aquí es de conexión/esquema, no de datos.
3. `GET /health/db` → `{"status":"ok","db":"reachable"}`.

Después de esto: `REGRESION-MANUAL-F0.md` (sección A primero) y luego `PLAN-PRUEBAS-F1-RDS.md`.
