// Préférence d'affichage (sans donnée sensible) : système, clair ou sombre.
export type Theme = "system" | "light" | "dark";
const KEY = "urag.theme";

export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // stockage indisponible : la préférence ne sera pas retenue
  }
}

export const nextTheme = (t: Theme): Theme => (t === "system" ? "light" : t === "light" ? "dark" : "system");
