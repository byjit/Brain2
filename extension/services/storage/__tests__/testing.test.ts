import { describe, it, expect, vi } from 'vitest';
import { createMemoryStorage } from '../testing';

describe('createMemoryStorage', () => {
  it('returns undefined for missing keys', async () => {
    const storage = createMemoryStorage();
    expect(await storage.getItem('local:foo')).toBeUndefined();
  });

  it('stores and retrieves values per full key', async () => {
    const storage = createMemoryStorage();
    await storage.setItem('local:foo', 42);
    expect(await storage.getItem('local:foo')).toBe(42);
  });

  it('treats different areas as separate namespaces', async () => {
    const storage = createMemoryStorage();
    await storage.setItem('local:foo', 'L');
    await storage.setItem('sync:foo', 'S');
    expect(await storage.getItem('local:foo')).toBe('L');
    expect(await storage.getItem('sync:foo')).toBe('S');
  });

  it('removeItem clears a key', async () => {
    const storage = createMemoryStorage();
    await storage.setItem('local:foo', 1);
    await storage.removeItem('local:foo');
    expect(await storage.getItem('local:foo')).toBeUndefined();
  });

  it('watch fires on set with next and previous values', async () => {
    const storage = createMemoryStorage();
    const listener = vi.fn();
    storage.watch('local:foo', listener);
    await storage.setItem('local:foo', 'a');
    await storage.setItem('local:foo', 'b');
    expect(listener).toHaveBeenNthCalledWith(1, 'a', undefined);
    expect(listener).toHaveBeenNthCalledWith(2, 'b', 'a');
  });

  it('watch unsubscribe stops further notifications', async () => {
    const storage = createMemoryStorage();
    const listener = vi.fn();
    const unwatch = storage.watch('local:foo', listener);
    unwatch();
    await storage.setItem('local:foo', 'a');
    expect(listener).not.toHaveBeenCalled();
  });
});
