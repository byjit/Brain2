import { describe, it, expect } from "vitest";
import {
  createClient,
  UnauthorizedError,
  NetworkError,
  ApiError,
} from "@/services/api/client";

describe("api client", () => {
  it("save() sends Bearer and parses result", async () => {
    const calls: any[] = [];
    const fetchImpl = async (url: any, init: any) => {
      calls.push([String(url), init]);
      return new Response(JSON.stringify({ id: "x", status: "saved" }), { status: 201 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    const r = await c.save({ type: "note", captured_text: "hi" });
    expect(r).toEqual({ id: "x", status: "saved" });
    expect(calls[0][0]).toBe("http://b/entries");
    expect(calls[0][1].method).toBe("POST");
    expect(calls[0][1].headers.Authorization).toBe("Bearer t");
    expect(JSON.parse(calls[0][1].body)).toMatchObject({ type: "note", captured_text: "hi" });
  });

  it("save() throws UnauthorizedError on 401", async () => {
    const fetchImpl = async () => new Response("nope", { status: 401 });
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await expect(c.save({ type: "note", captured_text: "hi" })).rejects.toBeInstanceOf(UnauthorizedError);
  });

  it("save() throws NetworkError when fetch rejects", async () => {
    const fetchImpl = async () => {
      throw new TypeError("Failed to fetch");
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await expect(c.save({ type: "note", captured_text: "hi" })).rejects.toBeInstanceOf(NetworkError);
  });

  it("getFailed() parses total + entries", async () => {
    const body = {
      total: 1,
      entries: [
        {
          id: "1",
          url: null,
          title: null,
          note: null,
          error_message: "boom",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    const fetchImpl = async () => new Response(JSON.stringify(body), { status: 200 });
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    const r = await c.getFailed();
    expect(r.total).toBe(1);
    expect(r.entries[0].error_message).toBe("boom");
  });

  it("repair() PATCHes the id with a note", async () => {
    const calls: any[] = [];
    const fetchImpl = async (url: any, init: any) => {
      calls.push([String(url), init]);
      return new Response(JSON.stringify({ id: "1", note: "fixed" }), { status: 200 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await c.repair({ id: "1", note: "fixed" });
    expect(calls[0][0]).toBe("http://b/entries/1");
    expect(calls[0][1].method).toBe("PATCH");
    expect(JSON.parse(calls[0][1].body)).toMatchObject({ note: "fixed" });
  });

  // --- additional edge cases ---

  it("getFailed() sends GET with Bearer and no content-type", async () => {
    const calls: any[] = [];
    const fetchImpl = async (url: any, init: any) => {
      calls.push([String(url), init]);
      return new Response(JSON.stringify({ total: 0, entries: [] }), { status: 200 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "tok", fetchImpl });
    await c.getFailed();
    expect(calls[0][0]).toBe("http://b/entries/failed");
    expect(calls[0][1].method).toBe("GET");
    expect(calls[0][1].headers.Authorization).toBe("Bearer tok");
    expect(calls[0][1].headers["Content-Type"]).toBeUndefined();
  });

  it("throws ApiError (with status) on a non-401 HTTP failure", async () => {
    const fetchImpl = async () => new Response("kaboom", { status: 500 });
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    const err = await c.save({ type: "note", captured_text: "hi" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
  });

  it("throws ApiError when the response body is malformed JSON", async () => {
    const fetchImpl = async () => new Response("not json", { status: 201 });
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await expect(c.save({ type: "note", captured_text: "hi" })).rejects.toBeInstanceOf(ApiError);
  });

  it("throws ApiError when the response shape fails Zod validation", async () => {
    const fetchImpl = async () => new Response(JSON.stringify({ id: 123 }), { status: 201 });
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await expect(c.save({ type: "note", captured_text: "hi" })).rejects.toBeInstanceOf(ApiError);
  });

  it("save() rejects invalid input before issuing a request", async () => {
    let called = false;
    const fetchImpl = async () => {
      called = true;
      return new Response("{}", { status: 201 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    // bad `type` value
    await expect(c.save({ type: "bogus" as any })).rejects.toBeTruthy();
    expect(called).toBe(false);
  });

  it("repair() rejects an empty note before issuing a request", async () => {
    let called = false;
    const fetchImpl = async () => {
      called = true;
      return new Response("{}", { status: 200 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await expect(c.repair({ id: "1", note: "" })).rejects.toBeTruthy();
    expect(called).toBe(false);
  });

  it("repair() forwards optional tags when provided", async () => {
    const calls: any[] = [];
    const fetchImpl = async (url: any, init: any) => {
      calls.push([String(url), init]);
      return new Response(JSON.stringify({ id: "1", note: "fixed" }), { status: 200 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    await c.repair({ id: "1", note: "fixed", tags: ["a", "b"] });
    expect(JSON.parse(calls[0][1].body)).toMatchObject({ note: "fixed", tags: ["a", "b"] });
  });

  it("deleteEntry() sends DELETE with Bearer and returns boolean status", async () => {
    const calls: any[] = [];
    const fetchImpl = async (url: any, init: any) => {
      calls.push([String(url), init]);
      return new Response(JSON.stringify({ deleted: true }), { status: 200 });
    };
    const c = createClient({ baseUrl: "http://b", getToken: async () => "t", fetchImpl });
    const r = await c.deleteEntry("123");
    expect(r).toBe(true);
    expect(calls[0][0]).toBe("http://b/entries/123");
    expect(calls[0][1].method).toBe("DELETE");
    expect(calls[0][1].headers.Authorization).toBe("Bearer t");
    expect(calls[0][1].headers["Content-Type"]).toBeUndefined();
  });
});

