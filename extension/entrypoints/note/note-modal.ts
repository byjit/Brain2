import type { ContentScriptContext } from "wxt/utils/content-script-context";
import { createShadowRootUi } from "wxt/utils/content-script-ui/shadow-root";
import { saveNoteMsg } from "@/services/capture/messages";

const ACCENT = "#6366F1";
let mounted = false;

/**
 * Mount the quick note modal dialog inside an isolated Shadow DOM in the center of the browser tab.
 */
export async function mountNoteModal(ctx: ContentScriptContext): Promise<void> {
  if (mounted) return;
  mounted = true;

  const ui = await createShadowRootUi(ctx, {
    name: "brain2-note-modal",
    position: "overlay",
    onMount: (container) => buildNoteModal(container),
    onRemove: () => {
      mounted = false;
    },
  });

  function buildNoteModal(container: HTMLElement): void {
    const backdrop = document.createElement("div");
    Object.assign(backdrop.style, {
      position: "fixed",
      top: "0",
      left: "0",
      width: "100vw",
      height: "100vh",
      background: "rgba(15, 23, 42, 0.3)",
      backdropFilter: "blur(4px)",
      webkitBackdropFilter: "blur(4px)",
      opacity: "0",
      transition: "opacity 0.25s ease",
      zIndex: "2147483646",
    } as any);
    backdrop.addEventListener("click", () => ui.remove());
    container.appendChild(backdrop);

    requestAnimationFrame(() => {
      backdrop.style.opacity = "1";
    });

    const card = document.createElement("div");
    Object.assign(card.style, {
      position: "fixed",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      width: "min(500px, 94vw)",
      display: "flex",
      flexDirection: "column",
      gap: "12px",
      padding: "16px",
      background: "#ffffff",
      color: "#0f172a",
      border: "1px solid rgba(15, 23, 42, 0.08)",
      borderRadius: "12px",
      boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04), 0 0 0 1px rgba(0, 0, 0, 0.04)",
      font: "14px/1.5 system-ui, -apple-system, sans-serif",
      zIndex: "2147483647",
    } satisfies Partial<CSSStyleDeclaration>);

    const heading = document.createElement("div");
    heading.textContent = "Quick Note to Brain2";
    Object.assign(heading.style, {
      fontWeight: "600",
      fontSize: "14px",
      color: "#0f172a",
    } satisfies Partial<CSSStyleDeclaration>);

    const textarea = document.createElement("textarea");
    textarea.placeholder = "Jot down notes, code snippets, or thoughts to save to your memory...";
    Object.assign(textarea.style, {
      width: "100%",
      minHeight: "160px",
      resize: "none",
      boxSizing: "border-box",
      padding: "10px 12px",
      border: "1px solid #e2e8f0",
      borderRadius: "8px",
      font: "13px/1.6 system-ui, -apple-system, sans-serif",
      color: "#0f172a",
      background: "#ffffff",
      outline: "none",
      transition: "border-color 0.15s ease, box-shadow 0.15s ease",
    } satisfies Partial<CSSStyleDeclaration>);

    textarea.addEventListener("focus", () => {
      textarea.style.borderColor = ACCENT;
      textarea.style.boxShadow = "0 0 0 2px rgba(99, 102, 241, 0.15)";
    });
    textarea.addEventListener("blur", () => {
      textarea.style.borderColor = "#e2e8f0";
      textarea.style.boxShadow = "none";
    });

    const footer = document.createElement("div");
    Object.assign(footer.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "12px",
      marginTop: "4px",
    } satisfies Partial<CSSStyleDeclaration>);

    const status = document.createElement("div");
    Object.assign(status.style, {
      fontSize: "12px",
      fontWeight: "500",
      color: "#64748b",
      whiteSpace: "nowrap",
      overflow: "hidden",
      textOverflow: "ellipsis",
      maxWidth: "240px",
    } satisfies Partial<CSSStyleDeclaration>);

    const actions = document.createElement("div");
    Object.assign(actions.style, {
      display: "flex",
      gap: "8px",
    } satisfies Partial<CSSStyleDeclaration>);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    Object.assign(cancelBtn.style, {
      padding: "6px 12px",
      borderRadius: "8px",
      border: "1px solid #e2e8f0",
      background: "#ffffff",
      color: "#475569",
      cursor: "pointer",
      font: "inherit",
      fontWeight: "500",
      fontSize: "12px",
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
    cancelBtn.addEventListener("click", () => ui.remove());

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "Save Note";
    Object.assign(saveBtn.style, {
      padding: "6px 12px",
      borderRadius: "8px",
      border: "none",
      background: ACCENT,
      color: "#ffffff",
      cursor: "pointer",
      font: "inherit",
      fontWeight: "500",
      fontSize: "12px",
      transition: "all 0.15s ease",
    } satisfies Partial<CSSStyleDeclaration>);

    saveBtn.addEventListener("mouseover", () => {
      saveBtn.style.background = "#4f46e5";
    });
    saveBtn.addEventListener("mouseout", () => {
      saveBtn.style.background = ACCENT;
    });

    saveBtn.addEventListener("click", async () => {
      const val = textarea.value.trim();
      if (!val) return;
      saveBtn.disabled = true;
      saveBtn.style.opacity = "0.6";
      status.style.color = "#64748b";
      status.textContent = "Saving to Brain2...";
      try {
        await saveNoteMsg.send(
          { text: val },
          { to: "background" },
        );
        status.style.color = "#059669";
        status.textContent = "Saved ✓";
        window.setTimeout(() => ui.remove(), 600);
      } catch {
        saveBtn.disabled = false;
        saveBtn.style.opacity = "1";
        status.style.color = "#ef4444";
        status.textContent = "Couldn't save — try the toolbar to sign in.";
      }
    });

    actions.append(cancelBtn, saveBtn);
    footer.append(status, actions);
    card.append(heading, textarea, footer);
    container.appendChild(card);
    textarea.focus();
  }

  ctx.onInvalidated(() => ui.remove());
  ui.mount();
}
