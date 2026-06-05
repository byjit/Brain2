/** @vitest-environment jsdom */
import { describe, it, expect } from "vitest";
import { extractReadable, extractConversation } from "@/lib/extract";

// Readability needs a reasonable amount of prose to lock onto an article, so
// we build a multi-paragraph <article> with distinctive sentences.
const PROSE_HTML = `
  <article>
    <h1>The History of the Lighthouse</h1>
    <p>The old lighthouse stood at the edge of the rocky cliff, guiding ships
    safely through the treacherous waters for nearly two hundred years. Its
    beam swept the horizon every night without fail.</p>
    <p>Keepers lived in the small cottage beside the tower, climbing the spiral
    staircase each evening to light the great lamp. They kept meticulous logs of
    passing vessels and the changing moods of the sea.</p>
    <p>When automation finally arrived, the last keeper packed his belongings
    and left the island for good, ending a long and storied tradition that the
    townspeople still remember fondly today.</p>
  </article>
`;

function buildDoc(html: string): Document {
  const doc = document.implementation.createHTMLDocument("Test Title");
  doc.body.innerHTML = html;
  return doc;
}

describe("extractReadable", () => {
  it("extracts article prose and a sensible title", () => {
    const doc = buildDoc(PROSE_HTML);
    const { title, textContent } = extractReadable(doc);
    expect(title).toContain("Lighthouse");
    expect(textContent).toContain("guiding ships");
    expect(textContent).toContain("automation finally arrived");
  });

  it("falls back gracefully when there is no parseable article", () => {
    const doc = document.implementation.createHTMLDocument("Bare Page");
    doc.body.innerHTML = "<span>just a tiny snippet</span>";
    const { title, textContent } = extractReadable(doc);
    expect(title).toBe("Bare Page");
    expect(textContent).toContain("just a tiny snippet");
  });

  it("does not mutate the source document", () => {
    const doc = buildDoc(PROSE_HTML);
    const before = doc.body.innerHTML;
    extractReadable(doc);
    expect(doc.body.innerHTML).toBe(before);
  });
});

describe("extractConversation", () => {
  it("captures the body text", () => {
    const doc = document.implementation.createHTMLDocument("Chat");
    doc.body.innerHTML =
      "<div>User: hello there</div><div>Assistant: hi, how can I help?</div>";
    const { title, textContent } = extractConversation(doc);
    expect(title).toBe("Chat");
    expect(textContent).toContain("hello there");
    expect(textContent).toContain("how can I help?");
  });
});
