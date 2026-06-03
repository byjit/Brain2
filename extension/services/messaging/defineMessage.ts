import type { ZodType } from 'zod';
import {
  MessagingError,
  isNoHandlerError,
  type Bridge,
  type Message,
} from './types';

export interface DefineMessageConfig<Req, Res> {
  /** Unique message name. Becomes the wire identifier. */
  name: string;
  /** Zod schema for the request payload. */
  request: ZodType<Req>;
  /**
   * Zod schema for the response. Omit for fire-and-forget events —
   * the returned handle exposes `emit`/`on` instead of `send`/`handle`.
   */
  response?: ZodType<Res>;
  /**
   * Explicit bridge instance. Overrides the module-level default set by
   * `setDefaultBridge()`. Tests pass `createMemoryBridge()` here.
   */
  bridge?: Bridge;
}

let defaultBridge: Bridge | undefined;

/**
 * Install the bridge used by every `defineMessage` call that does not
 * supply an explicit `bridge`. Entry points (background, popup, etc.)
 * should call this once with a `createWebextBridge(...)` instance built
 * from their matching `webext-bridge/<context>` subpath.
 */
export function setDefaultBridge(bridge: Bridge): void {
  defaultBridge = bridge;
}

/** @internal test helper — not exported from the barrel. */
export function __resetDefaultBridge(): void {
  defaultBridge = undefined;
}

function resolveBridge(explicit?: Bridge): Bridge {
  const bridge = explicit ?? defaultBridge;
  if (!bridge) {
    throw new Error(
      '[messaging] no bridge available. Call setDefaultBridge() in your ' +
        'entry point, or pass `bridge` explicitly to defineMessage().',
    );
  }
  return bridge;
}

export function defineMessage<Req, Res = void>(
  config: DefineMessageConfig<Req, Res>,
): Message<Req, Res> {
  const { name, request, response, bridge: explicitBridge } = config;

  function parseRequest(payload: unknown): Req {
    const parsed = request.safeParse(payload);
    if (!parsed.success) {
      throw new MessagingError(
        'INVALID_REQUEST',
        `Invalid request for "${name}"`,
        parsed.error,
      );
    }
    return parsed.data;
  }

  function parseResponse(raw: unknown): Res {
    if (!response) return undefined as never;
    const parsed = response.safeParse(raw);
    if (!parsed.success) {
      throw new MessagingError(
        'INVALID_RESPONSE',
        `Invalid response for "${name}"`,
        parsed.error,
      );
    }
    return parsed.data;
  }

  async function send(payload: Req, options: { to: string }): Promise<Res> {
    const bridge = resolveBridge(explicitBridge);
    const validated = parseRequest(payload);
    let raw: unknown;
    try {
      raw = await bridge.request<Req, unknown>(name, validated, options.to);
    } catch (err) {
      if (err instanceof MessagingError) throw err;
      if (isNoHandlerError(err)) {
        throw new MessagingError(
          'NO_HANDLER',
          `No handler for "${name}"`,
          err,
        );
      }
      throw new MessagingError(
        'HANDLER_THREW',
        `Handler for "${name}" threw`,
        err,
      );
    }
    return parseResponse(raw);
  }

  function handle(
    handler: (payload: Req) => Promise<Res> | Res,
  ): () => void {
    const bridge = resolveBridge(explicitBridge);
    return bridge.handle<Req, Res>(name, async (rawPayload) => {
      const validated = parseRequest(rawPayload);
      const result = await handler(validated);
      // Re-validate before returning so handler bugs surface clearly.
      return parseResponse(result);
    });
  }

  function emit(payload: Req, options: { to: string }): void {
    const bridge = resolveBridge(explicitBridge);
    const validated = parseRequest(payload);
    bridge.emit<Req>(name, validated, options.to);
  }

  function on(callback: (payload: Req) => void): () => void {
    const bridge = resolveBridge(explicitBridge);
    return bridge.on<Req>(name, (rawPayload) => {
      const validated = parseRequest(rawPayload);
      callback(validated);
    });
  }

  if (response) {
    return { name, send, handle } as unknown as Message<Req, Res>;
  }
  return { name, emit, on } as unknown as Message<Req, Res>;
}
