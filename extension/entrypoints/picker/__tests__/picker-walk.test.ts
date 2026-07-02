/** @vitest-environment jsdom */
import { describe, it, expect, beforeEach } from "vitest";
import {
  toggleSelection,
  joinClips,
  elementToClip,
} from "@/entrypoints/picker/picker-overlay";

beforeEach(() => {
  document.body.innerHTML = `
    <section id="outer"><article id="mid"><p id="inner">hello <b id="leaf">world</b></p></article></section>
    <aside id="sibling">note</aside>`;
});

const el = (id: string): Element => document.getElementById(id)!;

describe("toggleSelection", () => {
  it("adds an element to an empty set", () => {
    const next = toggleSelection([], el("inner"));
    expect(next.map((e) => e.id)).toEqual(["inner"]);
  });

  it("appends disjoint elements in click order", () => {
    let sel = toggleSelection([], el("inner"));
    sel = toggleSelection(sel, el("sibling"));
    expect(sel.map((e) => e.id)).toEqual(["inner", "sibling"]);
  });

  it("toggles an already-selected element off", () => {
    const sel = toggleSelection([el("inner")], el("inner"));
    expect(sel).toEqual([]);
  });

  it("ignores a descendant of an already-selected element (no double-select)", () => {
    const sel = toggleSelection([el("mid")], el("leaf"));
    expect(sel.map((e) => e.id)).toEqual(["mid"]);
  });

  it("subsumes selected descendants when their ancestor is added", () => {
    let sel = toggleSelection([], el("leaf"));
    sel = toggleSelection(sel, el("inner")); // inner contains leaf
    expect(sel.map((e) => e.id)).toEqual(["inner"]);
  });

  it("does not mutate the input array", () => {
    const input = [el("sibling")];
    toggleSelection(input, el("inner"));
    expect(input.map((e) => e.id)).toEqual(["sibling"]);
  });
});

describe("joinClips", () => {
  it("joins blocks with a horizontal rule", () => {
    expect(joinClips(["# A", "# B"])).toBe("# A\n---\n# B");
  });

  it("returns a single block unchanged", () => {
    expect(joinClips(["only"])).toBe("only");
  });

  it("returns an empty string for no blocks", () => {
    expect(joinClips([])).toBe("");
  });
});

describe("elementToClip", () => {
  it("returns outerHTML + source url + title", () => {
    const clip = elementToClip(el("inner"));
    expect(clip.html).toContain("hello");
    expect(clip.html).toContain('id="inner"');
    expect(typeof clip.sourceUrl).toBe("string");
    expect(typeof clip.title).toBe("string");
  });
});
