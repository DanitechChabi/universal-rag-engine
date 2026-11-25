import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../api";
import { formatDate } from "../components/ui";
import { t } from "../i18n";

type Dash = {
  sources: { active: number; error: number };
  documents: { by_status: Record<string, number>; total: number; failed: number };
  fragments: number;
  jobs: { queued: number; running: number; failed_24h: number };
  services: Record<string, string>;
  model: { name: string; locality: string } | null;
  policy: string;
  usage_30d: { answers: number; external: number; tokens_in: number; tokens_out: number };
  activity: { action: string; outcome: string; actor: string | null; at: string }[];
};

const b = t.dashboard;
const n = (v: number) => v.toLocaleString("fr-FR");

export function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dash>("/admin/dashboard"), refetchInterval: 10000 });
  const d = q.data;
  if (!d) return <div className="center">Chargement…</div>;
  const indexed = (d.documents.by_status.indexed ?? 0) + (d.documents.by_status.indexed_with_warning ?? 0);
  const errors = d.documents.failed + d.sources.error + d.jobs.failed_24h;
  const tiles = [
    { label: b.sources, value: n(d.sources.active), to: "/sources" },
    { label: b.documents, value: n(indexed), hint: b.ofTotal(d.documents.total), to: "/documents" },
    { label: b.fragments, value: n(d.fragments) },
    { label: b.jobs, value: n(d.jobs.queued + d.jobs.running), hint: b.jobsHint(d.jobs.running, d.jobs.queued) },
    { label: b.errors, value: n(errors), tone: errors ? "danger" : "ok", to: errors ? "/documents?status=failed" : undefined },
  ];

  return (
    <div className="page">
      <h1>{t.nav.dashboard}</h1>
      <div className="tiles">
        {tiles.map((x) => {
          const body = (
            <>
              <div className="tile-label">{x.label}</div>
              <div className={`tile-value ${x.tone === "danger" ? "text-danger" : ""}`}>{x.value}</div>
              {x.hint && <div className="small muted">{x.hint}</div>}
            </>
          );
          return x.to ? (
            <Link key={x.label} to={x.to} className="card tile tile-link">
              {body}
            </Link>
          ) : (
            <div key={x.label} className="card tile">
              {body}
            </div>
          );
        })}
      </div>
      <div className="grid-2">
        <section className="card card-pad stack">
          <h2>{b.platform}</h2>
          <dl className="meta">
            <dt>{b.services}</dt>
            <dd className="detail-badges">
              {Object.entries(d.services).map(([k, v]) => (
                <span key={k} className={`badge ${v === "ok" ? "badge-ok" : "badge-danger"}`}>
                  {k} {v === "ok" ? "✓" : "✗"}
                </span>
              ))}
            </dd>
            <dt>{b.model}</dt>
            <dd>
              {d.model ? (
                <>
                  {d.model.name}{" "}
                  <span className={`badge ${d.model.locality === "local" ? "badge-ok" : "badge-warn"}`}>
                    {d.model.locality === "local" ? t.assistant.local : t.assistant.external}
                  </span>
                </>
              ) : (
                "—"
              )}
            </dd>
            <dt>{b.policy}</dt>
            <dd>{t.aiMode[d.policy] ?? d.policy}</dd>
            <dt>{b.usage}</dt>
            <dd>
              {b.answers(d.usage_30d.answers, d.usage_30d.external)}
              <div className="small muted">{b.tokens(d.usage_30d.tokens_in, d.usage_30d.tokens_out)}</div>
            </dd>
          </dl>
        </section>
        <section className="card card-pad stack">
          <h2>{b.activity}</h2>
          <ul className="activity">
            {d.activity.map((a, i) => (
              <li key={i}>
                <span className={a.outcome === "success" ? "" : "text-danger"}>{b.actions[a.action] ?? a.action}</span>
                <span className="small muted">
                  {a.actor ?? b.system} · {formatDate(a.at, true)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
