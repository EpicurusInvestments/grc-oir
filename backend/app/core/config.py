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

# Valor de ejemplo de SECRET_KEY. Sirve para que la app arranque en local sin configurar
# nada, pero `core/auth/tokens.py` RECHAZA firmar o validar sesiones con él fuera de
# development: una llave que está en el repositorio no protege ninguna sesión.
SECRET_KEY_INSEGURA = "dev-insecure-change-me"


class Settings(BaseSettings):
    # El backend puede arrancar desde backend/ (uv run) o desde la raíz; buscamos en ambos.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Base de datos local para desarrollo (SQLite) — F1, ADR-028 ───────────────
    # Si viene definida (p.ej. "sqlite:///./dev_ordenes.db"), la app entera apunta a ese
    # archivo SQLite en vez de a SQL Server/RDS. Vacía (default) = comportamiento de
    # siempre, sin cambios: se construye la URL mssql+pyodbc de abajo. Los MODELOS son
    # los mismos en ambos casos (misma `Base.metadata`); esto solo elige qué motor
    # materializa el esquema. RDS sigue siendo la única base de producción — este switch
    # es exclusivamente para desarrollo/pruebas locales de F1.
    database_url: str = ""

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
    secret_key: str = SECRET_KEY_INSEGURA
    iva_rate: float = 0.16

    # ── Timbrado (PAC) ──────────────────────────────────────────────────────────
    # Codificación del archivo plano del PAC. Los layouts de los PAC mexicanos suelen
    # ser CP1252/Latin-1; el ejemplo de referencia llegó ya corrupto en sus acentos, así
    # que el valor real está PENDIENTE de confirmar con el proveedor. Se deja como
    # variable para poder cambiarlo sin tocar código.
    timbrado_encoding: str = "cp1252"
    # ── Importación masiva CSV (F0-05) ───────────────────────────────────────────
    # Límites del archivo de carga masiva de constantes. Configurables por entorno; si algún
    # día se necesita cargar un catálogo SAT completo (p.ej. c_ClaveProdServ ~52k filas) se
    # sube el tope. El archivo se procesa EN MEMORIA (no se persiste en el servidor).
    import_csv_max_bytes: int = 2 * 1024 * 1024  # 2 MB
    import_csv_max_rows: int = 5000
    # Orígenes permitidos por CORS (coma-separados). En dev, el frontend Vite.
    # En qa/producción se pone el dominio real vía variable de entorno.
    cors_origins: str = "http://localhost:5173"

    # ── Autenticación (F5-00) ────────────────────────────────────────────────────
    # Proveedor de autenticación. Un solo punto de selección: core/auth/get_auth_provider().
    #   local       → login con email + contraseña contra la tabla `usuario` (DEFAULT:
    #                 así las demos al cliente siempre pasan por la pantalla de login).
    #   dev_headers → identidad por X-Dev-User / X-Dev-Area (ADR-008). Solo development.
    #   azure_ad    → interfaz preparada, implementación diferida (falla con error claro).
    auth_provider: str = "local"
    # Sesión JWT firmada con SECRET_KEY. 8 h = una jornada laboral (decisión del equipo).
    jwt_expira_horas: int = 8
    jwt_algoritmo: str = "HS256"
    jwt_issuer: str = "grc-oir"

    # ── Auth de desarrollo (solo con AUTH_PROVIDER=dev_headers) ──────────────────
    # Usuario/área por defecto cuando no se envían los headers X-Dev-User / X-Dev-Area.
    dev_user: str = "dev.admin"
    dev_area: str = "admin"

    # ── SSO corporativo (por confirmar con IT de GRC) ────────────────────────────
    sso_provider: str = ""
    sso_client_id: str = ""

    # ── Almacenamiento de adjuntos de contrato (local | S3) ──────────────────────
    # STORAGE_BACKEND elige el adaptador (ver integrations/almacenamiento): 'local'
    # (sistema de archivos; default para dev/pruebas) o 's3' (bucket privado real).
    storage_backend: str = "local"
    # Raíz del adaptador local (relativa al proceso). Solo aplica con STORAGE_BACKEND=local.
    storage_local_root: str = "_storage_local"
    # Bucket y región del adaptador S3 (requeridos si STORAGE_BACKEND=s3).
    s3_bucket_contratos: str = ""
    aws_region: str = ""
    # Credenciales AWS. Se DECLARAN aquí para que pydantic-settings las lea del .env (y les
    # quite las comillas) y el adaptador las pase EXPLÍCITAMENTE a boto3: pydantic-settings NO
    # exporta a os.environ, así que el .env por sí solo no llega a la cadena de proveedores de
    # boto3 (causaba NoCredentialsError). Siguen viniendo SOLO del entorno/.env, nunca del
    # código. Si se dejan VACÍAS (qa/producción), boto3 usa su cadena por defecto: rol de
    # instancia / AWS Secrets Manager. Ver ADR-027.
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    # Tamaño máximo de un PDF de contrato (bytes). Configurable por entorno; default 10 MB.
    s3_max_pdf_bytes: int = 10 * 1024 * 1024
    # ADR-103: tope de un audio de "Material a Transmitir" (F1) — NO reusa
    # `s3_max_pdf_bytes` (silenciosamente cambiaría el tope de los adjuntos de
    # documentos). Configurable por entorno; default 15 MB (petición del usuario).
    s3_max_audio_bytes: int = 15 * 1024 * 1024
    # ADR-123: tope de "Formato de Horarios Reales" (F1) — acepta cualquier formato
    # (menos ejecutables), tope propio para no acoplarlo a los de arriba. Default 20 MB.
    s3_max_formato_real_bytes: int = 20 * 1024 * 1024

    # ── Correo (envío de PDFs de OrdenEstacion — ADR-105, local | SES) ───────────
    # CORREO_BACKEND elige el adaptador (ver integrations/correo): 'local' (no envía
    # nada real, solo registra en el log; default para dev/pruebas — SES en sandbox
    # exige verificar cada destinatario) o 'ses' (Amazon SES real).
    correo_backend: str = "local"
    # Remitente y región/credenciales de SES (requeridos si CORREO_BACKEND=ses).
    # Reusa `aws_region`/`aws_access_key_id`/`aws_secret_access_key` de arriba: SES vive
    # en la misma cuenta/región de AWS que S3.
    ses_from_email: str = ""
    ses_from_name: str = ""

    @property
    def is_development(self) -> bool:
        return self.app_env.strip().lower() == "development"

    @property
    def cors_origins_list(self) -> list[str]:
        """Orígenes CORS como lista (se parsea el string coma-separado del entorno)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """URL de conexión activa.

        Si `DATABASE_URL` está definida, se usa tal cual (desarrollo local con SQLite,
        F1 — ver ADR-028). Si no, se construye la URL `mssql+pyodbc` de siempre contra
        RDS: el comportamiento existente no cambia cuando la variable no está seteada.
        """
        if self.database_url:
            return self.database_url
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
