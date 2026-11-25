import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, del, post, put } from "../api";
import { formatDate } from "../components/ui";
import { t } from "../i18n";

const m = t.ai;

type Policy = {
  mode: "local_only" | "hybrid" | "cloud_allowed";
  allow_external_questions: boolean;
  allow_external_documents: boolean;
  allow_fallback_to_external: boolean;
  notify_user_on_external: boolean;
};
type Provider = { id: string; kind: string; name: string; endpoint: string | null; locality: string; enabled: boolean; key_configured: boolean };
type Model = {
  id: string;
  provider_id: string;
  name: string;
  priority: number;
  enabled: boolean;
  available: boolean;
  last_checked_at: string | null;
  locality: string;
  input_cost_per_mtok: number | null;
  output_cost_per_mtok: number | null;
};
type Limit = { period: "day" | "month"; max_tokens: number | null; max_cost: number | null; alert_ratio: number; disable_on_exceed: boolean };
type LimitStatus = { period: string; used_tokens: number; used_cost: number; max_tokens: number | null; max_cost: number | null; ratio: number; alert: boolean; exceeded: boolean };
type Overview = {
  policy: Policy;
  providers: Provider[];
  models: Model[];
  limits: Limit[];
  limits_status: LimitStatus[];
  usage_month: { model: string; locality: string; calls: number; tokens_in: number; tokens_out: number; cost: number | null }[];
};

const num = (v: number | null | undefined) => (v == null ? "—" : v.toLocaleString("fr-FR"));
const money = (v: number | null | undefined) => (v == null ? "—" : `${v.toLocaleString("fr-FR", { maximumFractionDigits: 4 })} $`);

