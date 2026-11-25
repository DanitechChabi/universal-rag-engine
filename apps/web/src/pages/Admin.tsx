import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { api, del, post, put } from "../api";
import { useAuth } from "../auth";
import { formatDate, Status } from "../components/ui";
import { t } from "../i18n";
import { AdminAI } from "./AdminAI";

const m = t.admin;
const ROLES = ["user", "doc_admin", "org_admin", "auditor"];

type User = { id: string; login: string; display_name: string; status: string; roles: string[] };
type Space = { id: string; name: string; sources: number; grants: { principal_type: string; principal_id: string; name: string }[] };
type Identity = {
  id: string;
  kind: "user" | "group";
  external_id: string;
  display_name: string | null;
  login: string | null;
  email: string | null;
  memberships: number;
  link: { user_id: string; login: string; verified: boolean } | null;
};
type Job = { id: number; kind: string; status: string; attempts: number; last_error: string | null; created_at: string; finished_at: string | null };

function useNotice() {
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const view = notice && (
    <div className={`alert alert-${notice.tone}`} role="status">
      {notice.text}
    </div>
  );
  return { view, ok: (text: string) => setNotice({ tone: "ok", text }), error: (e: Error) => setNotice({ tone: "error", text: e.message }) };
}

export function Admin() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("onglet") ?? "utilisateurs";
  const tabs = [
    ["utilisateurs", m.tabs.users],
    ["espaces", m.tabs.spaces],
    ["correspondances", m.tabs.identities],
    ["ia", m.tabs.ai],
    ["taches", m.tabs.jobs],
  ];
  return (
    <div className="page">
      <h1>{t.nav.admin}</h1>
      <div className="tabs" role="tablist">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" type="button" aria-selected={tab === id} className="tab" onClick={() => setParams({ onglet: id })}>
            {label}
          </button>
        ))}
      </div>
      {tab === "utilisateurs" && <Users />}
      {tab === "espaces" && <Spaces />}
      {tab === "correspondances" && <Identities />}
      {tab === "ia" && <AdminAI />}
      {tab === "taches" && <Jobs />}
    </div>
  );
}

