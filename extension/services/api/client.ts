import { z } from "zod";
import { SaveRequest, SaveResult, FailedEntry } from "@/services/capture/types";

// Shape of GET /entries/failed. Kept inline (rather than added to capture/types.ts)
// because it is only ever consumed here — the popup/UI reads individual FailedEntry
// rows, never the wrapper. Inlining avoids touching Task 1's schema file.
const FailedList = z.object({ total: z.number(), entries: z.array(FailedEntry) });
type FailedList = z.infer<typeof FailedList>;

/** The caller is not (or no longer) authenticated — background should trigger re-auth. */
export class UnauthorizedError extends Error {
  constructor(message = "Unauthorized (401) — token missing or expired") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

/** The request never reached the server (DNS, offline, CORS, fetch threw). Retryable. */
export class NetworkError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "NetworkError";
  }
}

/** Any other backend failure: non-2xx status, unparseable body, or schema mismatch. */
export class ApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface ClientConfig {
  baseUrl: string;
  /** Resolves the current Brain2 access token. Awaited on every request. */
  getToken: () => Promise<string>;
  /** Injected for testability; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
}

interface RequestOptions {
  method: "GET" | "POST" | "PATCH";
  path: string;
  /** When present, serialized as a JSON body with the matching Content-Type header. */
  json?: unknown;
}

export interface Brain2ApiClient {
  save: (req: SaveRequest) => Promise<SaveResult>;
  getFailed: () => Promise<FailedList>;
  repair: (input: { id: string; note: string; tags?: string[] }) => Promise<void>;
}

// PATCH body contract: note is required (min 1 char), tags optional. Mirrors the
// M7 backend validation so we fail fast client-side instead of round-tripping garbage.
const RepairInput = z.object({
  id: z.string().min(1),
  note: z.string().min(1),
  tags: z.array(z.string()).optional(),
});

export const createClient = ({
  baseUrl,
  getToken,
  fetchImpl = fetch,
}: ClientConfig): Brain2ApiClient => {
  /**
   * Single request helper: attaches the Bearer token, performs the fetch (network
   * failures become NetworkError), and maps HTTP status to typed errors. Returns the
   * raw Response so callers decide whether/how to parse the body.
   */
  const request = async ({ method, path, json }: RequestOptions): Promise<Response> => {
    const token = await getToken();
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
    };

    let res: Response;
    try {
      res = await fetchImpl(`${baseUrl}${path}`, {
        method,
        headers,
        ...(json !== undefined ? { body: JSON.stringify(json) } : {}),
      });
    } catch (cause) {
      throw new NetworkError(
        `Network request to ${method} ${path} failed (offline or unreachable)`,
        { cause },
      );
    }

    if (res.status === 401) {
      throw new UnauthorizedError();
    }
    if (!res.ok) {
      throw new ApiError(`${method} ${path} failed with status ${res.status}`, res.status);
    }
    return res;
  };

  /** Parse a successful response body and validate it against the given schema. */
  const parseJson = async <T>(res: Response, schema: z.ZodType<T>, label: string): Promise<T> => {
    let body: unknown;
    try {
      body = await res.json();
    } catch (cause) {
      throw new ApiError(`${label} returned a malformed (non-JSON) response`, res.status);
    }
    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      throw new ApiError(`${label} returned an unexpected shape: ${parsed.error.message}`, res.status);
    }
    return parsed.data;
  };

  return {
    save: async (req) => {
      // Validate before sending so we never push malformed payloads to the backend.
      const payload = SaveRequest.parse(req);
      const res = await request({ method: "POST", path: "/entries", json: payload });
      return parseJson(res, SaveResult, "POST /entries");
    },

    getFailed: async () => {
      const res = await request({ method: "GET", path: "/entries/failed" });
      return parseJson(res, FailedList, "GET /entries/failed");
    },

    repair: async (input) => {
      const { id, note, tags } = RepairInput.parse(input);
      await request({
        method: "PATCH",
        path: `/entries/${encodeURIComponent(id)}`,
        json: { note, ...(tags ? { tags } : {}) },
      });
      // Backend returns the full updated entry; we only need 2xx, so resolve void.
    },
  };
};
