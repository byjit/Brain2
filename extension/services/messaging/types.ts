import type { Context } from './contexts';

export type { Context };

export type MessagingErrorCode =
  | 'INVALID_REQUEST'
  | 'INVALID_RESPONSE'
  | 'NO_HANDLER'
  | 'HANDLER_THREW';

/**
 * Typed error surface for all messaging failures. Callers can inspect
 * `code` to distinguish transport errors from validation errors.
 */
export class MessagingError extends Error {
  readonly code: MessagingErrorCode;
  readonly cause?: unknown;

  constructor(code: MessagingErrorCode, message: string, cause?: unknown) {
    super(message);
    this.name = 'MessagingError';
    this.code = code;
    this.cause = cause;
  }
}

/**
 * Structural bridge interface — the single abstraction that both the real
 * webext-bridge adapter and `createMemoryBridge()` implement.
 *
 * Request/response and broadcast/event modes are deliberately separate
 * methods so the memory bridge (and the real adapter) can enforce the
 * correct semantics for each: request expects exactly one handler and
 * surfaces NO_HANDLER when missing; emit fans out to zero or more
 * listeners and never errors on an empty audience.
 */
export interface Bridge {
  /** Request/response: rejects with a NO_HANDLER-marked error if none registered. */
  request<Req, Res>(
    name: string,
    payload: Req,
    destination: string,
  ): Promise<Res>;
  /** Register the single request handler for `name`. Returns unsubscribe. */
  handle<Req, Res>(
    name: string,
    handler: (payload: Req) => Promise<Res> | Res,
  ): () => void;
  /** Fire-and-forget broadcast; never rejects on zero listeners. */
  emit<Req>(name: string, payload: Req, destination: string): void;
  /** Register an event listener for `name`. Returns unsubscribe. */
  on<Req>(name: string, listener: (payload: Req) => void): () => void;
}

/**
 * Error marker used by bridge implementations to signal "no handler for
 * this message name" in a way that survives serialisation across the
 * webext-bridge transport. `defineMessage` checks this flag on caught
 * errors to emit `MessagingError('NO_HANDLER', ...)`.
 */
export interface NoHandlerMarker {
  __messagingNoHandler: true;
}

export function isNoHandlerError(err: unknown): err is Error & NoHandlerMarker {
  return (
    typeof err === 'object' &&
    err !== null &&
    (err as Partial<NoHandlerMarker>).__messagingNoHandler === true
  );
}

export function makeNoHandlerError(name: string): Error & NoHandlerMarker {
  const err = new Error(`No handler for "${name}"`) as Error & NoHandlerMarker;
  err.__messagingNoHandler = true;
  return err;
}

/**
 * Typed handle returned by `defineMessage`.
 *
 * - With a response schema: request/response mode → use `send` + `handle`.
 * - Without a response schema: fire-and-forget mode → use `emit` + `on`.
 */
export interface RequestResponseMessage<Req, Res> {
  readonly name: string;
  send(payload: Req, options: { to: Context }): Promise<Res>;
  handle(handler: (payload: Req) => Promise<Res> | Res): () => void;
}

export interface EventMessage<Req> {
  readonly name: string;
  emit(payload: Req, options: { to: Context }): void;
  on(callback: (payload: Req) => void): () => void;
}

export type Message<Req, Res = void> = [Res] extends [void]
  ? EventMessage<Req>
  : RequestResponseMessage<Req, Res>;
