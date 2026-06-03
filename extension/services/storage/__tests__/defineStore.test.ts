import { describe, it, expect, vi } from 'vitest';
import { z } from 'zod';
import { defineStore } from '../defineStore';
import { createMemoryStorage } from '../testing';

describe('defineStore', () => {
  it('returns defaultValue when key is empty', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'theme',
      area: 'local',
      schema: z.enum(['light', 'dark']),
      defaultValue: 'light',
      _backend: backend,
    });
    expect(await store.get()).toBe('light');
  });

  it('round-trips a valid value through set/get', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'theme',
      area: 'local',
      schema: z.enum(['light', 'dark']),
      defaultValue: 'light',
      _backend: backend,
    });
    await store.set('dark');
    expect(await store.get()).toBe('dark');
  });

  it('throws on set when the value fails schema validation', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'count',
      area: 'local',
      schema: z.number().int().nonnegative(),
      defaultValue: 0,
      _backend: backend,
    });
    await expect(store.set(-1 as never)).rejects.toThrow();
  });

  it('returns defaultValue and warns when stored data is corrupt', async () => {
    const backend = createMemoryStorage();
    await backend.setItem('local:theme', 'purple'); // bypass validation
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const store = defineStore({
      key: 'theme',
      area: 'local',
      schema: z.enum(['light', 'dark']),
      defaultValue: 'light',
      _backend: backend,
    });
    expect(await store.get()).toBe('light');
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it('remove() restores defaultValue', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'theme',
      area: 'local',
      schema: z.enum(['light', 'dark']),
      defaultValue: 'light',
      _backend: backend,
    });
    await store.set('dark');
    await store.remove();
    expect(await store.get()).toBe('light');
  });

  it('watch fires with validated next/prev values', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'theme',
      area: 'local',
      schema: z.enum(['light', 'dark']),
      defaultValue: 'light',
      _backend: backend,
    });
    const listener = vi.fn();
    store.watch(listener);
    await store.set('dark');
    expect(listener).toHaveBeenCalledWith('dark', 'light');
  });

  it('watch returns an unsubscribe function', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'theme',
      area: 'local',
      schema: z.enum(['light', 'dark']),
      defaultValue: 'light',
      _backend: backend,
    });
    const listener = vi.fn();
    const unwatch = store.watch(listener);
    unwatch();
    await store.set('dark');
    expect(listener).not.toHaveBeenCalled();
  });

  it('uses the correct area prefix in the backend key', async () => {
    const backend = createMemoryStorage();
    const store = defineStore({
      key: 'token',
      area: 'sync',
      schema: z.string(),
      defaultValue: '',
      _backend: backend,
    });
    await store.set('abc');
    expect(await backend.getItem('sync:token')).toBe('abc');
  });
});
