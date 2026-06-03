import type { Bridge } from './types';
import { isNoHandlerError, makeNoHandlerError } from './types';

/**
 * Shape of the subset of `webext-bridge` that this adapter consumes.
 *
 * Every entry point (background, popup, content-script, options, devtools)
 * must import the matching `webext-bridge/<context>` subpath — v6 requires
 * context-specific entry points and no universal root export exists. The
 * imported `{ sendMessage, onMessage }` pair is passed into
 * `createWebextBridge()` so that this file (the single vendor touchpoint)
 * stays free of any hard-coded subpath.
 */
export interface WebextBridgeTransport {
  sendMessage: (
    messageId: string,
    data: unknown,
    destination: string,
  ) => Promise<unknown>;
  onMessage: (
    messageId: string,
    handler: (message: { data: unknown }) => unknown | Promise<unknown>,
  ) => void;
}

/**
 * Build a `Bridge` backed by a webext-bridge transport. The adapter
 * maintains its own registries for request handlers and event listeners,
 * installing exactly one dispatcher per message name on the underlying
 * transport. Unsubscribe functions actually remove entries from the
 * registry, fixing the listener-leak present in the previous revision.
 *
 * The adapter also owns NO_HANDLER classification: when a request arrives
 * with no handler registered, the dispatcher throws a marker error that
 * survives webext-bridge's transport layer and is recognised on the
 * caller side via `isNoHandlerError`. No regex matching against vendor
 * error prose is required anywhere above this file.
 */
export function createWebextBridge(transport: WebextBridgeTransport): Bridge {
  type AnyRequestHandler = (payload: unknown) => unknown | Promise<unknown>;
  type AnyListener = (payload: unknown) => void;

  const requestHandlers = new Map<string, AnyRequestHandler>();
  const eventListeners = new Map<string, Set<AnyListener>>();
  const installed = new Set<string>();

  function installDispatcher(name: string) {
    if (installed.has(name)) return;
    installed.add(name);
    transport.onMessage(name, async (message) => {
      const payload = message.data;
      const handler = requestHandlers.get(name);
      if (handler) {
        return handler(payload);
      }
      const listeners = eventListeners.get(name);
      if (listeners && listeners.size > 0) {
        for (const listener of listeners) {
          try {
            listener(payload);
          } catch {
            // broadcast listeners must not affect each other
          }
        }
        return undefined;
      }
      throw makeNoHandlerError(name);
    });
  }

  return {
    async request<Req, Res>(
      name: string,
      payload: Req,
      destination: string,
    ): Promise<Res> {
      try {
        return (await transport.sendMessage(
          name,
          payload,
          destination,
        )) as Res;
      } catch (err) {
        if (isNoHandlerError(err)) throw err;
        // Some webext-bridge versions reject with a string-wrapped error
        // when the target context has no dispatcher installed at all.
        // Preserve the raw error — defineMessage classifies it as
        // HANDLER_THREW unless the marker is set.
        throw err;
      }
    },

    handle<Req, Res>(
      name: string,
      handler: (payload: Req) => Promise<Res> | Res,
    ): () => void {
      installDispatcher(name);
      const wrapped = handler as AnyRequestHandler;
      requestHandlers.set(name, wrapped);
      return () => {
        if (requestHandlers.get(name) === wrapped) {
          requestHandlers.delete(name);
        }
      };
    },

    emit<Req>(name: string, payload: Req, destination: string): void {
      // Broadcast: caller never awaits. Silently drop any transport
      // rejection (including NO_HANDLER for zero listeners) because
      // broadcast-to-no-one is a valid state in pubsub semantics.
      const maybe = transport.sendMessage(name, payload, destination);
      if (maybe && typeof maybe.catch === 'function') {
        maybe.catch(() => {
          /* event mode: swallow */
        });
      }
    },

    on<Req>(name: string, listener: (payload: Req) => void): () => void {
      installDispatcher(name);
      let set = eventListeners.get(name);
      if (!set) {
        set = new Set();
        eventListeners.set(name, set);
      }
      const wrapped = listener as AnyListener;
      set.add(wrapped);
      return () => {
        set!.delete(wrapped);
      };
    },
  };
}
