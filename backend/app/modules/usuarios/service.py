"""Capa de negocio de la gestión de usuarios (F5-00).

Monta sobre `BaseService` (F0-00) para no reescribir listado/paginación/baja lógica, y
añade lo propio de la entidad:

- **Unicidad de email** (la credencial de login), case-insensitive.
- **Auditoría de `area` y `activo`** en `LogCambioParametro`: son los dos campos que
  otorgan o quitan acceso al sistema, exactamente lo que la regla de oro 6 manda registrar.
- **Guardarraíl anti-auto-bloqueo**: un admin no puede desactivarse ni cambiarse de área a
  sí mismo. Sin esto, el último admin puede dejar al sistema sin nadie que administre
  usuarios, y recuperarlo exigiría entrar a la base a mano.
- **Contraseña**: se hashea aquí y NUNCA se devuelve.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.audit import log_cambio_parametro
from app.core.auth.identity import Area, CurrentUser
from app.core.auth.passwords import hash_password
from app.core.errors import ConflictError, DomainError
from app.core.security_log import EventoSeguridad, registrar_evento_seguridad
from app.modules.catalogos.base_service import BaseService
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository
from app.modules.usuarios.schemas import UsuarioCreate, UsuarioRead, UsuarioUpdate


def _normaliza(valor: str) -> str:
    """Colapsa espacios internos y recorta extremos."""
    return " ".join(valor.split())


def _normaliza_email(valor: str) -> str:
    return valor.strip().lower()


class UsuarioService(BaseService[Usuario, UsuarioCreate, UsuarioUpdate, UsuarioRead]):
    read_schema = UsuarioRead
    entidad = "Usuario"

    def __init__(self, repo: UsuarioRepository) -> None:
        super().__init__(repo)
        self._usuario_repo = repo

    def _to_read(self, obj: Usuario) -> UsuarioRead:
        """Construcción EXPLÍCITA campo por campo.

        Deliberadamente NO se usa `model_validate(obj)`: enumerando los campos, añadir una
        columna sensible al modelo (hoy `password_hash`) no puede filtrarse a la respuesta
        por descuido. Del hash solo se deriva el booleano `tiene_password`.
        """
        return UsuarioRead(
            usuario_id=obj.usuario_id,
            nombre_usuario=obj.nombre_usuario,
            email=obj.email,
            area=obj.area,
            roles_adicionales=obj.roles_adicionales,
            activo=obj.activo,
            created_at=obj.created_at,
            tiene_password=bool(obj.password_hash),
        )

    # ── altas y ediciones ─────────────────────────────────────────────────────
    def _pre_create(self, payload: dict[str, Any], usuario: CurrentUser) -> None:
        payload["nombre_usuario"] = _normaliza(payload["nombre_usuario"])
        payload["email"] = _normaliza_email(payload["email"])
        payload["area"] = Area(payload["area"]).value
        self._verificar_email_unico(payload["email"], excluir_id=None)

        # La contraseña entra en claro y sale como hash; nunca se persiste el original.
        password = payload.pop("password", None)
        payload["password_hash"] = hash_password(password) if password else None

    def _pre_update(
        self, obj: Usuario, payload: dict[str, Any], usuario: CurrentUser
    ) -> None:
        if "nombre_usuario" in payload:
            payload["nombre_usuario"] = _normaliza(payload["nombre_usuario"])

        if "email" in payload:
            payload["email"] = _normaliza_email(payload["email"])
            self._verificar_email_unico(payload["email"], excluir_id=obj.usuario_id)

        if "area" in payload:
            nueva_area = Area(payload["area"]).value
            payload["area"] = nueva_area
            if nueva_area != obj.area:
                self._impedir_auto_bloqueo(obj, usuario, "cambiar tu propia área")
                # Se registra ANTES de escribir: el `commit` del repositorio persiste el
                # cambio y su bitácora en la MISMA transacción.
                log_cambio_parametro(
                    db=self.repo.db,
                    entidad=self.entidad,
                    entidad_id=obj.usuario_id,
                    campo="area",
                    anterior=obj.area,
                    nuevo=nueva_area,
                    usuario=usuario,
                )

    # ── alta/baja lógica ──────────────────────────────────────────────────────
    def cambiar_estado(
        self, id_: Any, activo: bool, usuario: CurrentUser, forzar: bool = False
    ) -> UsuarioRead:
        """Activa o desactiva al usuario (baja lógica; nunca se borra físicamente).

        Se sobreescribe la implementación base para auditar el cambio en AMBOS sentidos
        (el hook `_pre_desactivar` solo se dispara al desactivar) y para aplicar el
        guardarraíl de auto-bloqueo. `forzar` no aplica: un usuario no tiene dependientes.
        """
        obj = self._get_or_404(id_)

        if obj.activo != activo:
            if not activo:
                self._impedir_auto_bloqueo(obj, usuario, "desactivar tu propio usuario")
            log_cambio_parametro(
                db=self.repo.db,
                entidad=self.entidad,
                entidad_id=obj.usuario_id,
                campo="activo",
                anterior=obj.activo,
                nuevo=activo,
                usuario=usuario,
            )

        return self._to_read(self.repo.set_activo(obj, activo))

    # ── contraseña ────────────────────────────────────────────────────────────
    def establecer_password(
        self, id_: uuid.UUID, nueva: str, usuario: CurrentUser
    ) -> UsuarioRead:
        """(Re)establece la contraseña de un usuario. La anterior queda inservible.

        NO va a `LogCambioParametro`: esa tabla guarda valor anterior y nuevo de parámetros
        de negocio, y un reseteo no tiene valores que mostrar ahí. El evento sí queda
        trazado —quién reseteó a quién y cuándo, **sin** la contraseña ni el hash— en el
        log de seguridad (`core/security_log.py`); la bitácora formal es de F5 pleno.
        """
        obj = self._get_or_404(id_)
        actualizado = self.repo.update(obj, {"password_hash": hash_password(nueva)})
        registrar_evento_seguridad(
            evento=EventoSeguridad.PASSWORD_ESTABLECIDA,
            actor=usuario,
            objetivo=obj.nombre_usuario,
            objetivo_id=obj.usuario_id,
        )
        return self._to_read(actualizado)

    # ── reglas auxiliares ─────────────────────────────────────────────────────
    def _verificar_email_unico(self, email: str, excluir_id: uuid.UUID | None) -> None:
        if self._usuario_repo.get_by_email(email, excluir_id) is not None:
            raise ConflictError(
                f"Ya existe un usuario con el email «{email}».",
                detalles={"campo": "email", "valor": email},
            )

    @staticmethod
    def _impedir_auto_bloqueo(obj: Usuario, usuario: CurrentUser, accion: str) -> None:
        """Evita que quien administra se quite a sí mismo el acceso.

        En modo `dev_headers` no hay `usuario_id` (no hay registro detrás), así que la
        regla no aplica: es un modo de desarrollo, no de operación.
        """
        if usuario.usuario_id is not None and usuario.usuario_id == obj.usuario_id:
            raise DomainError(
                f"No puedes {accion}: perderías el acceso a la administración del "
                "sistema. Pídeselo a otro usuario del área Admin.",
                detalles={"usuario_id": str(obj.usuario_id)},
            )
