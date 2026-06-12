import { Readability } from "@mozilla/readability";

export interface Extracted {
  title: string;
  textContent: string;
}

/**
 * Upper bound on the page body we send for a `page` save.
 *
 * A `page` save discards its body server-side after summarizing a PREFIX of it (spec §7.3)
 * — the note is a routing card and the URL is the recovery path — so shipping a whole long
 * article (a Medium deep-dive can be hundreds of KB) only wastes bandwidth and risks the
 * backend's body-size limit. We send a generous prefix: comfortably larger than the
 * backend's summary window so the note never loses signal, yet bounded so capture cannot
 * fail on a huge page. Conversation/clip/note bodies are PERSISTED (not re-fetchable) and
 * are intentionally NOT capped here.
 */
export const MAX_PAGE_CAPTURE_CHARS = 32_000;

/** Cap `text` to a prefix, trimming back to a word boundary so we never cut mid-word. */
function capPageBody(text: string): string {
  if (text.length <= MAX_PAGE_CAPTURE_CHARS) return text;
  const slice = text.slice(0, MAX_PAGE_CAPTURE_CHARS);
  const lastSpace = slice.lastIndexOf(" ");
  return (lastSpace > 0 ? slice.slice(0, lastSpace) : slice).trimEnd();
}

/**
 * Article extraction via Mozilla Readability.
 *
 * Readability mutates the document it parses, so we always hand it a clone and
 * leave the live page untouched. Readability returns `null` on pages it can't
 * parse (e.g. apps with little prose) — in that case we fall back to the raw
 * document title and body text.
 */
export function extractReadable(doc: Document): Extracted {
  const parsed = new Readability(doc.cloneNode(true) as Document).parse();
  return {
    title: parsed?.title ?? doc.title ?? "",
    // Page bodies are discarded server-side after a prefix summary, so cap before send.
    textContent: capPageBody((parsed?.textContent ?? doc.body?.textContent ?? "").trim()),
  };
}

/**
 * Best-effort conversation capture for chat domains: the visible text of the
 * document body. Refined per-site during dogfood (spec §15 open question).
 *
 * `innerText` (which respects visibility/whitespace) is preferred at runtime,
 * but jsdom does not implement it — so we fall back to `textContent`.
 */
export function extractConversation(doc: Document): Extracted {
  const body = doc.body;
  const text = (body as HTMLElement | null)?.innerText ?? body?.textContent ?? "";
  return {
    title: doc.title ?? "",
    textContent: text.trim(),
  };
}
