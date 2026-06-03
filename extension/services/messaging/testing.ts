import type { Bridge } from './types';
import { makeNoHandlerError } from './types';

/**
 * In-memory `Bridge` implementation for tests and consumer unit tests.
 *
 * Semantics intentionally mirror the real webext-bridge adapter:
 * - `request` expects exactly one `handle(name, ...)` registration and
 *   rejects with a NO_HANDLER-marked error when absent.
 * - `emit` broadcasts to zero or more `on(name, ...)` listeners and
 *   never rejects on empty audiences.
 *
 * Keeping request and broadcast semantics separate eliminates the
 * "callers distinguish by whether they await" kludge in the previous
 * revision.
 */
export function createMemoryBridge(): Bridge {
  type AnyRequestHandler = (payload: unknown) => unknown | Promise<unknown>;
  type AnyListener = (payload: unknown) => void;

  const requestHandlers = new Map<string, AnyRequestHandler>();
  const eventListeners = new Map<string, Set<AnyListener>>();

  return {
    async request<Req, Res>(
      name: string,
      payload: Req,
      _destination: string,
    ): Promise<Res> {
      const handler = requestHandlers.get(name);
      if (!handler) {
        throw makeNoHandlerError(name);
      }
      return (await handler(payload)) as Res;
    },

    handle<Req, Res>(
      name: string,
      handler: (payload: Req) => Promise<Res> | Res,
    ): () => void {
      const wrapped = handler as AnyRequestHandler;
      requestHandlers.set(name, wrapped);
      return () => {
        if (requestHandlers.get(name) === wrapped) {
          requestHandlers.delete(name);
        }
      };
    },

    emit<Req>(name: string, payload: Req, _destination: string): void {
      const listeners = eventListeners.get(name);
      if (!listeners) return;
      for (const listener of listeners) {
        try {
          listener(payload);
        } catch {
          // broadcast listeners must not affect each other
        }
      }
    },

    on<Req>(name: string, listener: (payload: Req) => void): () => void {
      let set = eventListeners.get(name);
      if (!set) {
        set = new Set();
        eventListeners.set(name, set);
      }
      const wrapped = listener as AnyListener;
      set.add(wrapped);
      return () => {
        set!.delete(wrapped);
        if (set!.size === 0) eventListeners.delete(name);
      };
    },
  };
}
