import { createShadowRootUi } from "wxt/utils/content-script-ui/shadow-root";
import type { ContentScriptContext } from "wxt/utils/content-script-context";
import { saveClipMsg } from "@/services/capture/messages";
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
  return parent && parent !== document.body ? parent : el;
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
    const card = document.createElement("div");
    Object.assign(card.style, {
      position: "fixed",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      width: "min(560px, 90vw)",
      maxHeight: "80vh",
      display: "flex",
      flexDirection: "column",
      gap: "12px",
      padding: "20px",
      background: "#ffffff",
      color: "#1f2937",
      border: `1px solid ${ACCENT}`,
      borderRadius: "12px",
      boxShadow: "0 10px 40px rgba(0, 0, 0, 0.25)",
      font: "14px/1.5 system-ui, -apple-system, sans-serif",
      zIndex: "2147483647",
    } satisfies Partial<CSSStyleDeclaration>);

    const heading = document.createElement("div");
    heading.textContent = "Save clip to Brain2";
    Object.assign(heading.style, {
      fontWeight: "600",
      fontSize: "15px",
    } satisfies Partial<CSSStyleDeclaration>);

    const textarea = document.createElement("textarea");
    textarea.value = md;
    Object.assign(textarea.style, {
      width: "100%",
      minHeight: "220px",
      flex: "1",
      resize: "vertical",
      boxSizing: "border-box",
      padding: "10px",
      border: "1px solid #d1d5db",
      borderRadius: "8px",
      font: "13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace",
      color: "#1f2937",
      background: "#fafafa",
    } satisfies Partial<CSSStyleDeclaration>);

    const status = document.createElement("div");
    Object.assign(status.style, {
      fontSize: "13px",
      minHeight: "18px",
    } satisfies Partial<CSSStyleDeclaration>);

    const actions = document.createElement("div");
    Object.assign(actions.style, {
      display: "flex",
      justifyContent: "flex-end",
      gap: "8px",
    } satisfies Partial<CSSStyleDeclaration>);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    Object.assign(cancelBtn.style, {
      padding: "8px 16px",
      borderRadius: "8px",
      border: "1px solid #d1d5db",
      background: "#ffffff",
      color: "#374151",
      cursor: "pointer",
      font: "inherit",
    } satisfies Partial<CSSStyleDeclaration>);

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save";
    Object.assign(saveBtn.style, {
      padding: "8px 16px",
      borderRadius: "8px",
      border: "none",
      background: ACCENT,
      color: "#ffffff",
      cursor: "pointer",
      font: "inherit",
      fontWeight: "600",
    } satisfies Partial<CSSStyleDeclaration>);

    cancelBtn.addEventListener("click", () => ui.remove());

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.style.opacity = "0.6";
      status.style.color = "#6b7280";
      status.textContent = "Saving…";
      try {
        await saveClipMsg.send(
          {
            type: "clip",
            captured_text: textarea.value,
            source_url: sourceUrl,
            title: title || undefined,
          },
          { to: "background" },
        );
        status.style.color = "#059669";
        status.textContent = "Saved ✓";
        window.setTimeout(() => ui.remove(), 600);
      } catch {
        // Keep the card open so the user's edited text is never lost.
        saveBtn.disabled = false;
        saveBtn.style.opacity = "1";
        status.style.color = "#dc2626";
        status.textContent = "Couldn't save — try the toolbar to sign in.";
      }
    });

    actions.append(cancelBtn, saveBtn);
    card.append(heading, textarea, status, actions);
    container.appendChild(card);
    textarea.focus();
  }

  // `createShadowRootUi` already registers ctx.onInvalidated(remove); we add an
  // explicit teardown hook too so listeners are removed even if remove() isn't
  // routed through ctx invalidation.
  ctx.onInvalidated(() => ui.remove());

  ui.mount();
}
