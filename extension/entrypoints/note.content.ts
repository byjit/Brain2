import { sendMessage, onMessage } from "webext-bridge/content-script";
import { createWebextBridge, setDefaultBridge } from "@/services/messaging";
import { mountNoteModal } from "./note/note-modal";

export default defineContentScript({
  registration: "runtime",
  matches: [],
  main(ctx) {
    setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));
    void mountNoteModal(ctx);
  },
});
