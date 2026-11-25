// Textes de l'interface (ADR-0023) : regroupés ici pour une traduction ultérieure.
export const t = {
  product: "Universal RAG Engine",
  tagline: "Vos documents répondent, avec leurs sources.",
  login: {
    title: "Connexion",
    login: "Identifiant",
    password: "Mot de passe",
    submit: "Se connecter",
    pending: "Connexion…",
    invalid: "Identifiant ou mot de passe incorrect, ou compte temporairement verrouillé.",
    unavailable: "Le service est indisponible. Réessayez dans un instant.",
  },
  nav: {
    assistant: "Assistant",
    dashboard: "Tableau de bord",
    sources: "Sources",
    documents: "Documents",
    admin: "Administration",
    logout: "Se déconnecter",
    theme: "Changer de thème",
    themes: { system: "Thème du système", light: "Thème clair", dark: "Thème sombre" },
  },
  roles: {
    org_admin: "Administrateur",
    doc_admin: "Administrateur documentaire",
    user: "Utilisateur",
    auditor: "Auditeur",
    super_admin: "Super administrateur",
  } as Record<string, string>,
  aiMode: {
    local_only: "IA locale uniquement",
    hybrid: "IA locale et externe",
    cloud_allowed: "IA externe autorisée",
  } as Record<string, string>,
  errors: {
    generic: "Une erreur est survenue.",
    forbidden: "Vous n'avez pas accès à cette page.",
    notFound: "Page introuvable.",
  },
};
