import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * CORS import-boundary guardrail.
 *
 * The Brain2 backend ships NO CORS headers. Only the background service worker's
 * fetches are CORS-exempt (granted via `host_permissions` in MV3). Therefore the
 * two modules that talk to the backend over `fetch` — `services/api/client.ts`
 * (createClient) and `services/auth/oauth.ts` (which POSTs `/oauth/token`) — must
 * be imported ONLY by `entrypoints/background.ts`. If a popup or content-script
 * entry imports them (directly or transitively through a barrel), those fetches
 * run from a non-exempt context and fail at runtime with opaque CORS errors.
 *
 * This test statically asserts that the popup/content entry source files do not
 * import the backend-only modules. It is a cheap regression guard, not a full
 * transitive-graph analysis; the entry files are the realistic place a violation
 * is introduced.
 */

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

// Entry files that run in a CORS-bound context (popup window / page content script).
const corsBoundEntries = [
  "entrypoints/popup/App.tsx",
  "entrypoints/popup/main.tsx",
  "entrypoints/popup/SignIn.tsx",
  "entrypoints/popup/modes/SavePage.tsx",
  "entrypoints/popup/modes/CustomNote.tsx",
  "entrypoints/popup/modes/NeedsAttention.tsx",
  "entrypoints/popup/lib/is-signed-out.ts",
  "entrypoints/content.ts",
  "entrypoints/picker.content.ts",
  "entrypoints/picker/picker-overlay.ts",
  "entrypoints/picker/html-to-markdown.ts",
  "entrypoints/note.content.ts",
  "entrypoints/note/note-modal.ts",
];

// Module specifiers that must never appear in a CORS-bound entry's imports.
const forbidden = [/services\/api\/client/, /services\/auth\/oauth/];

describe("CORS import boundary", () => {
  it("popup/content entries do not import the backend-only fetch modules", () => {
    const violations: string[] = [];
    for (const rel of corsBoundEntries) {
      const file = resolve(root, rel);
      if (!existsSync(file)) continue; // tolerate future refactors of the file list
      const src = readFileSync(file, "utf8");
      for (const pattern of forbidden) {
        if (pattern.test(src)) {
          violations.push(`${rel} imports a backend-only module matching ${pattern}`);
        }
      }
    }
    expect(violations).toEqual([]);
  });
});
