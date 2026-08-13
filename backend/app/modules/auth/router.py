"""Capa API de autenticación (F5-00).

- `POST /auth/login`  — PÚBLICO (es lo que da la sesión; no puede exigir sesión).
- `GET  /auth/me`     — requiere sesión válida; no exige ningún permiso de módulo.
- `POST /auth/logout` — cortesía simétrica para el frontend (ver nota abajo).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.auth import get_auth_provider
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.auth.schemas import LoginIn, SesionOut, UsuarioSesion
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(get_auth_provider(), db)


@router.post("/login", response_model=SesionOut)
def login(
    payload: LoginIn,
    request: Request,
    svc: AuthService = Depends(get_auth_service),
) -> SesionOut:
    """Valida credenciales y emite el token de sesión (8 h por defecto).

    Cualquier fallo responde 401 con el MISMO mensaje genérico: no se revela si el email
    está dado de alta, si la contraseña es incorrecta o si el usuario está inactivo.
    """
    ip = request.client.host if request.client else None
    return svc.login(payload, ip)


@router.get("/me", response_model=UsuarioSesion)
def me(usuario: CurrentUser = Depends(get_current_user)) -> UsuarioSesion:
    """Identidad y área del usuario en sesión. El frontend la usa al recargar la página."""
    return AuthService.sesion_actual(usuario)


@router.post("/logout", status_code=204)
def logout() -> None:
    """Cierre de sesión.

    El token es **stateless**: la sesión se cierra de verdad cuando el cliente descarta el
    token (y expira sola a las 8 h). Este endpoint existe para que el frontend tenga una
    llamada simétrica y para tener dónde colgar una lista de revocación si el negocio
    llega a exigir invalidación inmediata (fuera de alcance en F5-00).
    """
    return None
