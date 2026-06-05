/** @vitest-environment jsdom */
import { describe, it, expect, beforeEach } from "vitest";
import {
  expandSelection,
  contractSelection,
  elementToClip,
} from "@/entrypoints/picker/picker-overlay";

beforeEach(() => {
  document.body.innerHTML = `
    <section id="outer"><article id="mid"><p id="inner">hello <b id="leaf">world</b></p></article></section>`;
});

describe("DOM walk", () => {
  it("expandSelection climbs to the parent block", () => {
    const inner = document.getElementById("inner")!;
    expect(expandSelection(inner).id).toBe("mid");
  });

  it("expandSelection clamps at body (top-level block returns itself)", () => {
    const outer = document.getElementById("outer")!;
    expect(expandSelection(outer)).toBe(outer); // parent is body → clamp
  });

  it("contractSelection descends to the first child element", () => {
    const mid = document.getElementById("mid")!;
    expect(contractSelection(mid).id).toBe("inner");
  });

  it("contractSelection on a leaf returns itself", () => {
    const leaf = document.getElementById("leaf")!;
    expect(contractSelection(leaf)).toBe(leaf);
  });

  it("contractSelection skips leading text nodes to the first child element", () => {
    const inner = document.getElementById("inner")!;
    // <p id="inner">hello <b id="leaf">world</b></p> — first node is text "hello "
    expect(contractSelection(inner).id).toBe("leaf");
  });

  it("elementToClip returns outerHTML + source url + title", () => {
    const inner = document.getElementById("inner")!;
    const clip = elementToClip(inner);
    expect(clip.html).toContain("hello");
    expect(clip.html).toContain('id="inner"');
    expect(typeof clip.sourceUrl).toBe("string");
    expect(typeof clip.title).toBe("string");
  });
});
