import { createShadowRootUi } from "wxt/utils/content-script-ui/shadow-root";
import type { ContentScriptContext } from "wxt/utils/content-script-context";
import { saveClipMsg } from "@/services/capture/messages";
import { isSignedOutError } from "@/entrypoints/popup/lib/is-signed-out";
import { htmlToMarkdown } from "./html-to-markdown";

// ---------------------------------------------------------------------------
// Pure selection helpers (unit-tested in __tests__/picker-walk.test.ts)
// ---------------------------------------------------------------------------

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

/**
 * Toggle `el` into/out of an ordered selection set while keeping the set free
 * of nested duplicates (idempotency — a piece of content can never be selected
 * twice):
 *  - already selected              → removed (toggle off)
 *  - contained by a selected element → ignored (its content is already captured
 *                                       by the ancestor, so it can't be added)
 *  - an ancestor of existing picks → added, and the now-subsumed descendants
 *                                     are dropped so their content isn't duplicated
 *
 * Returns a new array in click order; never mutates the input.
 */
export function toggleSelection(selected: Element[], el: Element): Element[] {
  // Exact match already present → toggle it off.
  if (selected.includes(el)) return selected.filter((s) => s !== el);
  // Content already captured by a selected ancestor → nothing to add.
  if (selected.some((s) => s.contains(el))) return selected;
  // Drop any selected descendants this element now subsumes, then append it.
  return [...selected.filter((s) => !el.contains(s)), el];
}

