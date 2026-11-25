import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Même origine que l'API (ADR-0023) : en développement, Vite relaie /api vers le service.
const api = process.env.URAG_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { "/api": { target: api, changeOrigin: false } } },
  preview: { port: 4173, strictPort: true, proxy: { "/api": { target: api, changeOrigin: false } } },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});
