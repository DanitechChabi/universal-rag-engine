import { t } from "../i18n";

const TONE: Record<string, string> = {
  indexed: "badge-ok",
  active: "badge-ok",
  complete: "badge-ok",
  indexed_with_warning: "badge-warn",
  pending: "badge-accent",
  processing: "badge-accent",
  uncertain: "badge-warn",
  disabled: "",
  failed: "badge-danger",
  error: "badge-danger",
  excluded: "",
};

export function Status({ value }: { value: string }) {
  return <span className={`badge ${TONE[value] ?? ""}`}>{t.status[value] ?? value}</span>;
}

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}
