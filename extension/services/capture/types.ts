import { z } from "zod";

export const SaveType = z.enum(["page", "clip", "conversation", "note"]);

export const SaveRequest = z.object({
  url: z.string().url().optional(),
  title: z.string().optional(),
  captured_text: z.string().optional(),
  type: SaveType,
  source_url: z.string().url().optional(),
});

export const SaveResult = z.object({ id: z.string(), status: z.enum(["saved", "updated"]) });

// No refresh token: the M7 backend never issues one. Expiry is handled by silent
// re-auth (Task 3), so we only persist the access token + its absolute expiry.
export const Tokens = z.object({
  accessToken: z.string().nullable(),
  expiresAt: z.number().nullable(), // epoch ms
});

export const FailedEntry = z.object({
  id: z.string(),
  url: z.string().nullable(),
  title: z.string().nullable(),
  note: z.string().nullable(),
  error_message: z.string().nullable(),
  updated_at: z.string(),
});

export type SaveType = z.infer<typeof SaveType>;
export type SaveRequest = z.infer<typeof SaveRequest>;
export type SaveResult = z.infer<typeof SaveResult>;
export type Tokens = z.infer<typeof Tokens>;
export type FailedEntry = z.infer<typeof FailedEntry>;
