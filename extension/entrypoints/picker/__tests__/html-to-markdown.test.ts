/** @vitest-environment jsdom */
import { describe, it, expect } from "vitest";
import { htmlToMarkdown } from "@/entrypoints/picker/html-to-markdown";

describe("htmlToMarkdown", () => {
  it("converts headings, links, lists", () => {
    const md = htmlToMarkdown('<h1>Title</h1><p>See <a href="https://x.com">x</a></p><ul><li>a</li><li>b</li></ul>');
    expect(md).toContain("# Title");
    expect(md).toContain("[x](https://x.com)");
    // Turndown renders bullets as "<marker>   item" (marker + 3 spaces), so
    // assert on a bullet marker followed by whitespace rather than a single space.
    expect(md).toMatch(/[-*]\s+a/);
  });
  it("preserves fenced code blocks (gfm)", () => {
    const md = htmlToMarkdown('<pre><code>const x = 1;</code></pre>');
    expect(md).toContain("const x = 1;");
    expect(md).toContain("```");
  });
});
