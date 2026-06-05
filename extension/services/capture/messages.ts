import { defineMessage } from "@/services/messaging";
import { SaveRequest, SaveResult, FailedEntry } from "./types";
import { z } from "zod";

// popup -> background
export const signInMsg      = defineMessage({ name: "sign-in",      request: z.object({}), response: z.object({ ok: z.boolean() }) });
export const savePageMsg    = defineMessage({ name: "save-page",    request: z.object({ overrideUrl: z.string().url().optional() }), response: SaveResult });
export const saveNoteMsg    = defineMessage({ name: "save-note",    request: z.object({ text: z.string().min(1) }), response: SaveResult });
export const startPickerMsg = defineMessage({ name: "start-picker", request: z.object({}) /* no response: popup closes */ });
export const getFailedMsg   = defineMessage({ name: "get-failed",   request: z.object({}), response: z.object({ total: z.number(), entries: z.array(FailedEntry) }) });
export const repairMsg      = defineMessage({ name: "repair",       request: z.object({ id: z.string(), note: z.string().min(1) }), response: z.object({ ok: z.boolean() }) });

// content -> background
export const saveClipMsg    = defineMessage({ name: "save-clip",    request: SaveRequest, response: SaveResult });

// background -> content (request page/conversation extraction from the active tab)
export const extractPageMsg = defineMessage({
  name: "extract-page",
  request: z.object({ mode: z.enum(["page", "conversation"]) }),
  response: z.object({ title: z.string(), url: z.string(), textContent: z.string() }),
});

// background -> popup (event, no response)
export const needsAttentionChanged = defineMessage({ name: "needs-attention-changed", request: z.object({ count: z.number() }) });
