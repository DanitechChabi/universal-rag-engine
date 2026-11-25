// Flux de réponse (SSE sur POST) : lu avec fetch, annulable (ADR-0023).
import { raw } from "./api";

export type Citation = {
  rank: number;
  document_id: string;
  title: string | null;
  pages: string | null;
  excerpt: string | null;
  accessible?: boolean;
  inferred?: boolean;
};

export type ModelInfo = { id: string; name: string; locality: "local" | "external" } | null;

export type ChatEvent =
  | { name: "meta"; data: { message_id: string; conversation_id: string; model: ModelInfo; question_reformulee?: string | null } }
  | { name: "sources"; data: { candidates: number } }
  | { name: "token"; data: { text: string } }
  | { name: "citations"; data: { items: Citation[] } }
  | { name: "done"; data: { insufficient: boolean; answer: string; reponse_incomplete?: boolean } }
  | { name: "error"; data: { code: string; detail: string } };

export function parseSse(buffer: string): { events: ChatEvent[]; rest: string } {
  const events: ChatEvent[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const part of parts) {
    let name = "message";
    const data: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length) events.push({ name, data: JSON.parse(data.join("\n")) } as ChatEvent);
  }
  return { events, rest };
}

export async function streamChat(
  question: string,
  conversationId: string | null,
  signal: AbortSignal,
  onEvent: (e: ChatEvent) => void,
): Promise<void> {
  const response = await raw("/chat", {
    method: "POST",
    body: JSON.stringify({ question, conversation_id: conversationId }),
    signal,
  });
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    const parsed = parseSse(buffer + value);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  if (buffer.trim()) parseSse(buffer + "\n\n").events.forEach(onEvent);
}

/** Découpe une réponse en texte et références [n] (jamais de HTML interprété). */
export function splitCitations(text: string): Array<string | number> {
  const out: Array<string | number> = [];
  let last = 0;
  for (const m of text.matchAll(/\[(\d{1,3})\]/g)) {
    if (m.index! > last) out.push(text.slice(last, m.index));
    out.push(Number(m[1]));
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
