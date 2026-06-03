/**
 * Storage areas supported by `wxt/storage`.
 * Maps to the prefixes used by `storage.defineItem('<area>:<key>', ...)`.
 */
export type StorageArea = 'local' | 'sync' | 'session' | 'managed';

export const STORAGE_AREAS: readonly StorageArea[] = [
  'local',
  'sync',
  'session',
  'managed',
] as const;
