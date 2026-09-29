"""Selección del adaptador de correo por configuración (ADR-105/ADR-138).

`get_correo()` es el ÚNICO punto donde se decide local vs SES vs SMTP, según
`CORREO_BACKEND` (`local` por defecto) — mismo criterio que `get_almacenamiento()`
(ADR-027).

- `local` → `CorreoLocal` (no envía nada real; solo registra en el log — default para
            dev/pruebas, ya que SES en sandbox exige verificar cada destinatario).
- `ses`   → `CorreoSES` (requiere `SES_FROM_EMAIL` y `AWS_REGION`; si faltan, falla con
            un error de configuración CLARO — no cae en silencio al local). Habla la API
            de AWS vía boto3 (access key/secret de IAM).
- `smtp`  → `CorreoSmtp` (ADR-138; requiere `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` y
            `SMTP_FROM_EMAIL`). Habla SMTP real (STARTTLS) — sirve para el endpoint SMTP
            de SES (credenciales SMTP dedicadas, DISTINTAS del access key/secret de
            `ses`) o cualquier otro servidor SMTP.
"""

from __future__ import annotations

from app.core.config import settings
from app.integrations.correo.adapter_local import CorreoLocal
from app.integrations.correo.errors import CorreoError
from app.integrations.correo.port import CorreoPort


def get_correo() -> CorreoPort:
    """Devuelve el adaptador de correo configurado."""
    backend = settings.correo_backend.strip().lower()

    if backend == "local":
        return CorreoLocal(settings.storage_local_root)

    if backend == "ses":
        if not settings.ses_from_email or not settings.aws_region:
            raise CorreoError(
                "CORREO_BACKEND=ses requiere SES_FROM_EMAIL y AWS_REGION configurados.",
                detalles={
                    "ses_from_email": bool(settings.ses_from_email),
                    "aws_region": bool(settings.aws_region),
                },
            )
        # Import diferido: solo se importa boto3 cuando el backend SES está activo.
        from app.integrations.correo.adapter_ses import CorreoSES

        return CorreoSES(
            region=settings.aws_region,
            from_email=settings.ses_from_email,
            from_name=settings.ses_from_name or None,
            access_key_id=settings.aws_access_key_id or None,
            secret_access_key=settings.aws_secret_access_key or None,
        )

    if backend == "smtp":
        faltan_datos_smtp = not (
            settings.smtp_host
            and settings.smtp_user
            and settings.smtp_password
            and settings.smtp_from_email
        )
        if faltan_datos_smtp:
            raise CorreoError(
                "CORREO_BACKEND=smtp requiere SMTP_HOST, SMTP_USER, SMTP_PASSWORD y "
                "SMTP_FROM_EMAIL configurados.",
                detalles={
                    "smtp_host": bool(settings.smtp_host),
                    "smtp_user": bool(settings.smtp_user),
                    "smtp_password": bool(settings.smtp_password),
                    "smtp_from_email": bool(settings.smtp_from_email),
                },
            )
        from app.integrations.correo.adapter_smtp import CorreoSmtp

        return CorreoSmtp(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name or None,
        )

    raise CorreoError(
        f"CORREO_BACKEND desconocido: '{settings.correo_backend}' (use 'local', 'ses' o 'smtp')."
    )


__all__ = ["get_correo", "CorreoPort", "CorreoError"]
