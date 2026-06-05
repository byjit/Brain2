import { Readability } from "@mozilla/readability";

export interface Extracted {
  title: string;
  textContent: string;
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
    textContent: (parsed?.textContent ?? doc.body?.textContent ?? "").trim(),
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
