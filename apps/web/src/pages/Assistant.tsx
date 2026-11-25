import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router";
import { api, ApiError, API } from "../api";
import { useAuth } from "../auth";
import { splitCitations, streamChat, type Citation, type ModelInfo } from "../chat";
import { IconCopy, IconOpen, IconPlus, IconSend, IconStop } from "../components/icons";
import { t } from "../i18n";

type Turn = {
  key: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  insufficient?: boolean;
  model?: ModelInfo;
  locality?: string | null;
  rewritten?: string | null;
  status: "streaming" | "done" | "stopped" | "error";
  error?: string;
};

type ConversationSummary = { id: string; title: string | null; updated_at: string };
type ConversationDetail = {
  id: string;
  messages: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    insufficient: boolean;
    locality: string | null;
    citations: Citation[];
  }>;
};

const a = t.assistant;

export function Assistant() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const conversationId = params.get("c");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [selected, setSelected] = useState<{ turn: string; rank: number | null } | null>(null);
  const [question, setQuestion] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const streaming = turns.some((x) => x.status === "streaming");
  // Conversation créée par la question en cours : son historique est déjà affiché.
  const createdHere = useRef<string | null>(null);

  const usable = useQuery({
    queryKey: ["models"],
    queryFn: () =>
      api<{ items: { id: string; name: string; locality: "local" | "external" }[]; external_blocked_by_limit: boolean; notify_on_external: boolean }>(
        "/models",
      ),
    staleTime: 30_000,
  });
  const [modelId, setModelId] = useState<string>("");
  const models = usable.data?.items ?? [];
  const chosen = models.find((x) => x.id === modelId) ?? models[0];

  const history = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api<{ items: ConversationSummary[] }>("/conversations"),
  });

  useEffect(() => {
    if (!conversationId) return; // conversation vidée par « Nouvelle conversation », jamais en différé
    if (createdHere.current === conversationId) return;
    let cancelled = false;
    api<ConversationDetail>(`/conversations/${conversationId}`)
      .then((detail) => {
        if (cancelled) return;
        setTurns(
          detail.messages.map((m) => ({
            key: m.id,
            role: m.role,
            content: m.content,
            citations: m.citations,
            insufficient: m.insufficient,
            locality: m.locality,
            status: "done",
          })),
        );
        setSelected(null);
      })
      .catch(() => !cancelled && setParams({}));
    return () => {
      cancelled = true;
    };
  }, [conversationId, setParams]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns]);

  function patch(key: string, change: Partial<Turn> | ((t: Turn) => Partial<Turn>)) {
    setTurns((all) => all.map((x) => (x.key === key ? { ...x, ...(typeof change === "function" ? change(x) : change) } : x)));
  }

  async function ask(e?: FormEvent) {
    e?.preventDefault();
    const text = question.trim();
    if (!text || streaming) return;
    const key = crypto.randomUUID();
    setQuestion("");
    setTurns((all) => [
      ...all,
      { key: `q-${key}`, role: "user", content: text, citations: [], status: "done" },
      { key, role: "assistant", content: "", citations: [], status: "streaming" },
    ]);
    setSelected(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(text, conversationId, controller.signal, (ev) => {
        switch (ev.name) {
          case "meta":
            patch(key, { model: ev.data.model, locality: ev.data.model?.locality ?? null, rewritten: ev.data.question_reformulee });
            if (!conversationId) {
              createdHere.current = ev.data.conversation_id;
              setParams({ c: ev.data.conversation_id }, { replace: true });
            }
            break;
          case "token":
            patch(key, (x) => ({ content: x.content + ev.data.text }));
            break;
          case "citations":
            patch(key, { citations: ev.data.items });
            break;
          case "done":
            // Texte validé par le serveur : citations vérifiées, liens et images retirés.
            patch(key, { content: ev.data.answer, insufficient: ev.data.insufficient, status: "done" });
            if (!ev.data.insufficient) setSelected({ turn: key, rank: null });
            break;
          case "error":
            patch(key, { status: "error", error: ev.data.code === "ai.policy" ? a.noModel : a.unavailable });
            break;
        }
      }, modelId || null);
      patch(key, (x) => (x.status === "streaming" ? { status: "error", error: a.interrupted } : {}));
    } catch (err) {
      if (controller.signal.aborted) patch(key, { status: "stopped" });
      else patch(key, { status: "error", error: err instanceof ApiError && err.status === 403 ? t.errors.forbidden : a.unavailable });
    } finally {
      abortRef.current = null;
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask();
    }
  }

  function newConversation() {
    abortRef.current?.abort();
    createdHere.current = null;
    setTurns([]);
    setSelected(null);
    setParams({});
  }

  const current = turns.find((x) => x.key === selected?.turn);

  return (
    <div className={`assistant ${current ? "with-sources" : ""}`}>
      <aside className="history" aria-label={a.history}>
        <button className="btn btn-primary" type="button" onClick={newConversation}>
          <IconPlus /> {a.newConversation}
        </button>
        <nav className="history-list">
          {history.data?.items.length === 0 && <p className="small muted">{a.noHistory}</p>}
          {history.data?.items.map((c) => (
            <button
              key={c.id}
              type="button"
              className="history-item"
              aria-current={c.id === conversationId ? "page" : undefined}
              onClick={() => {
                createdHere.current = null;
                setParams({ c: c.id });
              }}
            >
              <span>{c.title || a.untitled}</span>
              <time className="small muted" dateTime={c.updated_at}>
                {new Date(c.updated_at).toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}
              </time>
            </button>
          ))}
        </nav>
      </aside>

      <section className="thread" aria-label={a.conversation}>
        <div className="messages" aria-live="polite">
          {turns.length === 0 && (
            <div className="empty">
              <h1>{a.hello(me?.display_name ?? "")}</h1>
              <p className="muted">{a.intro}</p>
            </div>
          )}
          {turns.map((turn) =>
            turn.role === "user" ? (
              <div key={turn.key} className="msg msg-user">
                {turn.content}
              </div>
            ) : (
              <Answer
                key={turn.key}
                turn={turn}
                active={selected?.turn === turn.key}
                onCite={(rank) => setSelected({ turn: turn.key, rank })}
                onSources={() => setSelected({ turn: turn.key, rank: null })}
              />
            ),
          )}
          <div ref={endRef} />
        </div>
        <form className="composer" onSubmit={ask}>
          <label htmlFor="question" className="visually-hidden">
            {a.placeholder}
          </label>
          <textarea
            id="question"
            className="input"
            rows={2}
            maxLength={4000}
            placeholder={a.placeholder}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKey}
          />
          {streaming ? (
            <button className="btn" type="button" onClick={() => abortRef.current?.abort()}>
              <IconStop /> {a.stop}
            </button>
          ) : (
            <button className="btn btn-primary" type="submit" disabled={!question.trim()}>
              <IconSend /> {a.send}
            </button>
          )}
        </form>
        {models.length > 1 && (
          <div className="composer-model">
            <label htmlFor="model" className="small muted">
              {a.model}
            </label>
            <select id="model" className="input input-sm" value={modelId} onChange={(e) => setModelId(e.target.value)}>
              <option value="">{a.autoModel(models[0]?.name ?? "")}</option>
              {models.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name} ({x.locality === "local" ? a.local : a.external})
                </option>
              ))}
            </select>
          </div>
        )}
        {chosen?.locality === "external" && usable.data?.notify_on_external && (
          <div className="alert alert-warn small composer-warning" role="note">
            {a.externalWarning(chosen.name)}
          </div>
        )}
        {usable.data?.external_blocked_by_limit && <div className="alert alert-warn small composer-warning">{a.limitReached}</div>}
        <p className="composer-note small muted">{a.note}</p>
      </section>

      {current && (
        <aside className="sources" aria-label={a.sources}>
          <div className="sources-head">
            <h2>{a.sources}</h2>
            <button className="btn btn-ghost small" type="button" onClick={() => setSelected(null)}>
              {a.close}
            </button>
          </div>
          {current.citations.length === 0 && <p className="small muted">{a.noSources}</p>}
          {current.citations.map((c) => (
            <article key={c.rank} className={`source ${selected?.rank === c.rank ? "source-active" : ""}`} id={`source-${c.rank}`}>
              <div className="source-title">
                <span className="cite cite-static">{c.rank}</span>
                <strong>{c.title ?? a.restricted}</strong>
              </div>
              {c.pages && <div className="small muted">{c.pages}{c.inferred ? ` · ${a.inferred}` : ""}</div>}
              {c.excerpt && <blockquote className="excerpt">{c.excerpt}</blockquote>}
              {c.title && (
                <a className="btn btn-ghost small" href={`${API}/documents/${c.document_id}/open`} target="_blank" rel="noopener noreferrer">
                  <IconOpen /> {a.open}
                </a>
              )}
            </article>
          ))}
        </aside>
      )}
    </div>
  );
}

