import { describe, it, expect } from "vitest";
import { CHAT_DOMAINS, isChatDomain } from "@/lib/chat-domains";

describe("isChatDomain", () => {
  it("matches known chat hosts", () => {
    expect(isChatDomain("chatgpt.com")).toBe(true);
    expect(isChatDomain("claude.ai")).toBe(true);
    expect(isChatDomain("gemini.google.com")).toBe(true);
    expect(isChatDomain("chat.openai.com")).toBe(true);
  });
  it("is suffix-based (subdomains match) and www-insensitive", () => {
    expect(isChatDomain("www.claude.ai")).toBe(true);
    expect(isChatDomain("foo.chatgpt.com")).toBe(true);
  });
  it("rejects unrelated hosts", () => {
    expect(isChatDomain("example.com")).toBe(false);
    expect(isChatDomain("notchatgpt.com.evil.com")).toBe(false);
  });
  it("exposes the const list", () => {
    expect(CHAT_DOMAINS).toContain("claude.ai");
  });
});
