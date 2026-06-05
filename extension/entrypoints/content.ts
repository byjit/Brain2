import { sendMessage, onMessage } from "webext-bridge/content-script";
import { createWebextBridge, setDefaultBridge } from "@/services/messaging";
import { extractPageMsg } from "@/services/capture/messages";
import { extractReadable, extractConversation } from "@/lib/extract";

/**
 * Page-extractor content script.
 *
 * Registered as `runtime` (not auto-injected on any URL) — the background SW
 * injects it on demand via `browser.scripting.executeScript`, which resolves
 * only after `main()` has run and the handler is registered. A subsequent
 * `extractPageMsg.send(..., { to: "content-script@<tabId>" })` therefore always
 * finds the handler.
 */
export default defineContentScript({
  registration: "runtime",
  matches: [],
  main(_ctx) {
    setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));
    extractPageMsg.handle(async ({ mode }) => {
      const { title, textContent } =
        mode === "conversation"
          ? extractConversation(document)
          : extractReadable(document);
      return { title: title || document.title || "", url: location.href, textContent };
    });
  },
});
