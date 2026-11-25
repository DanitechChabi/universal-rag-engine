import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

type Info = { password: string; admin: string; alice: string; chloe: string; doc_admin: string; base_url: string };
const info = (): Info => JSON.parse(readFileSync(process.env.URAG_E2E_INFO!, "utf-8"));

async function login(page: Page, who: "admin" | "alice" | "chloe" | "doc_admin") {
  await page.goto("/connexion");
  await page.getByLabel("Identifiant").fill(info()[who]);
  await page.getByLabel("Mot de passe").fill(info().password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByLabel("Posez votre question…")).toBeVisible();
}

async function ask(page: Page, question: string) {
  await page.getByLabel("Posez votre question…").fill(question);
  await page.keyboard.press("Enter");
  await expect(page.locator(".msg-answer").last().locator(".answer-foot")).toBeVisible({ timeout: 30_000 });
  return page.locator(".msg-answer").last();
}

test("connexion : message d'erreur, session par cookie HttpOnly, déconnexion", async ({ page, context }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/connexion$/);
  await page.getByLabel("Identifiant").fill(info().alice);
  await page.getByLabel("Mot de passe").fill("mauvais mot de passe");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("alert")).toContainText("Identifiant ou mot de passe incorrect");
  await login(page, "alice");
  const cookies = await context.cookies();
  expect(cookies.find((c) => c.name === "urag_access")?.httpOnly).toBe(true);
  expect(cookies.find((c) => c.name === "urag_refresh")?.httpOnly).toBe(true);
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(stored).not.toMatch(/eyJ|token/i); // aucun jeton accessible au JavaScript
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/connexion$/);
});

test("assistant : réponse sourcée, extrait, ouverture du document, historique", async ({ page }) => {
  await login(page, "alice");
  const answer = await ask(page, "Quel est le loyer mensuel du bail ?");
  await expect(answer).toContainText("450 000 FCFA");
  await expect(answer.getByText("Modèle local")).toBeVisible();
  await answer.locator(".cite").first().click();
  const source = page.locator(".source").first();
  await expect(source).toContainText("contrat_bail_alpha");
  await expect(source.locator(".excerpt")).toContainText("450 000");
  const link = source.getByRole("link", { name: "Ouvrir le document" });
  const href = await link.getAttribute("href");
  expect(href).toMatch(/^\/api\/v1\/documents\/[0-9a-f-]+\/open$/);
  expect(await link.getAttribute("rel")).toContain("noopener");
  const [popup] = await Promise.all([page.waitForEvent("popup"), link.click()]);
  await popup.close();
  const response = await page.request.get(href!); // avec la session de l'utilisatrice (cookies)
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("application/pdf");
  expect(response.headers()["content-security-policy"]).toMatch(/^sandbox/);
  // La conversation est enregistrée et se rouvre depuis l'historique.
  await page.reload();
  await expect(page.locator(".msg-answer")).toContainText("450 000 FCFA");
  await expect(page.locator(".history-item").first()).toContainText("Quel est le loyer mensuel");
});

test("assistant : question de suite reformulée à partir de la conversation", async ({ page }) => {
  await login(page, "alice");
  await page.getByRole("button", { name: "Nouvelle conversation" }).click();
  await ask(page, "Quel est le loyer mensuel du bail ?");
  const answer = await ask(page, "Et sa durée ?");
  await expect(answer.getByText("Recherche effectuée pour : « Quelle est la durée du bail ? »")).toBeVisible();
  await expect(answer).toContainText("31/12/2026");
});

test("assistant : arrêt d'une génération en cours", async ({ page }) => {
  await login(page, "alice");
  await page.getByLabel("Posez votre question…").fill("Quelle est la durée de conservation des dossiers de crédit ?");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Arrêter" }).click();
  await expect(page.getByText("Génération interrompue.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Envoyer" })).toBeVisible();
});

