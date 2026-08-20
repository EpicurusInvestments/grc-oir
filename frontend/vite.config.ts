/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Un solo .env para todo el repo (raíz): evita mantener copias sincronizadas entre
  // backend/ y frontend/. El backend ya hace lo equivalente (ver Settings.model_config,
  // env_file=(".env", "../.env")).
  envDir: "..",
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    // En Docker el dev server escucha en 0.0.0.0 (ver docker-compose.yml).
    host: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: false,
  },
});
