"""Permisos a nivel de campo sobre parámetros sensibles.

Hook transversal con FIRMA ESTABLE desde la Entrega 1, para que los servicios que
modifican campos marcados como sensibles en la spec (p.ej. `porcentaje_comision_*`,
`dias_credito_default`) lo invoquen ANTES de escribir, y no haya re-trabajo cuando la
entidad `PermisoCampo` se administre en F5.

Estado F0-00: implementación mínima — Admin pasa; cualquier otra área se rechaza.
# TODO(F5): consultar la tabla `PermisoCampo` para resolver el permiso por (área, campo).
"""

from __future__ import annotations

from app.core.errors import PermissionDeniedError
from app.core.security import Area, CurrentUser


def verificar(entidad: str, campo: str, usuario: CurrentUser) -> None:
    """Lanza `PermissionDeniedError` (403) si el usuario no puede editar el campo.

    Args:
        entidad: nombre de la entidad de la spec (p.ej. "Agencia").
        campo: nombre del campo sensible (p.ej. "porcentaje_comision_agencia_default").
        usuario: usuario autenticado (su área decide).
    """
    # TODO(F5): reemplazar por consulta a PermisoCampo(area, entidad, campo).
    if usuario.area is Area.ADMIN:
        return
    raise PermissionDeniedError(
        f"El área '{usuario.area.value}' no puede modificar el campo sensible "
        f"'{entidad}.{campo}'.",
    )
