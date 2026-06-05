/**
 * Pure helpers for the background service worker.
 *
 * Kept here (not under `entrypoints/`) so they are plain modules — WXT treats
 * flat `entrypoints/*.ts` files as entrypoints requiring a default export — and
 * so they are unit-testable in a node environment without any extension globals.
 */
import { isChatDomain } from "@/lib/chat-domains";
import type { SaveType } from "@/services/capture/types";

/**
 * Decide the capture type for a host: known AI-chat surfaces are captured as a
 * conversation; everything else as a page (spec §7.3).
 */
export function saveTypeForHost(host: string): Extract<SaveType, "page" | "conversation"> {
  return isChatDomain(host) ? "conversation" : "page";
}

/**
 * Render the "needs attention" badge text from a count: empty when there is
 * nothing to show, capped at "99+" so it always fits the action badge.
 */
export function badgeText(count: number): string {
  if (count <= 0) return "";
  return count > 99 ? "99+" : String(count);
}
