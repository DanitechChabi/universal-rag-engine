import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, del, post } from "../api";
import { formatDate, Status } from "../components/ui";
import { t } from "../i18n";

type Source = {
  id: string;
  name: string;
  kind: string;
  status: string;
  enabled: boolean;
  last_sync_at: string | null;
  documents: number;
  errors: number;
};

const s = t.sources;

export function Sources() {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<{ tone: "ok" | "error" | "warn"; text: string } | null>(null);
  const sources = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<{ items: Source[] }>("/sources"),
    refetchInterval: 5000, // l'avancement des synchronisations apparaît sans recharger
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["sources"] });
  const action = useMutation({
    mutationFn: async ({ src, kind }: { src: Source; kind: "sync" | "test" | "toggle" | "remove" }) => {
      if (kind === "sync") {
        const r = await post<{ already_queued: boolean }>(`/sources/${src.id}/sync`);
        return { tone: "ok" as const, text: r.already_queued ? s.syncAlready : s.syncQueued };
      }
      if (kind === "test") {
        const r = await post<{ ok: boolean; message: string }>(`/sources/${src.id}/test`);
        return { tone: r.ok ? ("ok" as const) : ("error" as const), text: `${src.name} : ${r.message}` };
      }
      if (kind === "toggle") {
        await post(`/sources/${src.id}/${src.enabled ? "disable" : "enable"}`);
        return null;
      }
      await del(`/sources/${src.id}`);
      return null;
    },
    onSuccess: (n) => {
      setNotice(n);
      void refresh();
    },
    onError: (e: Error) => setNotice({ tone: "error", text: e.message || t.errors.generic }),
  });

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{s.title}</h1>
          <p className="muted small">{s.intro}</p>
        </div>
      </div>
      {notice && (
        <div className={`alert alert-${notice.tone}`} role="status">
          {notice.text}
        </div>
      )}
      <div className="card table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{s.name}</th>
              <th>{s.kind}</th>
              <th>{s.status}</th>
              <th>{s.lastSync}</th>
              <th className="num">{s.documents}</th>
              <th className="num">{s.errors}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sources.data?.items.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  {s.empty}
                </td>
              </tr>
            )}
            {sources.data?.items.map((src) => (
              <tr key={src.id}>
                <td>
                  <strong>{src.name}</strong>
                  {!src.enabled && <div className="small muted">{s.disabledNote}</div>}
                </td>
                <td>{t.kinds[src.kind] ?? src.kind}</td>
                <td>
                  <Status value={src.enabled ? src.status : "disabled"} />
                </td>
                <td>{src.last_sync_at ? formatDate(src.last_sync_at, true) : s.never}</td>
                <td className="num">
                  <Link to={`/documents?source=${src.id}`}>{src.documents}</Link>
                </td>
                <td className="num">
                  {src.errors > 0 ? <Link to={`/documents?source=${src.id}&status=failed`}>{src.errors}</Link> : 0}
                </td>
                <td>
                  <div className="row-actions">
                    <button className="btn small" type="button" disabled={!src.enabled || action.isPending} onClick={() => action.mutate({ src, kind: "sync" })}>
                      {s.sync}
                    </button>
                    <button className="btn btn-ghost small" type="button" disabled={action.isPending} onClick={() => action.mutate({ src, kind: "test" })}>
                      {s.test}
                    </button>
                    <button className="btn btn-ghost small" type="button" disabled={action.isPending} onClick={() => action.mutate({ src, kind: "toggle" })}>
                      {src.enabled ? s.disable : s.enable}
                    </button>
                    <button
                      className="btn btn-ghost btn-danger small"
                      type="button"
                      disabled={action.isPending}
                      onClick={() => window.confirm(s.confirmRemove(src.name)) && action.mutate({ src, kind: "remove" })}
                    >
                      {s.remove}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
