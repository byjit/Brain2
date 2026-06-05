import { createWebextBridge, setDefaultBridge } from "@/services/messaging";
import { config } from "@/lib/config";
import { createClient } from "@/services/api/client";
import { getValidAccessToken, signIn } from "@/services/auth/oauth";
import { saveTypeForHost, badgeText } from "@/lib/save-helpers";
import { needsAttentionStore } from "@/services/capture/stores";
import {
  savePageMsg,
  saveNoteMsg,
  saveClipMsg,
  startPickerMsg,
  signInMsg,
  getFailedMsg,
  repairMsg,
  needsAttentionChanged,
  extractPageMsg,
} from "@/services/capture/messages";

/**
 * Auth gate: resolves the access token or throws a recognizable signed_out error.
 * The message layer propagates this to the popup, which shows <SignIn/>. Response
 * schemas stay SaveResult-only (ISP), so we throw rather than widen the contract.
 */
class SignedOutError extends Error {
  constructor() {
    super("signed_out");
    this.name = "SignedOutError";
  }
}

async function requireToken(): Promise<string> {
  const t = await getValidAccessToken();
  if (!t) throw new SignedOutError();
  return t;
}

const client = createClient({ baseUrl: config.apiUrl, getToken: requireToken });

const POLL_ALARM = "poll-failed";

/** Paint the action badge from the persisted "needs attention" count. */
async function updateBadge(): Promise<void> {
  const count = await needsAttentionStore.get();
  await browser.action.setBadgeText({ text: badgeText(count) });
  await browser.action.setBadgeBackgroundColor({ color: "#DC2626" }); // a clear "attention" red badge
}

/** Pull the failed-entry total, persist it, repaint the badge, and notify the popup. */
async function refreshFailed(): Promise<number> {
  const { total } = await client.getFailed();
  await needsAttentionStore.set(total);
  await updateBadge();
  needsAttentionChanged.emit({ count: total }, { to: "popup" });
  return total;
}

function ensureAlarm(): void {
  browser.alarms.create(POLL_ALARM, { periodInMinutes: 5 });
}

/**
 * Register every message handler against the (already-installed) default bridge.
 * Split out so the bridge is set up first; each `.handle()`/`.on()` subscribes
 * synchronously via webext-bridge's port transport.
 */
function registerMessageHandlers(): void {
  // ---- save page (current tab via injected extractor, or override URL only) ----
  savePageMsg.handle(async ({ overrideUrl }) => {
    await requireToken(); // gate early
    if (overrideUrl) {
      // We can't scrape a page we're not on; send the URL — the backend re-fetches it.
      const host = new URL(overrideUrl).hostname;
      return client.save({ type: saveTypeForHost(host), url: overrideUrl });
    }
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !tab.url) throw new Error("No active tab to save");
    const host = new URL(tab.url).hostname;
    const mode = saveTypeForHost(host);
    await browser.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["/content-scripts/content.js"],
    });
    const extracted = await extractPageMsg.send({ mode }, { to: `content-script@${tab.id}` });
    return client.save({
      type: mode,
      url: extracted.url,
      title: extracted.title || undefined,
      captured_text: extracted.textContent || undefined,
    });
  });

  // ---- save custom note ----
  // The backend persists `captured_text` as the note's content and uses it verbatim
  // (note_source="user", NO summarization — see backend note_resolver.py). So a note is
  // just `{ type: "note", captured_text }`; no separate `note` field is required.
  saveNoteMsg.handle(async ({ text }) => {
    await requireToken();
    return client.save({ type: "note", captured_text: text });
  });

  // ---- save clip (from picker content script) ----
  saveClipMsg.handle(async (req) => {
    await requireToken();
    return client.save(req);
  });

  // ---- start element picker (event: popup closes, no response) ----
  startPickerMsg.on(async () => {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;
    await browser.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["/content-scripts/picker.js"],
    });
  });

  // ---- interactive sign-in ----
  signInMsg.handle(async () => {
    try {
      await signIn();
      return { ok: true };
    } catch {
      return { ok: false };
    }
  });

  // ---- needs-attention list ----
  getFailedMsg.handle(async () => {
    await requireToken();
    const r = await client.getFailed();
    await needsAttentionStore.set(r.total);
    await updateBadge();
    return r;
  });

  // ---- repair a failed entry ----
  repairMsg.handle(async ({ id, note }) => {
    await requireToken();
    await client.repair({ id, note });
    const next = Math.max(0, (await needsAttentionStore.get()) - 1);
    await needsAttentionStore.set(next);
    await updateBadge();
    needsAttentionChanged.emit({ count: next }, { to: "popup" });
    return { ok: true };
  });
}

export default defineBackground(() => {
  // Native lifecycle listeners are registered SYNCHRONOUSLY so the SW never misses a
  // wake event after a restart (svc-register-listeners-synchronously).
  browser.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name !== POLL_ALARM) return;
    // signed-out is normal here; swallow so the alarm never throws.
    refreshFailed().catch(() => {});
  });
  browser.runtime.onInstalled.addListener(() => {
    ensureAlarm();
    updateBadge().catch(() => {});
  });
  browser.runtime.onStartup.addListener(() => {
    ensureAlarm();
    updateBadge().catch(() => {});
  });
  // Belt-and-braces: ensure the polling alarm exists on every cold start, not only on
  // install/startup events (which a re-spawned SW may not receive).
  ensureAlarm();

  // webext-bridge/background registers its connect listener at import time and pulls in
  // webextension-polyfill, which throws under WXT's build-time fake-browser prerender.
  // Loading it dynamically here keeps it OUT of prerender (defineBackground never runs
  // `main()` during build) while still wiring the message handlers at real SW startup.
  void (async () => {
    const { sendMessage, onMessage } = await import("webext-bridge/background");
    setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));
    registerMessageHandlers();
  })();
});
