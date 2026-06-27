import { createShadowRootUi } from "wxt/utils/content-script-ui/shadow-root";
import type { ContentScriptContext } from "wxt/utils/content-script-context";
import { saveClipMsg } from "@/services/capture/messages";
import { isSignedOutError } from "@/entrypoints/popup/lib/is-signed-out";
import { htmlToMarkdown } from "./html-to-markdown";

// ---------------------------------------------------------------------------
// Pure DOM-walk helpers (unit-tested in __tests__/picker-walk.test.ts)
// ---------------------------------------------------------------------------

/**
 * Expand the current selection one logical block upward.
 *
 * Returns the element's parent, but never climbs above `document.body`:
 * if the element is already a top-level block directly under body, it is
 * returned unchanged (clamped). This keeps the selection predictable and
 * avoids ever selecting `<body>` or `<html>`.
 */
export function expandSelection(el: Element): Element {
  const parent = el.parentElement;
  // Clamp at the top of the content tree: never climb to `<body>` or `<html>`.
  const atTop =
    !parent ||
    parent === document.body ||
    parent === document.documentElement;
  return atTop ? el : parent;
}

/**
 * Contract the current selection one level downward to the first *element*
 * child (text nodes are skipped). If the element has no element children,
 * it is returned unchanged.
 */
export function contractSelection(el: Element): Element {
  return el.firstElementChild ?? el;
}

/** Snapshot the data needed to build a clip from an element. */
export function elementToClip(el: Element): {
  html: string;
  sourceUrl: string;
  title: string;
} {
  return {
    html: el.outerHTML,
    sourceUrl: location.href,
    title: document.title,
  };
}

/** Display host for a URL (e.g. "example.com"), falling back to the raw string. */
export function hostFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// ---------------------------------------------------------------------------
// Overlay controller (glue — verified by compile/build + manual QA)
// ---------------------------------------------------------------------------

// Accent (indigo), deliberately NOT red — red reads as destructive.
const ACCENT = "#6366F1";

// Module-level guard: if the picker script is injected twice, the second
// mount no-ops rather than stacking overlays.
let mounted = false;

/**
 * Mount the element-picker overlay inside an isolated Shadow DOM.
 *
 * Interaction model:
 *  - `mousemove` highlights the element under the cursor.
 *  - `ArrowUp` expands, `ArrowDown` contracts the current selection.
 *  - `click` (capture) freezes the selection → HTML→Markdown → review card.
 *  - `Escape` / Cancel aborts; Save sends a `clip` to the background.
 *
 * Uses WXT's `createShadowRootUi` for style isolation and lifecycle cleanup.
 * It works with runtime-registered/programmatically-injected scripts because
 * we don't rely on `cssInjectionMode: "ui"` — all overlay styling is inline,
 * so no entry CSS fetch is needed.
 */
