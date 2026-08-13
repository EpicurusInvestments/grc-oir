"""Hash y verificación de contraseñas (bcrypt).

ÚNICO lugar del sistema que conoce el algoritmo: migrar a argon2id sería reescribir este
archivo y nada más (los adaptadores y la migración del seed llaman solo a estas dos
funciones). La contraseña en claro NUNCA se persiste, ni se registra en logs, ni se
devuelve en ningún schema.

Límite conocido de bcrypt: solo considera los primeros **72 bytes** de la contraseña. Los
schemas que ESTABLECEN contraseña la validan antes con un mensaje claro; aquí se trunca de
forma defensiva para que bcrypt nunca lance una excepción por una entrada larga que llegue
por otra vía (p.ej. el formulario de login).
"""

from __future__ import annotations

from functools import lru_cache

import bcrypt

# Costo del hash. 12 es el balance habitual (~250 ms en hardware moderno): caro para un
# ataque por diccionario, imperceptible en un login. Las pruebas lo bajan para no pagar
# ese costo N veces (ver `test_f5_00_auth.py`).
_ROUNDS = 12
_MAX_BYTES = 72


def _a_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BYTES]


@lru_cache(maxsize=1)
def _hash_senuelo() -> bytes:
    """Hash desechable para gastar tiempo cuando NO hay contraseña que verificar."""
    return bcrypt.hashpw(b"usuario-inexistente", bcrypt.gensalt(rounds=_ROUNDS))


def hash_password(password: str) -> str:
    """Hash de la contraseña, listo para persistir en `usuario.password_hash`."""
    return bcrypt.hashpw(_a_bytes(password), bcrypt.gensalt(rounds=_ROUNDS)).decode("ascii")


def verificar_password(password: str, hash_almacenado: str | None) -> bool:
    """Verifica la contraseña. Devuelve `False` ante cualquier fallo; nunca lanza.

    Si no hay hash (usuario sin contraseña establecida, o de Azure AD en el futuro) se
    ejecuta igualmente una verificación **señuelo**: el tiempo de respuesta no debe
    revelar si el usuario existe o si tiene contraseña. Esa es la mitad temporal del
    "mensaje de error genérico"; la otra mitad la pone el adaptador.
    """
    if not hash_almacenado:
        bcrypt.checkpw(b"contrasena-invalida", _hash_senuelo())
        return False
    try:
        return bcrypt.checkpw(_a_bytes(password), hash_almacenado.encode("ascii"))
    except (ValueError, TypeError):
        # Hash corrupto o con un formato que bcrypt no reconoce: no autentica.
        return False