function Users() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const notice = useNotice();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<{ items: User[] }>("/users") });
  const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) => api(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => void refresh(),
    onError: notice.error,
  });
  const create = useMutation({
    mutationFn: (body: object) => post("/users", body),
    onSuccess: () => {
      notice.ok(m.userCreated);
      void refresh();
    },
    onError: notice.error,
  });

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    create.mutate({
      login: f.get("login"),
      display_name: f.get("display_name"),
      email: f.get("email") || null,
      password: f.get("password"),
      roles: ROLES.filter((r) => f.get(`role-${r}`)),
    });
    e.currentTarget.reset();
  }

  return (
    <>
      {notice.view}
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{m.login}</th>
              <th>{m.name}</th>
              <th>{m.roles}</th>
              <th>{m.status}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.data?.items.map((u) => (
              <tr key={u.id}>
                <td className="mono">{u.login}</td>
                <td>{u.display_name}</td>
                <td>
                  <div className="checks">
                    {ROLES.map((r) => (
                      <label key={r} className="check">
                        <input
                          type="checkbox"
                          checked={u.roles.includes(r)}
                          disabled={patch.isPending || (u.id === me?.user_id && r === "org_admin")}
                          onChange={(e) =>
                            patch.mutate({ id: u.id, body: { roles: e.target.checked ? [...u.roles, r] : u.roles.filter((x) => x !== r) } })
                          }
                        />
                        {t.roles[r]}
                      </label>
                    ))}
                  </div>
                </td>
                <td>
                  <Status value={u.status === "active" ? "active" : "disabled"} />
                </td>
                <td>
                  <div className="row-actions">
                  {u.id !== me?.user_id && (
                    <button
                      className="btn btn-ghost small"
                      type="button"
                      onClick={() => patch.mutate({ id: u.id, body: { status: u.status === "active" ? "disabled" : "active" } })}
                    >
                      {u.status === "active" ? m.disable : m.enable}
                    </button>
                  )}
                </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="card card-pad form-grid" onSubmit={submit}>
        <h2 className="span-all">{m.newUser}</h2>
        <div className="field">
          <label htmlFor="nu-login">{m.login}</label>
          <input className="input" id="nu-login" name="login" required minLength={2} autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor="nu-name">{m.name}</label>
          <input className="input" id="nu-name" name="display_name" required />
        </div>
        <div className="field">
          <label htmlFor="nu-email">{m.email}</label>
          <input className="input" id="nu-email" name="email" type="email" />
        </div>
        <div className="field">
          <label htmlFor="nu-password">{m.password}</label>
          <input className="input" id="nu-password" name="password" type="password" required minLength={12} autoComplete="new-password" />
        </div>
        <div className="checks span-all">
          {ROLES.map((r) => (
            <label key={r} className="check">
              <input type="checkbox" name={`role-${r}`} defaultChecked={r === "user"} />
              {t.roles[r]}
            </label>
          ))}
        </div>
        <div>
          <button className="btn btn-primary" type="submit" disabled={create.isPending}>
            {m.create}
          </button>
        </div>
      </form>
    </>
  );
}

function Spaces() {
  const qc = useQueryClient();
  const notice = useNotice();
  const spaces = useQuery({ queryKey: ["spaces"], queryFn: () => api<{ items: Space[] }>("/spaces") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<{ items: User[] }>("/users") });
  const [editing, setEditing] = useState<string | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const save = useMutation({
    mutationFn: (id: string) => put(`/spaces/${id}/grants`, [...chosen].map((p) => ({ principal_type: "user", principal_id: p }))),
    onSuccess: () => {
      setEditing(null);
      notice.ok(m.grantsSaved);
      void qc.invalidateQueries({ queryKey: ["spaces"] });
    },
    onError: notice.error,
  });
  const create = useMutation({
    mutationFn: (name: string) => post("/spaces", { name }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["spaces"] }),
    onError: notice.error,
  });

  return (
    <>
      <p className="muted small">{m.spacesIntro}</p>
      {notice.view}
      {spaces.data?.items.map((s) => (
        <section key={s.id} className="card card-pad stack">
          <div className="page-head">
            <h2>{s.name}</h2>
            <span className="small muted">{m.sourcesCount(s.sources)}</span>
          </div>
          {editing === s.id ? (
            <>
              <div className="checks">
                {users.data?.items.map((u) => (
                  <label key={u.id} className="check">
                    <input
                      type="checkbox"
                      checked={chosen.has(u.id)}
                      onChange={(e) => {
                        const next = new Set(chosen);
                        if (e.target.checked) next.add(u.id);
                        else next.delete(u.id);
                        setChosen(next);
                      }}
                    />
                    {u.display_name}
                  </label>
                ))}
              </div>
              <div className="row-actions start">
                <button className="btn btn-primary small" type="button" onClick={() => save.mutate(s.id)}>
                  {m.save}
                </button>
                <button className="btn btn-ghost small" type="button" onClick={() => setEditing(null)}>
                  {m.cancel}
                </button>
              </div>
            </>
          ) : (
            <div className="detail-badges">
              {s.grants.length === 0 && <span className="small muted">{m.noGrant}</span>}
              {s.grants.map((g) => (
                <span key={g.principal_id} className="badge badge-accent">
                  {g.name}
                </span>
              ))}
              <button
                className="btn btn-ghost small"
                type="button"
                onClick={() => {
                  setChosen(new Set(s.grants.filter((g) => g.principal_type === "user").map((g) => g.principal_id)));
                  setEditing(s.id);
                }}
              >
                {m.editGrants}
              </button>
            </div>
          )}
        </section>
      ))}
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          const input = e.currentTarget.elements.namedItem("space") as HTMLInputElement;
          if (input.value.trim()) create.mutate(input.value.trim());
          input.value = "";
        }}
      >
        <input className="input" name="space" placeholder={m.newSpace} aria-label={m.newSpace} />
        <button className="btn" type="submit">
          {m.create}
        </button>
      </form>
    </>
  );
}

