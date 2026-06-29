# frontend/Dockerfile — Imagen de desarrollo del frontend (React + TypeScript)
#
# En desarrollo solo necesitamos Node con el servidor de desarrollo (hot-reload).
# La imagen de PRODUCCIÓN será distinta (build estático servido por un servidor web)
# y se definirá cuando se acuerde el despliegue.

FROM node:20-slim

WORKDIR /app

# Instalar dependencias primero para aprovechar el caché de capas de Docker
COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173
# [[POR LLENAR: ajustar puerto/comando si se usa Next.js (3000, npm run dev)]]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
