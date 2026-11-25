import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

// Parcours de bout en bout contre la vraie API (phase 4, condition de sortie) : base neuve, corpus
// indexé, modèle de réponse déterministe (tests/e2e/serveur_de_test.py). Identifiants générés
// à chaque lancement, écrits hors du dépôt.
export const INFO = process.env.URAG_E2E_INFO ?? join(tmpdir(), `urag-e2e-${process.pid}.json`);
process.env.URAG_E2E_INFO = INFO;
const API_PORT = 8011;
const WEB_PORT = 5181;

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1, // les parcours partagent la même base de démonstration
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, locale: "fr-FR", trace: "off" },
  webServer: [
    {
      command: `uv run python tests/e2e/serveur_de_test.py --port ${API_PORT} --info ${INFO} --delay 0.03`,
      cwd: "../..",
      url: `http://127.0.0.1:${API_PORT}/api/v1/admin/health`,
      timeout: 240_000,
      reuseExistingServer: false,
      stdout: "pipe",
    },
    {
      command: `pnpm exec vite --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      env: { URAG_API_URL: `http://127.0.0.1:${API_PORT}` },
      url: `http://127.0.0.1:${WEB_PORT}`,
      timeout: 60_000,
      reuseExistingServer: false,
    },
  ],
});
