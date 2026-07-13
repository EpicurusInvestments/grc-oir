"""Configuración central del backend.

Lee TODO desde variables de entorno (`.env` en local; en Docker las inyecta
`docker-compose.yml` vía `env_file`). Las credenciales NUNCA viven en el código.

Aquí también se construye la URL de conexión a SQL Server (AWS RDS). El nombre de la
base es `GRC-OIR` (con guion): por eso la cadena ODBC se pasa por `odbc_connect=`
URL-encodeada, para que el guion no rompa la URL de SQLAlchemy.
"""

from __future__ import annotations

import urllib.parse
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # El backend puede arrancar desde backend/ (uv run) o desde la raíz; buscamos en ambos.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Base de datos (AWS RDS SQL Server) ─────────────────────────────────────
    db_host: str = "localhost"
    db_port: int = 1433
    db_name: str = "GRC-OIR"
    db_user: str = ""
    db_password: str = ""
    # Encrypt / TrustServerCertificate: valores tal como los entiende ODBC Driver 18.
    db_encrypt: str = "yes"
    db_trust_server_certificate: str = "yes"
    odbc_driver: str = "ODBC Driver 18 for SQL Server"

    # ── Backend ────────────────────────────────────────────────────────────────
    # development | qa | production. Gobierna el stub de autenticación (ver security.py):
    # el acceso dev por headers SOLO se permite en development; en otros entornos sin SSO
    # la autenticación falla cerrada.
    app_env: str = "development"
    secret_key: str = "dev-insecure-change-me"
    iva_rate: float = 0.16
    # Orígenes permitidos por CORS (coma-separados). En dev, el frontend Vite.
    # En qa/producción se pone el dominio real vía variable de entorno.
    cors_origins: str = "http://localhost:5173"

    # ── Auth de desarrollo (mientras el SSO corporativo está [[POR LLENAR]]) ─────
    # Usuario/área por defecto cuando no se envían los headers X-Dev-User / X-Dev-Area.
    dev_user: str = "dev.admin"
    dev_area: str = "admin"

    # ── SSO corporativo (por confirmar con IT de GRC) ────────────────────────────
    sso_provider: str = ""
    sso_client_id: str = ""

    # ── Almacenamiento de adjuntos de contrato (S3) ──────────────────────────────
    # Vacío en F0-03: la subida a S3 está diferida y se usa el adaptador local. Cuando se
    # configure el bucket, el adaptador S3 leerá estos valores (credenciales por el
    # proveedor de AWS del entorno, nunca aquí).
    s3_bucket_contratos: str = ""
    aws_region: str = ""

    @property
    def is_development(self) -> bool:
        return self.app_env.strip().lower() == "development"

    @property
    def cors_origins_list(self) -> list[str]:
        """Orígenes CORS como lista (se parsea el string coma-separado del entorno)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """URL `mssql+pyodbc` usando odbc_connect (soporta el guion de GRC-OIR)."""
        odbc_str = (
            f"DRIVER={{{self.odbc_driver}}};"
            f"SERVER={self.db_host},{self.db_port};"
            f"DATABASE={self.db_name};"
            f"UID={self.db_user};"
            f"PWD={self.db_password};"
            f"Encrypt={self.db_encrypt};"
            f"TrustServerCertificate={self.db_trust_server_certificate};"
        )
        return "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(odbc_str)


@lru_cache
def get_settings() -> Settings:
    """Settings cacheado (una sola lectura del entorno por proceso)."""
    return Settings()


settings = get_settings()
