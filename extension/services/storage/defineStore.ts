import { storage } from 'wxt/utils/storage';
import type { ZodType } from 'zod';
import type { StorageArea } from './areas';
import type { Store } from './types';
import type { MemoryStorageBackend } from './testing';

/**
 * Structural backend interface. Both the real `wxt/utils/storage` adapter and
 * `createMemoryStorage()` implement this shape, so tests can swap backends
 * without touching `browser.*`.
 */
type Backend = MemoryStorageBackend;

export interface DefineStoreConfig<T> {
  /** Key within the chosen area. Combined as `<area>:<key>`. */
  key: string;
  /** Which `browser.storage` area to use. */
  area: StorageArea;
  /** Zod schema — drives runtime validation and TypeScript inference. */
  schema: ZodType<T>;
  /** Value returned when the key is empty or corrupt. */
  defaultValue: T;
  /**
   * @internal Backend override for tests. Defaults to the real
   * `wxt/utils/storage` adapter. Not wired through the barrel; prefer
   * passing an instance in test setup code only.
   */
  _backend?: Backend;
}

/**
 * Real backend: a thin wrapper around `wxt/utils/storage` that matches the
 * structural `Backend` interface. This is the ONLY place in the codebase
 * that imports from `wxt/utils/storage`.
 *
 * NOTE: The task plan specifies `import { storage } from 'wxt/storage'`, but
 * this package path does not exist in wxt's exports map. The correct path is
 * `wxt/utils/storage`. The `StorageItemKey` in @wxt-dev/storage@1.2.8 is a
 * union of four specific area prefixes (`local:`, `sync:`, `session:`,
 * `managed:`), so neither `\`local:${string}\`` nor `\`${string}:${string}\``
 * is assignable. Casting through `any` is the only safe escape hatch, kept
 * isolated to this file only.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const toKey = (key: string) => key as any;

const wxtBackend: Backend = {
  async getItem<T>(key: string) {
    const value = await storage.getItem<T>(toKey(key));
    return value ?? undefined;
  },
  async setItem<T>(key: string, value: T) {
    await storage.setItem(toKey(key), value);
  },
  async removeItem(key: string) {
    await storage.removeItem(toKey(key));
  },
  watch<T>(
    key: string,
    callback: (next: T | undefined, prev: T | undefined) => void,
  ) {
    return storage.watch<T>(
      toKey(key),
      (next, prev) => callback(next ?? undefined, prev ?? undefined),
    );
  },
};

export function defineStore<T>(config: DefineStoreConfig<T>): Store<T> {
  const {
    key,
    area,
    schema,
    defaultValue,
    _backend = wxtBackend,
  } = config;
  const fullKey = `${area}:${key}`;

  function validateRead(raw: unknown): T {
    const parsed = schema.safeParse(raw);
    if (parsed.success) return parsed.data;
    console.warn(
      `[storage] corrupt value at "${fullKey}", falling back to default`,
      parsed.error,
    );
    return defaultValue;
  }

  return {
    async get() {
      const raw = await _backend.getItem<unknown>(fullKey);
      if (raw === undefined) return defaultValue;
      return validateRead(raw);
    },
    async set(value: T) {
      const parsed = schema.parse(value); // throws on invalid input
      await _backend.setItem(fullKey, parsed);
    },
    async remove() {
      await _backend.removeItem(fullKey);
    },
    watch(callback) {
      return _backend.watch<unknown>(fullKey, (nextRaw, prevRaw) => {
        const next =
          nextRaw === undefined ? defaultValue : validateRead(nextRaw);
        const prev =
          prevRaw === undefined ? defaultValue : validateRead(prevRaw);
        callback(next, prev);
      });
    },
  };
}