function Answer({ turn, active, onCite, onSources }: { turn: Turn; active: boolean; onCite: (rank: number) => void; onSources: () => void }) {
  const [copied, setCopied] = useState(false);
  const ranks = new Set(turn.citations.map((c) => c.rank));
  const local = (turn.model?.locality ?? turn.locality) !== "external";

  async function copy() {
    await navigator.clipboard.writeText(turn.content.replace(/\s?\[\d{1,3}\]/g, ""));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className={`msg msg-answer ${active ? "msg-active" : ""} ${turn.insufficient ? "msg-insufficient" : ""}`}>
      {turn.rewritten && <div className="small muted">{a.rewritten(turn.rewritten)}</div>}
      <div className="answer-text">
        {turn.content === "" && turn.status === "streaming" && <span className="muted">{a.searching}</span>}
        {splitCitations(turn.content).map((part, i) =>
          typeof part === "string" ? (
            <span key={i}>{part}</span>
          ) : ranks.has(part) ? (
            <button key={i} type="button" className="cite" onClick={() => onCite(part)} aria-label={`${a.source} ${part}`}>
              {part}
            </button>
          ) : null,
        )}
        {turn.status === "streaming" && turn.content && <span className="caret" aria-hidden />}
      </div>
      {turn.status === "stopped" && <div className="alert alert-warn small">{a.stopped}</div>}
      {turn.status === "error" && <div className="alert alert-error small">{turn.error}</div>}
      {turn.status === "done" && (
        <div className="answer-foot">
          {turn.citations.length > 0 && (
            <button type="button" className="btn btn-ghost small" onClick={onSources}>
              {a.sourcesCount(turn.citations.length)}
            </button>
          )}
          <button type="button" className="btn btn-ghost small" onClick={() => void copy()}>
            <IconCopy /> {copied ? a.copied : a.copy}
          </button>
          {(turn.model || turn.locality) && (
            <span className={`badge ${local ? "badge-ok" : "badge-warn"}`} title={turn.model?.name}>
              {local ? a.local : a.external}
              {turn.model ? ` · ${turn.model.name}` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