function Identities() {
  const qc = useQueryClient();
  const notice = useNotice();
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<{ items: { id: string; name: string; kind: string }[] }>("/sources") });
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<{ items: User[] }>("/users") });
  const [source, setSource] = useState("");
  const current = source || sources.data?.items[0]?.id || "";
  const ids = useQuery({
    queryKey: ["identities", current],
    queryFn: () => api<{ items: Identity[]; to_confirm: number; unlinked_users: number }>(`/sources/${current}/identities`),
    enabled: !!current,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ["identities", current] });
  const act = useMutation({
    mutationFn: async (a: { kind: "confirm" | "unlink" | "link"; id: string; user?: string }) => {
      if (a.kind === "confirm") await post(`/principal-links/${a.id}/confirm`);
      else if (a.kind === "unlink") await del(`/principal-links/${a.id}`);
      else await put("/principal-links", { user_id: a.user, external_principal_id: a.id });
    },
    onSuccess: () => void refresh(),
    onError: notice.error,
  });
  const importCsv = useMutation({
    mutationFn: (csv: string) => post<{ imported: number }>(`/sources/${current}/principal-links/import`, { csv }),
    onSuccess: (r) => {
      notice.ok(m.imported(r.imported));
      void refresh();
    },
    onError: notice.error,
  });

  return (
    <>
      <p className="muted small">{m.identitiesIntro}</p>
      <div className="filters">
        <select className="input" aria-label={t.documents.source} value={current} onChange={(e) => setSource(e.target.value)}>
          {sources.data?.items.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name} ({t.kinds[s.kind] ?? s.kind})
            </option>
          ))}
        </select>
      </div>
      {notice.view}
      {ids.data && (
        <div className="detail-badges">
          <span className={`badge ${ids.data.to_confirm ? "badge-warn" : "badge-ok"}`}>{m.toConfirm(ids.data.to_confirm)}</span>
          <span className="badge">{m.unlinked(ids.data.unlinked_users)}</span>
        </div>
      )}
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{m.external}</th>
              <th>{m.kind}</th>
              <th>{m.localAccount}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ids.data?.items.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  {m.noIdentity}
                </td>
              </tr>
            )}
            {ids.data?.items.map((i) => (
              <tr key={i.id}>
                <td>
                  <strong>{i.display_name ?? i.external_id}</strong>
                  <div className="small muted">{[i.login, i.email].filter(Boolean).join(" · ")}</div>
                </td>
                <td>{i.kind === "user" ? m.user : m.group(i.memberships)}</td>
                <td>
                  {i.link ? (
                    <>
                      <span className="mono">{i.link.login}</span>{" "}
                      <span className={`badge ${i.link.verified ? "badge-ok" : "badge-warn"}`}>{i.link.verified ? m.confirmed : m.proposed}</span>
                    </>
                  ) : i.kind === "user" ? (
                    <select
                      className="input input-sm"
                      aria-label={m.linkTo}
                      value=""
                      onChange={(e) => e.target.value && act.mutate({ kind: "link", id: i.id, user: e.target.value })}
                    >
                      <option value="">{m.linkTo}</option>
                      {users.data?.items.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.display_name} ({u.login})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="small muted">{m.groupNote}</span>
                  )}
                </td>
                <td>
                  <div className="row-actions">
                  {i.link && !i.link.verified && (
                    <button className="btn btn-primary small" type="button" onClick={() => act.mutate({ kind: "confirm", id: i.id })}>
                      {m.confirm}
                    </button>
                  )}
                  {i.link && (
                    <button className="btn btn-ghost btn-danger small" type="button" onClick={() => act.mutate({ kind: "unlink", id: i.id })}>
                      {m.unlink}
                    </button>
                  )}
                </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form
        className="card card-pad stack"
        onSubmit={(e) => {
          e.preventDefault();
          const area = e.currentTarget.elements.namedItem("csv") as HTMLTextAreaElement;
          if (area.value.trim()) importCsv.mutate(area.value);
        }}
      >
        <h2>{m.importTitle}</h2>
        <p className="small muted">{m.importHelp}</p>
        <textarea className="input mono" name="csv" rows={4} placeholder={"login_local;identifiant_externe\nalice.mensah;42"} aria-label={m.importTitle} />
        <div>
          <button className="btn" type="submit" disabled={!current || importCsv.isPending}>
            {m.import}
          </button>
        </div>
      </form>
    </>
  );
}

function Jobs() {
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => api<{ items: Job[] }>("/admin/jobs"), refetchInterval: 5000 });
  return (
    <div className="card table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{m.job}</th>
            <th>{m.status}</th>
            <th className="num">{m.attempts}</th>
            <th>{m.created}</th>
            <th>{m.finished}</th>
            <th>{m.lastError}</th>
          </tr>
        </thead>
        <tbody>
          {jobs.data?.items.map((j) => (
            <tr key={j.id}>
              <td>{m.jobKinds[j.kind] ?? j.kind}</td>
              <td>
                <span className={`badge ${j.status === "succeeded" ? "badge-ok" : j.status === "failed" ? "badge-danger" : "badge-accent"}`}>
                  {m.jobStatus[j.status] ?? j.status}
                </span>
              </td>
              <td className="num">{j.attempts}</td>
              <td>{formatDate(j.created_at, true)}</td>
              <td>{formatDate(j.finished_at, true)}</td>
              <td className="small text-danger">{j.last_error ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