export function AdminAI() {
  const qc = useQueryClient();
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [keyFor, setKeyFor] = useState<string | null>(null);
  const data = useQuery({ queryKey: ["ai"], queryFn: () => api<Overview>("/admin/ai") });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["ai"] });
    void qc.invalidateQueries({ queryKey: ["models"] });
  };
  const run = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: (r) => {
      if (r && typeof r === "object" && "available" in r) {
        const res = r as { available: boolean; detail: string };
        setNotice({ tone: res.available ? "ok" : "error", text: `${m.testResult} : ${res.detail}` });
      }
      refresh();
    },
    onError: (e: Error) => setNotice({ tone: "error", text: e.message }),
  });
  const d = data.data;
  if (!d) return <div className="center">Chargement…</div>;
  const providerName = (id: string) => d.providers.find((p) => p.id === id)?.name ?? "—";

  function savePolicy(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const mode = String(f.get("mode")) as Policy["mode"];
    const external = mode !== "local_only";
    run.mutate(() =>
      put("/admin/ai/policy", {
        mode,
        allow_external_questions: external && f.get("q") === "on",
        allow_external_documents: external && f.get("d") === "on",
        allow_fallback_to_external: external && f.get("f") === "on",
        notify_user_on_external: f.get("n") === "on",
      }),
    );
    setNotice({ tone: "ok", text: m.policySaved });
  }

  function addProvider(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const kind = String(f.get("kind"));
    run.mutate(() =>
      post("/admin/ai/providers", {
        kind,
        name: f.get("name"),
        endpoint: f.get("endpoint") || null,
        locality: kind === "openai_compatible" ? f.get("locality") : undefined,
        api_key: f.get("api_key") || null,
      }),
    );
    e.currentTarget.reset();
  }

  function addModel(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const n = (k: string) => (f.get(k) ? Number(f.get(k)) : null);
    run.mutate(() =>
      post("/admin/ai/models", {
        provider_id: f.get("provider_id"),
        name: f.get("name"),
        priority: n("priority") ?? 100,
        input_cost_per_mtok: n("in"),
        output_cost_per_mtok: n("out"),
      }),
    );
    e.currentTarget.reset();
  }

  function saveLimits(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const limits = (["day", "month"] as const)
      .map((p) => ({
        period: p,
        max_tokens: f.get(`${p}-tokens`) ? Number(f.get(`${p}-tokens`)) : null,
        max_cost: f.get(`${p}-cost`) ? Number(f.get(`${p}-cost`)) : null,
        alert_ratio: 0.8,
        disable_on_exceed: true,
      }))
      .filter((l) => l.max_tokens || l.max_cost);
    run.mutate(() => put("/admin/ai/limits", limits));
    setNotice({ tone: "ok", text: m.limitsSaved });
  }

  const limit = (p: "day" | "month") => d.limits.find((l) => l.period === p);

  return (
    <>
      {notice && (
        <div className={`alert alert-${notice.tone}`} role="status">
          {notice.text}
        </div>
      )}

      <form className="card card-pad stack" onSubmit={savePolicy} key={JSON.stringify(d.policy)}>
        <h2>{m.policy}</h2>
        <div className="radios">
          {(["local_only", "hybrid", "cloud_allowed"] as const).map((mode) => (
            <label key={mode} className="radio-card">
              <input type="radio" name="mode" value={mode} defaultChecked={d.policy.mode === mode} />
              <span>
                <strong>{t.aiMode[mode]}</strong>
                <span className="small muted">{m.modeHelp[mode]}</span>
              </span>
            </label>
          ))}
        </div>
        <div className="checks">
          <label className="check"><input type="checkbox" name="q" defaultChecked={d.policy.allow_external_questions} />{m.allowQuestions}</label>
          <label className="check"><input type="checkbox" name="d" defaultChecked={d.policy.allow_external_documents} />{m.allowDocuments}</label>
          <label className="check"><input type="checkbox" name="f" defaultChecked={d.policy.allow_fallback_to_external} />{m.allowFallback}</label>
          <label className="check"><input type="checkbox" name="n" defaultChecked={d.policy.notify_user_on_external} />{m.notify}</label>
        </div>
        <p className="small muted">{m.policyNote}</p>
        <div><button className="btn btn-primary" type="submit">{m.save}</button></div>
      </form>

      <section className="card card-pad stack">
        <h2>{m.models}</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>{m.model}</th><th>{m.provider}</th><th>{m.locality}</th><th className="num">{m.priority}</th><th>{m.prices}</th><th>{m.state}</th><th /></tr>
            </thead>
            <tbody>
              {d.models.length === 0 && <tr><td colSpan={7} className="muted">{m.noModel}</td></tr>}
              {d.models.map((x) => (
                <tr key={x.id}>
                  <td className="mono">{x.name}</td>
                  <td>{providerName(x.provider_id)}</td>
                  <td><span className={`badge ${x.locality === "local" ? "badge-ok" : "badge-warn"}`}>{x.locality === "local" ? m.local : m.external}</span></td>
                  <td className="num">{x.priority}</td>
                  <td className="small">{x.input_cost_per_mtok != null || x.output_cost_per_mtok != null ? `${money(x.input_cost_per_mtok)} / ${money(x.output_cost_per_mtok)}` : "—"}</td>
                  <td>
                    <span className={`badge ${x.available ? "badge-ok" : "badge-danger"}`}>{x.available ? m.available : m.notTested}</span>
                    {!x.enabled && <span className="badge">{m.disabled}</span>}
                    {x.last_checked_at && <div className="small muted">{formatDate(x.last_checked_at, true)}</div>}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="btn small" type="button" onClick={() => run.mutate(() => post(`/admin/ai/models/${x.id}/test`))}>{m.test}</button>
                      <button className="btn btn-ghost small" type="button" onClick={() => run.mutate(() => api(`/admin/ai/models/${x.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !x.enabled }) }))}>
                        {x.enabled ? m.disable : m.enable}
                      </button>
                      <button className="btn btn-ghost btn-danger small" type="button" onClick={() => window.confirm(m.confirmDelete(x.name)) && run.mutate(() => del(`/admin/ai/models/${x.id}`))}>{m.remove}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form className="form-grid" onSubmit={addModel}>
          <div className="field"><label htmlFor="am-provider">{m.provider}</label>
            <select className="input" id="am-provider" name="provider_id" required>
              {d.providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
          <div className="field"><label htmlFor="am-name">{m.modelName}</label><input className="input" id="am-name" name="name" required placeholder="qwen2.5:14b, claude-opus-5-5, google/gemma-4-31b-it:free…" /></div>
          <div className="field"><label htmlFor="am-priority">{m.priority}</label><input className="input" id="am-priority" name="priority" type="number" defaultValue={100} /></div>
          <div className="field"><label htmlFor="am-in">{m.priceIn}</label><input className="input" id="am-in" name="in" type="number" step="0.0001" min="0" /></div>
          <div className="field"><label htmlFor="am-out">{m.priceOut}</label><input className="input" id="am-out" name="out" type="number" step="0.0001" min="0" /></div>
          <div className="field"><label>&nbsp;</label><button className="btn" type="submit" disabled={d.providers.length === 0}>{m.addModel}</button></div>
        </form>
        <p className="small muted">{m.modelNote}</p>
      </section>

      <section className="card card-pad stack">
        <h2>{m.providers}</h2>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>{m.name}</th><th>{m.kind}</th><th>{m.endpoint}</th><th>{m.locality}</th><th>{m.key}</th><th /></tr></thead>
            <tbody>
              {d.providers.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong>{!p.enabled && <div className="small muted">{m.disabled}</div>}</td>
                  <td>{m.kinds[p.kind] ?? p.kind}</td>
                  <td className="mono small">{p.endpoint ?? m.defaultEndpoint}</td>
                  <td><span className={`badge ${p.locality === "local" ? "badge-ok" : "badge-warn"}`}>{p.locality === "local" ? m.local : m.external}</span></td>
                  <td>{p.key_configured ? m.keySaved : "—"}</td>
                  <td>
                    <div className="row-actions">
                      {keyFor === p.id ? (
                        <form
                          className="inline-form"
                          onSubmit={(e) => {
                            e.preventDefault();
                            const input = e.currentTarget.elements.namedItem("key") as HTMLInputElement;
                            if (input.value) run.mutate(() => api(`/admin/ai/providers/${p.id}`, { method: "PATCH", body: JSON.stringify({ api_key: input.value }) }));
                            setKeyFor(null);
                          }}
                        >
                          <input className="input input-sm" name="key" type="password" autoComplete="off" aria-label={m.newKey} placeholder={m.newKey} autoFocus />
                          <button className="btn small" type="submit">{m.save}</button>
                        </form>
                      ) : (
                        <button className="btn btn-ghost small" type="button" onClick={() => setKeyFor(p.id)}>{m.replaceKey}</button>
                      )}
                      <button className="btn btn-ghost btn-danger small" type="button" onClick={() => window.confirm(m.confirmDelete(p.name)) && run.mutate(() => del(`/admin/ai/providers/${p.id}`))}>{m.remove}</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form className="form-grid" onSubmit={addProvider}>
          <div className="field"><label htmlFor="ap-kind">{m.kind}</label>
            <select className="input" id="ap-kind" name="kind">
              {Object.entries(m.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></div>
          <div className="field"><label htmlFor="ap-name">{m.name}</label><input className="input" id="ap-name" name="name" required /></div>
          <div className="field"><label htmlFor="ap-endpoint">{m.endpoint}</label><input className="input" id="ap-endpoint" name="endpoint" placeholder="http://serveur-ia:11434" /></div>
          <div className="field"><label htmlFor="ap-locality">{m.localityCompat}</label>
            <select className="input" id="ap-locality" name="locality"><option value="local">{m.local}</option><option value="external">{m.external}</option></select></div>
          <div className="field"><label htmlFor="ap-key">{m.apiKey}</label><input className="input" id="ap-key" name="api_key" type="password" autoComplete="off" /></div>
          <div className="field"><label>&nbsp;</label><button className="btn" type="submit">{m.addProvider}</button></div>
        </form>
        <p className="small muted">{m.keyNote}</p>
      </section>

      <form className="card card-pad stack" onSubmit={saveLimits} key={JSON.stringify(d.limits)}>
        <h2>{m.limits}</h2>
        <p className="small muted">{m.limitsNote}</p>
        <div className="form-grid">
          {(["day", "month"] as const).map((p) => (
            <fieldset key={p} className="fieldset">
              <legend>{m.period[p]}</legend>
              <div className="field"><label htmlFor={`${p}-tokens`}>{m.maxTokens}</label><input className="input" id={`${p}-tokens`} name={`${p}-tokens`} type="number" min="1" defaultValue={limit(p)?.max_tokens ?? ""} /></div>
              <div className="field"><label htmlFor={`${p}-cost`}>{m.maxCost}</label><input className="input" id={`${p}-cost`} name={`${p}-cost`} type="number" min="0.01" step="0.01" defaultValue={limit(p)?.max_cost ?? ""} /></div>
            </fieldset>
          ))}
        </div>
        {d.limits_status.map((s) => (
          <div key={s.period} className={`alert ${s.exceeded ? "alert-error" : s.alert ? "alert-warn" : "alert-ok"} small`}>
            {m.period[s.period as "day" | "month"]} : {m.used(num(s.used_tokens), money(s.used_cost), Math.round(s.ratio * 100))}
            {s.exceeded ? ` — ${m.exceeded}` : s.alert ? ` — ${m.alert}` : ""}
          </div>
        ))}
        <div><button className="btn btn-primary" type="submit">{m.save}</button></div>
      </form>

      <section className="card card-pad stack">
        <h2>{m.usage}</h2>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>{m.model}</th><th>{m.locality}</th><th className="num">{m.calls}</th><th className="num">{m.tokensIn}</th><th className="num">{m.tokensOut}</th><th className="num">{m.cost}</th></tr></thead>
            <tbody>
              {d.usage_month.length === 0 && <tr><td colSpan={6} className="muted">{m.noUsage}</td></tr>}
              {d.usage_month.map((u, i) => (
                <tr key={i}>
                  <td>{u.model}</td>
                  <td>{u.locality === "local" ? m.local : m.external}</td>
                  <td className="num">{num(u.calls)}</td>
                  <td className="num">{num(u.tokens_in)}</td>
                  <td className="num">{num(u.tokens_out)}</td>
                  <td className="num">{money(u.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="small muted">{m.costNote}</p>
      </section>
    </>
  );
}
