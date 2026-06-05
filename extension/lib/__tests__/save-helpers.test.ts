import { describe, it, expect } from "vitest";
import { saveTypeForHost, badgeText } from "@/lib/save-helpers";

describe("saveTypeForHost", () => {
  it("maps chat hosts to conversation, others to page", () => {
    expect(saveTypeForHost("claude.ai")).toBe("conversation");
    expect(saveTypeForHost("example.com")).toBe("page");
  });
});

describe("badgeText", () => {
  it("renders count, empty for 0, caps at 99+", () => {
    expect(badgeText(0)).toBe("");
    expect(badgeText(3)).toBe("3");
    expect(badgeText(150)).toBe("99+");
  });
});
