# backend/Dockerfile — Imagen del backend (FastAPI + driver ODBC para SQL Server)
#
# ¿Por qué este Dockerfile tiene "tanto" sistema operativo?
# Para hablar con SQL Server desde Python se necesita el "ODBC Driver 18 for
# SQL Server" de Microsoft (una librería del sistema, no de Python). Aquí lo
# instalamos dentro de la imagen para que TODOS los desarrolladores tengan
# exactamente el mismo driver, igual al que se usará en despliegue.

FROM python:3.12-slim

# Instalar el ODBC Driver 18 de Microsoft (repos oficiales de Microsoft para Debian)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg2 ca-certificates apt-transport-https \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias de Python primero (aprovecha el caché de Docker:
# si solo cambia el código, no se reinstala todo)
COPY pyproject.toml ./
# [[POR LLENAR: comando de instalación según el gestor elegido, p.ej.:]]
# RUN pip install --no-cache-dir .
# o con uv:  RUN pip install uv && uv sync --frozen

# El código se monta como volumen en desarrollo (ver docker-compose.yml),
# pero lo copiamos también para que la imagen sirva sin volúmenes (CI/despliegue):
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
