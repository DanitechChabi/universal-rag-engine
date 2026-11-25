import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, API, del, post } from "../api";
import { IconOpen } from "../components/icons";
import { formatDate, Status } from "../components/ui";
import { t } from "../i18n";

type Doc = {
  id: string;
  title: string;
  filename: string | null;
  extension: string | null;
  status: string;
  status_detail: string | null;
  acl_status: string;
  access_key_count: number;
  deny_key_count: number;
  excluded: boolean;
  source_modified_at: string | null;
  source_version: string | null;
  source_id: string;
  source: string;
  chunk_count: number | null;
};

type Version = {
  id: string;
  current: boolean;
  status: string;
  chunk_count: number;
  page_count: number | null;
  ocr_engine: string | null;
  warnings: string[];
  error: string | null;
  created_at: string;
  pipeline_version: number;
  context: string | null;
};

type Detail = Doc & {
  mime_type: string | null;
  size_bytes: number | null;
  doc_class: string | null;
  location: string | null;
  access: { status: string; keys: number; deny_keys: number; reason: string | null; synced_at: string | null };
  versions: Version[];
};

const d = t.documents;
const PAGE = 50;
const STATUSES = ["indexed", "indexed_with_warning", "pending", "processing", "failed", "excluded"];

export function Documents() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const status = params.get("status") ?? "";
  const source = params.get("source") ?? "";
  const offset = Number(params.get("offset") ?? 0);
  const selected = params.get("doc");
  const queryClient = useQueryClient();

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "doc" && key !== "offset") next.delete("offset");
    setParams(next, { replace: key === "q" });
  }

  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<{ items: { id: string; name: string }[] }>("/sources") });
  const list = useQuery({
    queryKey: ["documents", q, status, source, offset],
    queryFn: () => {
      const search = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
      if (q) search.set("q", q);
      if (status) search.set("status", status);
      if (source) search.set("source_id", source);
      return api<{ items: Doc[]; total: number }>(`/documents?${search}`);
    },
    placeholderData: keepPreviousData,
    refetchInterval: 5000,
  });

  return (
    <div className={`page-split ${selected ? "with-detail" : ""}`}>
      <div className="page">
        <div className="page-head">
          <h1>{d.title}</h1>
          <span className="muted small">{list.data ? d.total(list.data.total) : ""}</span>
        </div>
        <div className="filters">
          <input className="input" type="search" placeholder={d.search} aria-label={d.search} value={q} onChange={(e) => setParam("q", e.target.value)} />
          <select className="input" aria-label={d.status} value={status} onChange={(e) => setParam("status", e.target.value)}>
            <option value="">{d.allStatuses}</option>
            {STATUSES.map((x) => (
              <option key={x} value={x}>
                {t.status[x]}
              </option>
            ))}
          </select>
          <select className="input" aria-label={d.source} value={source} onChange={(e) => setParam("source", e.target.value)}>
            <option value="">{d.allSources}</option>
            {sources.data?.items.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </div>
        <div className="card table-wrap">
          <table className="table table-click">
            <thead>
              <tr>
                <th>{d.name}</th>
                <th className="col-optional">{d.source}</th>
                <th>{d.format}</th>
                <th className="col-optional">{d.modified}</th>
                <th>{d.status}</th>
                <th>{d.access}</th>
                <th className="num">{d.chunks}</th>
              </tr>
            </thead>
            <tbody>
              {list.data?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    {d.empty}
                  </td>
                </tr>
              )}
              {list.data?.items.map((doc) => (
                <tr key={doc.id} aria-selected={doc.id === selected} tabIndex={0} onClick={() => setParam("doc", doc.id)} onKeyDown={(e) => e.key === "Enter" && setParam("doc", doc.id)}>
                  <td>
                    <strong>{doc.title}</strong>
                    {doc.filename && <div className="small muted">{doc.filename}</div>}
                  </td>
                  <td className="col-optional">{doc.source}</td>
                  <td className="upper">{doc.extension ?? "—"}</td>
                  <td className="col-optional">{formatDate(doc.source_modified_at)}</td>
                  <td>
                    <Status value={doc.status} />
                    {doc.excluded && doc.status !== "excluded" && <div className="small muted">{t.status.excluded}</div>}
                  </td>
                  <td>
                    <Status value={doc.acl_status} />
                  </td>
                  <td className="num">{doc.chunk_count ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data && list.data.total > PAGE && (
          <div className="pager">
            <button className="btn small" type="button" disabled={offset === 0} onClick={() => setParam("offset", String(Math.max(0, offset - PAGE)))}>
              {d.previous}
            </button>
            <span className="small muted">
              {offset + 1}–{Math.min(offset + PAGE, list.data.total)} / {list.data.total}
            </span>
            <button className="btn small" type="button" disabled={offset + PAGE >= list.data.total} onClick={() => setParam("offset", String(offset + PAGE))}>
              {d.next}
            </button>
          </div>
        )}
      </div>
      {selected && (
        <DocumentDetail
          id={selected}
          onClose={() => setParam("doc", null)}
          onChanged={() => void queryClient.invalidateQueries({ queryKey: ["documents"] })}
        />
      )}
    </div>
  );
}

function DocumentDetail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const detail = useQuery({ queryKey: ["document", id], queryFn: () => api<Detail>(`/documents/${id}`), refetchInterval: 5000 });
  const action = useMutation({
    mutationFn: async (kind: "reindex" | "exclude" | "include" | "remove") => {
      if (kind === "remove") await del(`/documents/${id}/index`);
      else await post(`/documents/${id}/${kind}`);
      return kind;
    },
    onSuccess: (kind) => {
      setNotice(kind === "reindex" ? d.reindexQueued : null);
      onChanged();
      void queryClient.invalidateQueries({ queryKey: ["document", id] });
    },
    onError: (e: Error) => setNotice(e.message),
  });
  const doc = detail.data;

  return (
    <aside className="detail" aria-label={doc?.title ?? ""}>
      <div className="sources-head">
        <h2>{doc?.title ?? "…"}</h2>
        <button className="btn btn-ghost small" type="button" onClick={onClose}>
          {t.assistant.close}
        </button>
      </div>
      {doc && (
        <>
          <div className="detail-badges">
            <Status value={doc.status} />
            <Status value={doc.access.status} />
          </div>
          {doc.excluded && <div className="alert alert-warn small">{d.excludedNote}</div>}
          {doc.status_detail && <div className="alert alert-error small">{doc.status_detail}</div>}
          {notice && <div className="alert alert-ok small">{notice}</div>}
          <div className="row-actions">
            <button className="btn small" type="button" disabled={action.isPending} onClick={() => action.mutate("reindex")}>
              {d.reindex}
            </button>
            <button className="btn btn-ghost small" type="button" disabled={action.isPending} onClick={() => action.mutate(doc.excluded ? "include" : "exclude")}>
              {doc.excluded ? d.include : d.exclude}
            </button>
            {doc.versions.length > 0 && (
              <button className="btn btn-ghost btn-danger small" type="button" disabled={action.isPending} onClick={() => window.confirm(d.confirmRemove(doc.title)) && action.mutate("remove")}>
                {d.removeIndex}
              </button>
            )}
            <a className="btn btn-ghost small" href={`${API}/documents/${id}/open`} target="_blank" rel="noopener noreferrer">
              <IconOpen /> {d.open}
            </a>
          </div>
          <section>
            <h3 className="detail-h">{d.metadata}</h3>
            <dl className="meta">
              <dt>{d.source}</dt>
              <dd>{doc.source}</dd>
              <dt>Fichier</dt>
              <dd>{doc.filename ?? "—"}</dd>
              <dt>Emplacement</dt>
              <dd>{doc.location || "—"}</dd>
              <dt>{d.modified}</dt>
              <dd>{formatDate(doc.source_modified_at, true)}</dd>
              <dt>Taille</dt>
              <dd>{doc.size_bytes != null ? `${Math.ceil(doc.size_bytes / 1024)} Ko` : "—"}</dd>
              <dt>Version (source)</dt>
              <dd className="mono">{doc.source_version ?? "—"}</dd>
            </dl>
          </section>
          <section>
            <h3 className="detail-h">{d.accessTitle}</h3>
            <p className="small">{d.accessKeys(doc.access.keys, doc.access.deny_keys)}</p>
            {doc.access.reason && <p className="small muted">{doc.access.reason}</p>}
          </section>
          <section>
            <h3 className="detail-h">{d.versions}</h3>
            <ol className="versions">
              {doc.versions.map((v) => (
                <li key={v.id}>
                  <div>
                    <Status value={v.status} /> {v.current && <span className="badge badge-accent">{d.current}</span>}
                  </div>
                  <div className="small muted">
                    {formatDate(v.created_at, true)} · {v.chunk_count} fragments
                    {v.page_count ? ` · ${v.page_count} pages` : ""}
                    {v.ocr_engine ? ` · OCR ${v.ocr_engine.split("/")[0]}` : ""}
                  </div>
                  {v.context && <div className="small">{v.context}</div>}
                  {v.warnings.map((w) => (
                    <div key={w} className="small text-warn">
                      {w}
                    </div>
                  ))}
                  {v.error && <div className="small text-danger">{v.error}</div>}
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </aside>
  );
}
