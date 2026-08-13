# Módulo F5-00 — Autenticación base (login local + preparación Azure AD) · Fase: F5 (adelantado)

> **Estado: IMPLEMENTADO** (2026-08-12). Decisiones técnicas en **ADR-041**; endpoints en
> `docs/API-CONTRACT.md` (secciones «Autenticación» y «Gestión de usuarios»).
>
> **Adelanto consciente de F5.** Se construyó antes que el resto de F5 porque: (1) da una
> impresión profesional en las demos al cliente, y (2) define cómo se identifica el usuario
> en todo el sistema, algo que las demás fases (F1 en adelante) necesitan para su RBAC.
> El resto de F5 (permisos finos por campo, roles complejos, bitácora de seguridad formal,
> conexión real Azure AD) se construye cuando llegue el turno de la fase completa.

## Propósito

Reemplazar la autenticación de desarrollo por headers (`X-Dev-User`/`X-Dev-Area`) por un
inicio de sesión real, con dos proveedores intercambiables por configuración: **local**
(para el equipo de desarrollo, sin dependencia de Azure) y **Azure AD** (para producción y
pruebas con AD; se deja preparado, no implementado). Incluye gestión mínima de usuarios y
RBAC por área.

## Concepto central: proveedor de autenticación intercambiable

Análogo al puerto de almacenamiento de S3 (ADR-020). El sistema no depende de "login local"
ni de "Azure AD" directamente, sino de una **abstracción de proveedor de autenticación** con
implementaciones seleccionables por variable de entorno:
- `AUTH_PROVIDER=local` → login local con usuario/contraseña (implementado en F5-00).
- `AUTH_PROVIDER=azure_ad` → OAuth/OpenID Connect contra Azure AD (interfaz preparada en
  F5-00; implementación real diferida).
- `AUTH_PROVIDER=dev_headers` → **modo desarrollo** que conserva el mecanismo actual de headers
  para que el equipo no tenga que loguearse en cada prueba local. Ver "Decisiones confirmadas".

Beneficio: activar Azure AD en producción no requiere reescribir el sistema, solo implementar
el adaptador y cambiar la variable.

## Decisiones confirmadas (líder del proyecto)

1. **Contraseña inicial del seed `dev.admin`:** vía **migración** que le asigne el hash de una
   contraseña temporal (el valor se comparte por canal seguro; en el repo nunca va en claro).
   Debe poder cambiarse después desde la gestión de usuarios.
2. **Modo desarrollo por defecto vs login real:** existe `AUTH_PROVIDER=dev_headers` para que el
   equipo NO tenga que loguearse en cada prueba local, PERO el sistema usa **login real por
   defecto** (para que las demos al cliente siempre sean con login). El modo `dev_headers` solo
   debe funcionar en entorno de desarrollo (fail-closed fuera de development, como el mecanismo
   actual).
3. **Expiración del token:** 8 horas (una jornada), configurable por env.
4. **Ubicación de la pantalla de gestión de usuarios:** dentro del menú **"Seguridad"** (la
   tarjeta/fase de Seguridad que ya existe en el dashboard). Al construir F5-00 se "enciende" la
   entrada de Seguridad en el `phaseRegistry` para alojar esta pantalla (aunque el resto de F5
   siga pendiente). Confirmar con Claude Code cómo montar esa ruta de forma limpia.

## Alcance de F5-00

### Backend
- **Modelo Usuario** (ya existe de F0-04): agregar `password_hash` (NUNCA contraseña en texto
  plano; hash con bcrypt o argon2) y lo necesario para el login local. Mantener `area` (ENUM
  ya definido) y `activo`.
- **Abstracción de proveedor de autenticación** (puerto) + adaptador **local**:
  - Endpoint de login: valida credenciales, devuelve un token de sesión (JWT) con la identidad
    y el área del usuario.
  - Verificación del token en cada petición protegida (reemplaza los headers de desarrollo).
  - Expiración del token (8h, configurable); manejo de sesión.
- **Adaptador `dev_headers`:** conserva el comportamiento actual (X-Dev-User/X-Dev-Area) para
  desarrollo, fail-closed fuera de development.