test("droits : un utilisateur sans accès ne reçoit ni réponse ni source, ni écrans d'administration", async ({ page }) => {
  await login(page, "chloe");
  const answer = await ask(page, "Quel est le loyer mensuel du bail ?");
  await expect(answer).toContainText("ne permettent pas de répondre");
  await expect(answer).not.toContainText("450 000");
  await expect(page.locator(".cite")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Documents" })).toHaveCount(0);
  await page.goto("/administration");
  await expect(page.getByText("Vous n'avez pas accès à cette page.")).toBeVisible();
});

test("documents : exclure un document le retire des réponses, le réintégrer le rétablit", async ({ browser }) => {
  const admin = await (await browser.newContext()).newPage();
  await login(admin, "admin");
  await admin.getByRole("link", { name: "Documents" }).click();
  await admin.getByRole("searchbox", { name: "Rechercher par nom" }).fill("bail");
  await admin.getByRole("cell", { name: /contrat_bail_alpha/ }).click();
  const detail = admin.locator("aside.detail");
  await expect(detail.getByText("Historique des versions")).toBeVisible();
  await detail.getByRole("button", { name: "Exclure" }).click();
  await expect(detail.getByText("Exclu des recherches et des réponses.")).toBeVisible();

  const alice = await (await browser.newContext()).newPage();
  await login(alice, "alice");
  const answer = await ask(alice, "Quel est le loyer mensuel du bail ?");
  await expect(answer).not.toContainText("450 000");

  await detail.getByRole("button", { name: "Réintégrer" }).click();
  await expect(detail.getByText("Exclu des recherches et des réponses.")).toHaveCount(0);
  await alice.getByRole("button", { name: "Nouvelle conversation" }).click();
  await expect(await ask(alice, "Quel est le loyer mensuel du bail ?")).toContainText("450 000 FCFA");
});

test("correspondance des comptes : la proposition ne donne rien avant confirmation", async ({ browser }) => {
  const alice = await (await browser.newContext()).newPage();
  await login(alice, "alice");
  await expect(await ask(alice, "Quel est le taux d'endettement maximal ?")).not.toContainText("33 %");

  const admin = await (await browser.newContext()).newPage();
  await login(admin, "admin");
  await admin.goto("/administration?onglet=correspondances");
  await admin.getByLabel("Source").selectOption({ label: "GED (simulée) (Source simulée)" });
  const row = admin.getByRole("row", { name: /Alice Mensah/ });
  await expect(row.getByText("proposée")).toBeVisible();
  await row.getByRole("button", { name: "Confirmer" }).click();
  await expect(row.getByText("confirmée")).toBeVisible();

  await alice.getByRole("button", { name: "Nouvelle conversation" }).click();
  const answer = await ask(alice, "Quel est le taux d'endettement maximal ?");
  await expect(answer).toContainText("33 %");
  await answer.locator(".cite").first().click();
  await expect(alice.locator(".source").first()).toContainText("politique_credit_2026");
});

test("tableau de bord et thème sombre", async ({ page }) => {
  await login(page, "admin");
  await page.getByRole("link", { name: "Tableau de bord" }).click();
  await expect(page.getByText("Documents indexés")).toBeVisible();
  await expect(page.getByText("postgres ✓")).toBeVisible();
  const theme = page.getByRole("button", { name: "Changer de thème" });
  await theme.click(); // système → clair
  await theme.click(); // clair → sombre
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark"); // préférence retenue
});

// Dernier parcours : il remplace le modèle de l'installation par des modèles configurés.
test("IA hybride : choisir un modèle externe (scénario 14), puis couper l'externe (scénario 15)", async ({ browser }) => {
  const admin = await (await browser.newContext()).newPage();
  await login(admin, "admin");
  await admin.goto("/administration?onglet=ia");
  const endpoint = `${info().base_url}/demo-llm/v1`;
  for (const [kind, name, locality, key] of [
    ["openai_compatible", "Serveur IA interne", "local", ""],
    ["openai", "Service externe", "", "cle-de-demonstration"],
  ]) {
    await admin.getByLabel("Type").selectOption(kind);
    await admin.getByLabel("Nom", { exact: true }).fill(name);
    await admin.getByLabel("Adresse", { exact: true }).fill(endpoint);
    if (locality) await admin.getByLabel("Où (serveur compatible OpenAI)").selectOption(locality);
    if (key) await admin.getByLabel("Clé d'API (facultative)").fill(key);
    await admin.getByRole("button", { name: "Ajouter le fournisseur" }).click();
    await expect(admin.getByRole("cell", { name: name, exact: true })).toBeVisible();
  }
  await expect(admin.getByText("enregistrée (chiffrée)")).toBeVisible();
  await expect(admin.locator("body")).not.toContainText("cle-de-demonstration"); // jamais réaffichée
  for (const [provider, model, priority] of [
    ["Serveur IA interne", "demo-local", "10"],
    ["Service externe", "demo-externe", "20"],
  ]) {
    await admin.getByLabel("Fournisseur", { exact: true }).selectOption({ label: provider });
    await admin.getByLabel("Nom du modèle chez le fournisseur").fill(model);
    await admin.getByLabel("Priorité", { exact: true }).fill(priority);
    await admin.getByRole("button", { name: "Ajouter le modèle" }).click();
    const row = admin.getByRole("row", { name: new RegExp(model) });
    await row.getByRole("button", { name: "Tester" }).click();
    await expect(row.getByText("Disponible")).toBeVisible();
  }
  await admin.getByLabel(/IA externe autorisée/).check();
  await admin.getByLabel("Autoriser l'envoi des extraits de documents vers l'externe").check();
  await admin.getByRole("button", { name: "Enregistrer" }).first().click();
  await expect(admin.getByText("Politique enregistrée")).toBeVisible();

  const alice = await (await browser.newContext()).newPage();
  await login(alice, "alice");
  await alice.getByLabel("Modèle de réponse").selectOption({ label: "demo-externe (Modèle externe)" });
  await expect(alice.getByRole("note")).toContainText("seront envoyés à « demo-externe », un service externe");
  const answer = await ask(alice, "Quel est le loyer mensuel du bail ?");
  await expect(answer.getByText("Modèle externe · demo-externe")).toBeVisible();
  await expect(answer).toContainText("450 000 FCFA");

  await admin.getByLabel(/IA locale uniquement/).check();
  await admin.getByRole("button", { name: "Enregistrer" }).first().click();
  await expect(admin.getByText("Politique enregistrée")).toBeVisible();
  await alice.reload();
  await expect(alice.getByLabel("Modèle de réponse")).toHaveCount(0); // un seul modèle autorisé : pas de choix
  await alice.getByRole("button", { name: "Nouvelle conversation" }).click();
  const local = await ask(alice, "Quel est le loyer mensuel du bail ?");
  await expect(local.getByText("Modèle local · demo-local")).toBeVisible();
});
