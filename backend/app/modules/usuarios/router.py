"""Capa API de la gestión de usuarios (F5-00). Solo Admin.

Reutiliza `build_crud_router` (F0-00) para los 5 endpoints estándar —listar, obtener,
crear, editar y activar/desactivar— con `requiere_permiso("usuarios:...")` ya cableado, y
añade el endpoint propio de F5-00: establecer contraseña.

El permiso `usuarios` está en la matriz RBAC SOLO para Admin, incluso en lectura: el
padrón de usuarios no es un catálogo consultable por las demás áreas.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, requiere_permiso
from app.modules.catalogos.crud_router import build_crud_router
from app.modules.usuarios.repository import UsuarioRepository
from app.modules.usuarios.schemas import (
    EstablecerPasswordIn,
    UsuarioCreate,
    UsuarioRead,
    UsuarioUpdate,
)
from app.modules.usuarios.service import UsuarioService


def get_usuario_service(db: Session = Depends(get_db)) -> UsuarioService:
    return UsuarioService(UsuarioRepository(db))


router = build_crud_router(
    prefix="/usuarios",
    tags=["usuarios"],
    permiso_base="usuarios",
    read_schema=UsuarioRead,
    create_schema=UsuarioCreate,
    update_schema=UsuarioUpdate,
    get_service=get_usuario_service,
    id_type=uuid.UUID,
)


@router.post("/{usuario_id}/password", response_model=UsuarioRead)
def establecer_password(
    usuario_id: uuid.UUID,
    payload: EstablecerPasswordIn,
    actual: CurrentUser = Depends(requiere_permiso("usuarios:editar")),
    svc: UsuarioService = Depends(get_usuario_service),
) -> UsuarioRead:
    """(Re)establece la contraseña de un usuario.

    Endpoint separado de la edición del perfil a propósito: cambiar una contraseña es un
    acto explícito, no un efecto colateral de guardar un formulario. La contraseña anterior
    deja de funcionar de inmediato; las sesiones ya emitidas siguen vivas hasta expirar
    (el token es *stateless* — ver limitaciones conocidas en ADR-028).
    """
    return svc.establecer_password(usuario_id, payload.password, actual)
