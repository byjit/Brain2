import TurndownService from "turndown";
import { gfm } from "turndown-plugin-gfm";

/**
 * Shared Turndown instance configured for GitHub-flavored Markdown with
 * fenced code blocks and ATX (`#`) headings. Reused across calls — the
 * service is stateless per `turndown(...)` invocation.
 */
const service = new TurndownService({
  codeBlockStyle: "fenced",
  headingStyle: "atx",
});
service.use(gfm);

/**
 * Convert an HTML string to Markdown. Pure: Turndown parses the HTML via the
 * ambient DOM (jsdom in tests, the browser at runtime).
 */
export function htmlToMarkdown(html: string): string {
  return service.turndown(html);
}