/** Join per-element markdown blocks into one clip body, separated by a rule. */
export function joinClips(markdowns: string[]): string {
  return markdowns.join("\n---\n");
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
 * Interaction model (multi-select):
 *  - `mousemove` highlights the element under the cursor.
 *  - `click` (capture) toggles that element into/out of the selection set,
 *    keeping nested picks de-duplicated (see `toggleSelection`).
 *  - `Enter` freezes the selection → HTML→Markdown per element, joined by a
 *    `---` rule → review card.
 *  - `Escape` / Cancel aborts; Save sends a `clip` to the background and
 *    confirms with a lower-right toast.
 *
 * Uses WXT's `createShadowRootUi` for style isolation and lifecycle cleanup.
 * It works with runtime-registered/programmatically-injected scripts because
 * we don't rely on `cssInjectionMode: "ui"` — all overlay styling is inline,
 * so no entry CSS fetch is needed.
 */
export async function mountPicker(ctx: ContentScriptContext): Promise<void> {
  if (mounted) return;
  mounted = true;

  // The element currently under the cursor (hover candidate, not yet picked).
  let current: Element | null = null;
  // The ordered, de-duplicated set of picked elements.
  let selected: Element[] = [];
  // Tracks whether we've switched from "picking" to "review card" mode so the
  // mousemove/keyboard handlers stop interfering once the user has captured.
  let capturing = false;

  const ui = await createShadowRootUi(ctx, {
    name: "brain2-picker",
    position: "overlay",
    onMount: (container) => buildPicker(container),
    onRemove: () => teardown(),
  });

  // The overlay chrome (hover box, persistent selection boxes, counter pill) is
  // created in onMount; we keep references here so teardown can detach them.
  let highlight: HTMLDivElement | null = null;
  let selectionLayer: HTMLDivElement | null = null;
  let counter: HTMLDivElement | null = null;
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
    selectionLayer = null;
    counter = null;
    current = null;
    selected = [];
    mounted = false;
  }

  /** Position an absolutely-positioned box over `el`, accounting for scroll. */
  function positionBox(box: HTMLDivElement, el: Element): void {
    const rect = el.getBoundingClientRect();
    box.style.top = `${rect.top + window.scrollY}px`;
    box.style.left = `${rect.left + window.scrollX}px`;
    box.style.width = `${rect.width}px`;
    box.style.height = `${rect.height}px`;
  }

  /** Position the transient hover highlight over `el`. */
  function positionHighlight(el: Element): void {
    if (!highlight) return;
    positionBox(highlight, el);
    highlight.style.display = "block";
  }

  /** Redraw the persistent selection boxes + numbered badges from `selected`. */
  function renderSelection(): void {
    if (!selectionLayer) return;
    selectionLayer.replaceChildren();
    selected.forEach((el, i) => {
      const box = document.createElement("div");
      Object.assign(box.style, {
        position: "absolute",
        boxSizing: "border-box",
        border: `2px solid ${ACCENT}`,
        background: "rgba(99, 102, 241, 0.20)",
        borderRadius: "3px",
        pointerEvents: "none",
        zIndex: "2147483646",
      } satisfies Partial<CSSStyleDeclaration>);
      positionBox(box, el);

      // Small numbered badge (click order) anchored to the box's top-left.
      const badge = document.createElement("div");
      badge.textContent = String(i + 1);
      Object.assign(badge.style, {
        position: "absolute",
        top: "-9px",
        left: "-9px",
        minWidth: "18px",
        height: "18px",
        padding: "0 4px",
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: ACCENT,
        color: "#ffffff",
        borderRadius: "9px",
        font: "600 11px/1 system-ui, -apple-system, sans-serif",
      } satisfies Partial<CSSStyleDeclaration>);
      box.appendChild(badge);
      selectionLayer!.appendChild(box);
    });
    updateCounter();
  }

  /** Reflect the selection count in the fixed hint pill. */
  function updateCounter(): void {
    if (!counter) return;
    const n = selected.length;
    counter.style.display = n === 0 ? "none" : "flex";
    if (n > 0) {
      counter.textContent = `${n} selected · Enter to review · Esc to cancel`;
    }
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

    // Layer that holds one persistent box per picked element.
    selectionLayer = document.createElement("div");
    Object.assign(selectionLayer.style, {
      position: "absolute",
      top: "0",
      left: "0",
      pointerEvents: "none",
    } satisfies Partial<CSSStyleDeclaration>);
    container.appendChild(selectionLayer);

    // Minimal fixed hint pill; hidden until the first element is picked.
    counter = document.createElement("div");
    Object.assign(counter.style, {
      position: "fixed",
      bottom: "20px",
      left: "50%",
      transform: "translateX(-50%)",
      display: "none",
      alignItems: "center",
      padding: "8px 14px",
      background: "#0f172a",
      color: "#f8fafc",
      borderRadius: "999px",
      font: "500 12px/1.4 system-ui, -apple-system, sans-serif",
      boxShadow: "0 8px 24px -6px rgba(15, 23, 42, 0.45)",
      pointerEvents: "none",
      zIndex: "2147483647",
    } satisfies Partial<CSSStyleDeclaration>);
    container.appendChild(counter);

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
      } else if (e.key === "Enter") {
        e.preventDefault();
        finalize(container);
      }
    };

    const onClick = (event: Event): void => {
      if (capturing) return;
      const e = event as MouseEvent;
      if (isOwnTarget(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      const target = current ?? (e.target as Element | null);
      if (!target || isOwnTarget(target)) return;
      // Toggle into the de-duplicated selection set, then redraw.
      selected = toggleSelection(selected, target);
      renderSelection();
    };

    addDocListener("mousemove", onMouseMove, false);
    addDocListener("keydown", onKeyDown, true);
    addDocListener("click", onClick, true);
  }

  /** Freeze the selection set and swap the overlay into the review card. */
  function finalize(container: HTMLElement): void {
    if (selected.length === 0) return; // nothing picked yet — Enter is a no-op
    capturing = true;
    if (highlight) highlight.style.display = "none";
    if (selectionLayer) selectionLayer.style.display = "none";
    if (counter) counter.style.display = "none";

    const clips = selected.map(elementToClip);
    const md = joinClips(clips.map((c) => htmlToMarkdown(c.html)));
    // All picks come from the same page, so provenance is the page itself.
    const { sourceUrl, title } = clips[0];
    buildReviewCard(container, md, sourceUrl, title);
  }

  /** Show a minimal, auto-dismissing confirmation toast in the lower right. */
  function showToast(container: HTMLElement, text: string): void {
    const toast = document.createElement("div");
    toast.textContent = text;
    Object.assign(toast.style, {
      position: "fixed",
      bottom: "20px",
      right: "20px",
      padding: "12px 16px",
      background: "#0f172a",
      color: "#f8fafc",
      borderRadius: "10px",
      font: "500 13px/1.4 system-ui, -apple-system, sans-serif",
      boxShadow: "0 8px 24px -6px rgba(15, 23, 42, 0.45)",
      opacity: "0",
      transform: "translateY(8px)",
      transition: "opacity 0.2s ease, transform 0.2s ease",
      pointerEvents: "none",
      zIndex: "2147483647",
    } satisfies Partial<CSSStyleDeclaration>);
    container.appendChild(toast);
    requestAnimationFrame(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateY(0)";
    });
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
        // Confirm with a lower-right toast, then tear the overlay down. We drop
        // the card first but keep the shadow UI mounted so the toast survives
        // long enough to be seen (ui.remove() would destroy the shadow root).
        backdrop.remove();
        card.remove();
        showToast(container, "Saved to Brain2 ✓");
        window.setTimeout(() => ui.remove(), 2000);
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
