"""Selección del adaptador de almacenamiento por configuración (ADR-027).

`get_almacenamiento()` es el ÚNICO punto donde se decide local vs S3, según
`STORAGE_BACKEND` (`local` por defecto). El servicio de Contrato depende solo del puerto
(`AlmacenamientoPort`) y nunca de un adaptador concreto.

- `local` → `AlmacenamientoLocal` (sistema de archivos; default para dev/pruebas).
- `s3`    → `AlmacenamientoS3` (requiere `S3_BUCKET_CONTRATOS` y `AWS_REGION`; si faltan,
            falla con un error de configuración CLARO — no cae en silencio al local).
"""

from __future__ import annotations

from app.core.config import settings
from app.integrations.almacenamiento.adapter_local import AlmacenamientoLocal
from app.integrations.almacenamiento.documentos import AlmacenamientoError
from app.integrations.almacenamiento.port import AlmacenamientoPort


def get_almacenamiento() -> AlmacenamientoPort:
    """Devuelve el adaptador de almacenamiento configurado."""
    backend = settings.storage_backend.strip().lower()

    if backend == "local":
        return AlmacenamientoLocal(settings.storage_local_root)

    if backend == "s3":
        if not settings.s3_bucket_contratos or not settings.aws_region:
            raise AlmacenamientoError(
                "STORAGE_BACKEND=s3 requiere S3_BUCKET_CONTRATOS y AWS_REGION configurados.",
                detalles={
                    "s3_bucket_contratos": bool(settings.s3_bucket_contratos),
                    "aws_region": bool(settings.aws_region),
                },
            )
        # Import diferido: solo se importa boto3 cuando el backend S3 está activo.
        from app.integrations.almacenamiento.adapter_s3 import AlmacenamientoS3

        # Credenciales explícitas si vienen del .env; vacías → boto3 usa su cadena por
        # defecto (rol de instancia / Secrets Manager en qa/producción). Ver ADR-027.
        return AlmacenamientoS3(
            bucket=settings.s3_bucket_contratos,
            region=settings.aws_region,
            access_key_id=settings.aws_access_key_id or None,
            secret_access_key=settings.aws_secret_access_key or None,
        )

    raise AlmacenamientoError(
        f"STORAGE_BACKEND desconocido: '{settings.storage_backend}' (use 'local' o 's3').",
    )


__all__ = ["get_almacenamiento"]