export async function mountPicker(ctx: ContentScriptContext): Promise<void> {
  if (mounted) return;
  mounted = true;

  // The element currently under consideration.
  let current: Element | null = null;
  // Tracks whether we've switched from "picking" to "review card" mode so the
  // mousemove/keyboard handlers stop interfering once the user has captured.
  let capturing = false;

  const ui = await createShadowRootUi(ctx, {
    name: "brain2-picker",
    position: "overlay",
    onMount: (container) => buildPicker(container),
    onRemove: () => teardown(),
  });

  // The highlight box and the page-level listeners are created in onMount; we
  // keep references here so teardown can detach them deterministically.
  let highlight: HTMLDivElement | null = null;
  const documentListeners: Array<{
    type: string;
    handler: EventListener;
    capture: boolean;
  }> = [];

  function addDocListener(
    type: string,
    handler: EventListener,
    capture: boolean,
  ): void {
    document.addEventListener(type, handler, capture);
    documentListeners.push({ type, handler, capture });
  }

  function teardown(): void {
    for (const { type, handler, capture } of documentListeners) {
      document.removeEventListener(type, handler, capture);
    }
    documentListeners.length = 0;
    highlight = null;
    current = null;
    mounted = false;
  }

  /** Position the highlight box over `el`, accounting for scroll offsets. */
  function positionHighlight(el: Element): void {
    if (!highlight) return;
    const rect = el.getBoundingClientRect();
    highlight.style.top = `${rect.top + window.scrollY}px`;
    highlight.style.left = `${rect.left + window.scrollX}px`;
    highlight.style.width = `${rect.width}px`;
    highlight.style.height = `${rect.height}px`;
    highlight.style.display = "block";
  }

  /** True when the event originated inside our own overlay shadow host. */
  function isOwnTarget(target: EventTarget | null): boolean {
    return target instanceof Node && ui.shadowHost.contains(target);
  }

  function buildPicker(container: HTMLElement): void {
    highlight = document.createElement("div");
    Object.assign(highlight.style, {
      position: "absolute",
      boxSizing: "border-box",
      border: `2px solid ${ACCENT}`,
      background: "rgba(99, 102, 241, 0.12)",
      borderRadius: "3px",
      pointerEvents: "none",
      zIndex: "2147483647",
      display: "none",
    } satisfies Partial<CSSStyleDeclaration>);
    container.appendChild(highlight);

    const onMouseMove = (event: Event): void => {
      if (capturing) return;
      const e = event as MouseEvent;
      if (isOwnTarget(e.target)) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (!el || isOwnTarget(el)) return;
      current = el;
      positionHighlight(current);
    };

    const onKeyDown = (event: Event): void => {
      if (capturing) return;
      const e = event as KeyboardEvent;
      if (e.key === "Escape") {
        e.preventDefault();
        ui.remove();
        return;
      }
      if (!current) return;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        current = expandSelection(current);
        positionHighlight(current);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        current = contractSelection(current);
        positionHighlight(current);
      }
    };

    const onClick = (event: Event): void => {
      if (capturing) return;
      const e = event as MouseEvent;
      if (isOwnTarget(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      const target = current ?? (e.target as Element | null);
      if (!target) return;
      capture(container, target);
    };

    addDocListener("mousemove", onMouseMove, false);
    addDocListener("keydown", onKeyDown, true);
    addDocListener("click", onClick, true);
  }

  /** Freeze the selection and swap the overlay into the review card. */
  function capture(container: HTMLElement, el: Element): void {
    capturing = true;
    if (highlight) highlight.style.display = "none";
    const { html, sourceUrl, title } = elementToClip(el);
    const md = htmlToMarkdown(html);
    buildReviewCard(container, md, sourceUrl, title);
  }

  function buildReviewCard(
    container: HTMLElement,
    md: string,
    sourceUrl: string,
    title: string,
  ): void {
    const backdrop = document.createElement("div");
    Object.assign(backdrop.style, {
      position: "fixed",
      top: "0",
      left: "0",
      width: "100vw",
      height: "100vh",
      background: "rgba(15, 23, 42, 0.25)",
      backdropFilter: "blur(4px)",
      webkitBackdropFilter: "blur(4px)",
      opacity: "0",
      transition: "opacity 0.2s ease",
      zIndex: "2147483646",
    } as any);
    backdrop.addEventListener("click", () => ui.remove());
    container.appendChild(backdrop);

    const card = document.createElement("div");
    Object.assign(card.style, {
      position: "fixed",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -48%) scale(0.98)",
      width: "min(560px, 90vw)",
      maxHeight: "80vh",
      display: "flex",
      flexDirection: "column",
      gap: "16px",
      padding: "24px",
      background: "#ffffff",
      color: "#0f172a",
      border: "1px solid rgba(15, 23, 42, 0.08)",
      borderRadius: "14px",
      boxShadow: "0 12px 32px -8px rgba(15, 23, 42, 0.18), 0 0 0 1px rgba(15, 23, 42, 0.05)",
      font: "14px/1.5 system-ui, -apple-system, sans-serif",
      opacity: "0",
      transition: "opacity 0.2s ease, transform 0.2s ease",
      zIndex: "2147483647",
    } satisfies Partial<CSSStyleDeclaration>);

    // Fade the backdrop and ease the card in together for a calmer entrance.
    requestAnimationFrame(() => {
      backdrop.style.opacity = "1";
      card.style.opacity = "1";
      card.style.transform = "translate(-50%, -50%) scale(1)";
    });

    const heading = document.createElement("div");
    heading.textContent = "Review selection";
    Object.assign(heading.style, {
      fontWeight: "600",
      fontSize: "15px",
      letterSpacing: "-0.01em",
      color: "#0f172a",
    } satisfies Partial<CSSStyleDeclaration>);

    // Subtle source line gives provenance without clutter; truncates on overflow.
    const source = document.createElement("div");
    source.textContent = hostFromUrl(sourceUrl);
    Object.assign(source.style, {
      marginTop: "-10px",
      fontSize: "12px",
      color: "#94a3b8",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
    } satisfies Partial<CSSStyleDeclaration>);

    const textarea = document.createElement("textarea");
    textarea.value = md;
    Object.assign(textarea.style, {
      width: "100%",
      minHeight: "220px",
      flex: "1",
      resize: "vertical",
      boxSizing: "border-box",
      padding: "12px",
      border: "1px solid #e2e8f0",
      borderRadius: "10px",
      font: "13px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace",
      color: "#334155",
      background: "#f8fafc",
      outline: "none",
      transition: "border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease",
    } satisfies Partial<CSSStyleDeclaration>);

    textarea.addEventListener("focus", () => {
      textarea.style.borderColor = ACCENT;
      textarea.style.background = "#ffffff";
      textarea.style.boxShadow = "0 0 0 3px rgba(99, 102, 241, 0.12)";
    });
    textarea.addEventListener("blur", () => {
      textarea.style.borderColor = "#e2e8f0";
      textarea.style.background = "#f8fafc";
      textarea.style.boxShadow = "none";
    });

    const status = document.createElement("div");
    Object.assign(status.style, {
      fontSize: "12px",
      minHeight: "18px",
      fontWeight: "500",
    } satisfies Partial<CSSStyleDeclaration>);

    const actions = document.createElement("div");
    Object.assign(actions.style, {
      display: "flex",
      justifyContent: "flex-end",
      gap: "10px",
    } satisfies Partial<CSSStyleDeclaration>);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    Object.assign(cancelBtn.style, {
      padding: "8px 16px",
      borderRadius: "8px",
      border: "1px solid #e2e8f0",
      background: "#ffffff",
      color: "#475569",
      cursor: "pointer",
      font: "inherit",
      fontWeight: "500",
      fontSize: "13px",
      transition: "all 0.15s ease",
    } satisfies Partial<CSSStyleDeclaration>);

    cancelBtn.addEventListener("mouseover", () => {
      cancelBtn.style.background = "#f8fafc";
      cancelBtn.style.borderColor = "#cbd5e1";
      cancelBtn.style.color = "#0f172a";
    });
    cancelBtn.addEventListener("mouseout", () => {
      cancelBtn.style.background = "#ffffff";
      cancelBtn.style.borderColor = "#e2e8f0";
      cancelBtn.style.color = "#475569";
    });

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save clip";
    Object.assign(saveBtn.style, {
      padding: "8px 16px",
      borderRadius: "8px",
      border: "none",
      background: ACCENT,
      color: "#ffffff",
      cursor: "pointer",
      font: "inherit",
      fontWeight: "600",
      fontSize: "13px",
      transition: "all 0.15s ease",
    } satisfies Partial<CSSStyleDeclaration>);

    saveBtn.addEventListener("mouseover", () => {
      saveBtn.style.background = "#4f46e5";
    });
    saveBtn.addEventListener("mouseout", () => {
      saveBtn.style.background = ACCENT;
    });

    cancelBtn.addEventListener("click", () => ui.remove());

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.style.opacity = "0.6";
      status.style.color = "#64748b";
      status.textContent = "Saving to Brain2...";
      try {
        await saveClipMsg.send(
          {
            type: "clip",
            captured_text: textarea.value,
            // A clip is URL-backed: the backend requires `url` and dedups on its
            // normalized form (spec §7.1). For the element picker that URL is the
            // page the selection came from, which is also recorded as `source_url`
            // for clip provenance (DB schema §schema). Both are the same page URL.
            url: sourceUrl,
            source_url: sourceUrl,
            title: title || undefined,
          },
          { to: "background" },
        );
        status.style.color = "#059669";
        status.textContent = "Saved ✓";
        window.setTimeout(() => ui.remove(), 600);
      } catch (err) {
        // Keep the card open so the user's edited text is never lost.
        saveBtn.disabled = false;
        saveBtn.style.opacity = "1";
        status.style.color = "#ef4444";
        // Only point the user at sign-in when the failure is actually an auth one;
        // other failures (network, backend) must not masquerade as "please sign in".
        status.textContent = isSignedOutError(err)
          ? "Couldn't save — open the toolbar to sign in."
          : "Couldn't save — please try again.";
      }
    });

    actions.append(cancelBtn, saveBtn);
    card.append(heading, source, textarea, status, actions);
    container.appendChild(card);
    textarea.focus();
  }

  // `createShadowRootUi` already registers ctx.onInvalidated(remove); we add an
  // explicit teardown hook too so listeners are removed even if remove() isn't
  // routed through ctx invalidation.
  ctx.onInvalidated(() => ui.remove());

  ui.mount();
}
