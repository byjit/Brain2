/**
 * Ambient type declarations for `turndown-plugin-gfm`, which ships no `.d.ts`.
 *
 * The package exports GitHub-flavored-Markdown plugins for Turndown. Each is a
 * Turndown `Plugin` (a function applied via `service.use(...)`). We type the
 * named exports we consume and the aggregate `gfm` bundle.
 */
declare module "turndown-plugin-gfm" {
  import type { Plugin } from "turndown";

  export const gfm: Plugin;
  export const highlightedCodeBlock: Plugin;
  export const strikethrough: Plugin;
  export const tables: Plugin;
  export const taskListItems: Plugin;
}
