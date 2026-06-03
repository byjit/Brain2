/**
 * Minimal in-memory stand-in for the subset of `wxt/storage` that
 * `defineStore` consumes. Used by service tests and by consumer code
 * that wants to unit-test without a browser runtime.
 *
 * Keys are full `<area>:<name>` strings — identical to what
 * `wxt/storage` uses internally.
 */
export interface MemoryStorageBackend {
  getItem<T>(key: string): Promise<T | undefined>;
  setItem<T>(key: string, value: T): Promise<void>;
  removeItem(key: string): Promise<void>;
  watch<T>(
    key: string,
    callback: (next: T | undefined, prev: T | undefined) => void,
  ): () => void;
}

export function createMemoryStorage(): MemoryStorageBackend {
  const data = new Map<string, unknown>();
  const watchers = new Map<
    string,
    Set<(next: unknown, prev: unknown) => void>
  >();

  function notify(key: string, next: unknown, prev: unknown) {
    const listeners = watchers.get(key);
    if (!listeners) return;
    for (const listener of listeners) listener(next, prev);
  }

  // The real `wxt/utils/storage` backend serialises values through
  // `JSON` on write and parses them on read, so consumers never see the
  // same reference twice. Mirroring that with `structuredClone` here
  // prevents tests written against the memory backend from relying on
  // shared-reference semantics that production would not provide.
  function clone<V>(value: V): V {
    return value === undefined ? value : (structuredClone(value) as V);
  }

  return {
    async getItem<T>(key: string) {
      return clone(data.get(key)) as T | undefined;
    },
    async setItem<T>(key: string, value: T) {
      const prev = data.get(key);
      const next = clone(value);
      data.set(key, next);
      notify(key, next, prev);
    },
    async removeItem(key: string) {
      const prev = data.get(key);
      data.delete(key);
      notify(key, undefined, prev);
    },
    watch<T>(
      key: string,
      callback: (next: T | undefined, prev: T | undefined) => void,
    ) {
      let listeners = watchers.get(key);
      if (!listeners) {
        listeners = new Set();
        watchers.set(key, listeners);
      }
      const cb = callback as (next: unknown, prev: unknown) => void;
      listeners.add(cb);
      return () => {
        listeners!.delete(cb);
      };
    },
  };
}
