/**
 * Single source of truth for chat-domain detection.
 *
 * Used to decide whether a tab is a known AI-chat surface so the extractor
 * can switch from article (Readability) extraction to best-effort conversation
 * capture. There is intentionally NO store behind this — it's a static list.
 */
export const CHAT_DOMAINS = [
  "chatgpt.com",
  "chat.openai.com",
  "claude.ai",
  "gemini.google.com",
] as const;

/**
 * Suffix-based, www-insensitive host match.
 *
 * A host matches a domain when it equals the domain or is a subdomain of it.
 * The `.`-boundary `endsWith` check prevents lookalikes such as
 * `notchatgpt.com` from matching `chatgpt.com`.
 */
export function isChatDomain(
  host: string,
  domains: readonly string[] = CHAT_DOMAINS,
): boolean {
  const normalized = host.toLowerCase().replace(/^www\./, "");
  return domains.some((d) => normalized === d || normalized.endsWith("." + d));
}