- **Adaptador Azure AD:** interfaz/hueco preparado, sin la conexión real (diferido).
- **RBAC por área:** las peticiones resuelven el área del **usuario autenticado** (no de un
  header, salvo en modo dev_headers). Respetar las áreas ya definidas: ventas, facturacion,
  tesoreria, cxc, cxp, direccion, nominas, admin. Sin romper los módulos de F0.
- **Gestión de usuarios (endpoints):** crear, editar, activar/desactivar usuarios; asignar área;
  (re)establecer contraseña. Solo Admin.

### Frontend
- **Pantalla de login** (respetando theme.css y el diseño del sistema; buena primera impresión).
- **Manejo de sesión:** guardar el token, enviarlo en cada petición (vía el apiClient existente),
  redirigir a login si no hay sesión / expira, y logout.
- **Pantalla de gestión de usuarios** (Admin), ubicada en el menú **Seguridad**: lista + alta/
  edición, asignar área, activar/desactivar, establecer contraseña.
- **Guard de rutas:** las pantallas requieren sesión; la gestión de usuarios requiere Admin.
- **Encender la fase Seguridad** en el `phaseRegistry` (al menos para alojar esta pantalla).

## Seguridad (requisitos, no opcionales)
- Contraseñas SIEMPRE con hash fuerte (bcrypt/argon2); jamás en texto plano ni en logs.
- Token con expiración (8h configurable); secreto de firma del JWT solo en `.env` (nunca en
  código ni en `.env.example`, donde va como `[[POR LLENAR]]`).
- Mensajes de error de login genéricos ("usuario o contraseña incorrectos"), sin revelar si
  el usuario existe.
- El secreto de firma y cualquier credencial, solo por entorno (`.env` / Secrets Manager en prod).
- Un login mal hecho da falsa sensación de seguridad: hacerlo bien en lo básico aunque sea mínimo.

## Estados
- Usuario: `activo` (baja lógica). Sin máquina de estados.

## Roles / permisos
- Gestión de usuarios: solo Admin.
- El RBAC por área que ya usan los catálogos (escritura Admin, lectura resto) ahora se resuelve
  del usuario autenticado. El control fino por campo/rol se completa en F5 pleno.

## Reglas de negocio clave
- Un usuario tiene exactamente un área (ENUM). `roles_adicionales` queda para el RBAC fino de F5.
- El seed `dev.admin` (de F0-04) es el primer usuario; su contraseña inicial se asigna por
  migración (decisión 1).

## Integraciones
- Azure AD (diferido): OAuth/OpenID Connect. La configuración del lado de Azure (registro de
  la app, permisos) la realiza quien administre Azure. En F5-00 solo se deja la interfaz.

## Dependencias
- Modelo Usuario de F0-04. Es transversal: una vez en `main`, las demás fases resuelven su
  identidad/RBAC sobre este módulo. **Debe entrar a `main` antes de que F1 implemente su RBAC.**

## Coordinación con el trabajo en curso (F1)
- F5-00 lo construye el líder en su propia rama, desde `main`, y se mergea PRIMERO.
- El dev de F1 (que trabaja en local, aún sin commits) hará `git pull` de `main` tras el merge
  e integrará el login a su rama, construyendo el RBAC de F1 sobre la identidad real.
- Cuidar el cambio de "headers dev" → "usuario autenticado" para no romper F1; comunicarlo. El
  modo `dev_headers` ayuda a esta transición sin frenar el trabajo local.

## Cómo quedó implementado

Construido en 5 tandas, todas validadas por el líder del proyecto.

### Backend

| Pieza | Ubicación |
|---|---|
| Puerto de autenticación + factory | `app/core/auth/port.py` · `__init__.py` (`get_auth_provider`) |
| Adaptadores | `adapter_local.py` (implementado) · `adapter_dev_headers.py` (ADR-008 intacto) · `adapter_azure_ad.py` (hueco preparado) |
| Contraseñas y token | `app/core/auth/passwords.py` (bcrypt) · `tokens.py` (JWT HS256) |
| Identidad y RBAC | `app/core/auth/identity.py` (`Area`, `CurrentUser`) · `app/core/security.py` (matriz RBAC, `requiere_permiso`) |
| Log de seguridad | `app/core/security_log.py` (mínimo; formal en F5 pleno) |
| API de sesión | `app/modules/auth/` → `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` |
| Gestión de usuarios | `app/modules/usuarios/` → CRUD + `POST /usuarios/{id}/password` |
| Migración | `a1c8e3d47b92` — `usuario.password_hash` NVARCHAR(255) NULL + contraseña del seed desde el entorno |

