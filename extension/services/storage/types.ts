import type { StorageArea } from './areas';

/**
 * Typed handle returned by `defineStore`. Consumers interact with storage
 * through this interface only — they never touch `browser.storage.*` or
 * `wxt/storage` directly.
 */
export interface Store<T> {
  /** Read the current value. Returns `defaultValue` if missing or corrupt. */
  get(): Promise<T>;
  /** Validate against the schema and write. Throws on invalid input. */
  set(value: T): Promise<void>;
  /** Clear the key. Subsequent `get()` returns `defaultValue`. */
  remove(): Promise<void>;
  /** Subscribe to changes. Returns an unsubscribe function. */
  watch(callback: (next: T, prev: T) => void): () => void;
}

export type { StorageArea };
