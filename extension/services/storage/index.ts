/**
 * Public API for the storage service.
 *
 * Consumers MUST import only from this file. Reaching into internals
 * (`./defineStore`, `./bridge`, etc.) is forbidden — it breaks the
 * service boundary.
 */
export { defineStore } from './defineStore';
export type { DefineStoreConfig } from './defineStore';
export type { Store, StorageArea } from './types';
export { createMemoryStorage } from './testing';
export type { MemoryStorageBackend } from './testing';
