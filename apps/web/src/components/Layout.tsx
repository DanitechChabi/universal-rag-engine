import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { CAN_ASK, DOC_ADMIN, ORG_ADMIN, useAuth } from "../auth";
import { t } from "../i18n";
import { applyTheme, nextTheme, readTheme, type Theme } from "../theme";
import { IconAdmin, IconChat, IconDashboard, IconDocuments, IconLogout, IconSources, IconTheme } from "./icons";

export function Layout() {
  const { me, logout, can } = useAuth();
  const [theme, setTheme] = useState<Theme>(readTheme);

  const links = [
    { to: "/", label: t.nav.assistant, icon: <IconChat />, show: can(...CAN_ASK) },
    { to: "/tableau-de-bord", label: t.nav.dashboard, icon: <IconDashboard />, show: can(...DOC_ADMIN) },
    { to: "/sources", label: t.nav.sources, icon: <IconSources />, show: can(...DOC_ADMIN) },
    { to: "/documents", label: t.nav.documents, icon: <IconDocuments />, show: can(...DOC_ADMIN) },
    { to: "/administration", label: t.nav.admin, icon: <IconAdmin />, show: can(...ORG_ADMIN) },
  ].filter((l) => l.show);

  function toggleTheme() {
    const next = nextTheme(theme);
    applyTheme(next);
    setTheme(next);
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <img src="/logo.svg" alt="" width={28} height={28} />
          <div className="brand-text">
            <div className="brand-name">{t.product}</div>
            <div className="brand-tag">{me?.organization}</div>
          </div>
        </div>
        <nav className="nav" aria-label="Navigation principale">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.to === "/"} title={l.label}>
              {l.icon}
              <span>{l.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user">
            <span className="user-name">{me?.display_name}</span>
            <span className="small muted">{me?.roles.map((r) => t.roles[r] ?? r).join(", ")}</span>
          </div>
          <span className={`badge ${me?.ai_mode === "local_only" ? "badge-ok" : "badge-warn"}`} title="Politique d'IA de l'organisation">
            {t.aiMode[me?.ai_mode ?? "local_only"]}
          </span>
          <div className="foot-actions">
            <button className="btn btn-ghost" type="button" onClick={toggleTheme} title={`${t.nav.theme} (${t.nav.themes[theme]})`} aria-label={t.nav.theme}>
              <IconTheme />
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => void logout()} title={t.nav.logout} aria-label={t.nav.logout}>
              <IconLogout />
            </button>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