**Decisiones de implementación** (detalle y razones en ADR-041):
- Credencial de login = **email** (único e indexado); `nombre_usuario` no lo es.
- `Area` y `CurrentUser` se movieron a `core/auth/identity.py` para romper el ciclo
  `security ↔ auth`, y se **re-exportan** desde `core/security.py`: los imports de F0 no
  cambiaron.
- El **estado del usuario se relee de la BD en cada petición**: desactivar a alguien o
  cambiarle el área invalida su sesión de inmediato, sin esperar a que expire el token.
- **`requiere_permiso` no cambió**: los 11 catálogos de F0 y sus pruebas no se tocaron
  (el `conftest` fija `dev_headers` para ellas).
- Auditoría: `area` y `activo` → `LogCambioParametro`. El **reseteo de contraseña** va al
  log de seguridad, no a esa tabla (no tiene valores que mostrar en un panel de detalle).
- Guardarraíl anti-auto-bloqueo: nadie puede desactivarse ni cambiarse su propia área.

### Frontend

| Pieza | Ubicación |
|---|---|
| Token + señal de expiración | `shared/lib/session.ts` |
| Shim de `currentUser` (decisión H-4) | `shared/lib/currentUser.ts` |
| Sesión (provider + hook) | `modules/auth/session.tsx` · `sessionContext.ts` |
| Pantalla de login | `modules/auth/pages/LoginPage.tsx` |
| Guards | `modules/auth/components/RequireSession.tsx` · `RequireArea.tsx` |
| Explorador F5 | `modules/seguridad/pages/SeguridadExplorerPage.tsx` · `seguridadRegistry.tsx` |
| Gestión de usuarios | `modules/seguridad/usuarios/` (lista + detalle + formulario + diálogo de contraseña) |

- **Las 14 pantallas de F0 no se tocaron**: el `SessionProvider` sincroniza el shim
  `currentUser`. La migración a `useSession()` queda para un PR aparte.
- El login usa el **rojo de marca** `--grc-red: #D73347` (token en `theme.css`), y F5
  Seguridad reusa ese mismo token vía la clase de scope `.phase-f5`.
- Tras un login **desde cero** se entra al Dashboard; solo si la sesión **expiró
  trabajando** se retoma la pantalla interrumpida.

### Pruebas
- Backend: **241** (`pytest`), incluidas login OK/fallido, token expirado/alterado/de otro
  emisor, acceso sin sesión, RBAC por área con token, política y truncado de contraseñas,
  auditoría y guardarraíl. `ruff` y `mypy --strict` limpios.
- Frontend: **34** (`vitest`), incluidas login, guards, expiración, destino post-login y la
  pantalla de usuarios. `tsc --noEmit` y `eslint` limpios.

## Limitaciones conocidas (riesgos aceptados, a revisitar en F5 pleno)

Registradas también en ADR-041:

1. **Sin control de intentos fallidos ni rate limiting** en el login.
2. **Token en `localStorage`** del navegador: expuesto a XSS. La alternativa (cookie
   `httpOnly` + CSRF) cambia CORS y el flujo completo.
3. **Sin refresh token**: al expirar las 8 h se vuelve a iniciar sesión.
4. **`logout` es un no-op de servidor**: el token sigue siendo válido hasta expirar aunque
   el cliente lo descarte. El frontend cierra sesión descartándolo.
5. **Sin política de rotación/caducidad de contraseñas** ni "forzar cambio en el primer
   inicio de sesión".
6. **Azure AD sin implementar**: el adaptador existe y falla con un mensaje claro.
7. **`roles_adicionales`** se captura pero todavía no participa en ninguna decisión de
   permisos (es del RBAC fino de F5 pleno).

## Pendientes resueltos durante la implementación
- **Ruta de la pantalla bajo "Seguridad"**: `/seguridad` con `SeguridadExplorerPage` +
  `seguridadRegistry`, mismo patrón que el explorador de catálogos. El resto de F5 se suma
  como entradas nuevas del registry, sin tocar la ruta.
- **Librerías**: `pyjwt>=2.9` (token) y `bcrypt>=4.2` (hash, sin `passlib`), formalizadas en
  `backend/pyproject.toml`.
