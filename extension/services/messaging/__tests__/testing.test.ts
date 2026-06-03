import { describe, it, expect, vi } from 'vitest';
import { createMemoryBridge } from '../testing';
import { isNoHandlerError } from '../types';

describe('createMemoryBridge — request/response', () => {
  it('routes a request to the registered handler and returns the result', async () => {
    const bridge = createMemoryBridge();
    bridge.handle('greet', async (payload: { name: string }) => ({
      hello: payload.name,
    }));
    const result = await bridge.request('greet', { name: 'world' }, 'background');
    expect(result).toEqual({ hello: 'world' });
  });

  it('rejects with NO_HANDLER-marked error when no handler is registered', async () => {
    const bridge = createMemoryBridge();
    const err = await bridge
      .request('missing', {}, 'background')
      .catch((e) => e);
    expect(isNoHandlerError(err)).toBe(true);
  });

  it('propagates handler throws to the caller', async () => {
    const bridge = createMemoryBridge();
    bridge.handle('explode', async () => {
      throw new Error('boom');
    });
    await expect(
      bridge.request('explode', {}, 'background'),
    ).rejects.toThrow('boom');
  });

  it('handle() replaces the previous request handler for the same name', async () => {
    const bridge = createMemoryBridge();
    bridge.handle('greet', async () => 'first');
    bridge.handle('greet', async () => 'second');
    const result = await bridge.request('greet', {}, 'background');
    expect(result).toBe('second');
  });

  it('unsubscribe from a replaced handler does not clear the current handler', async () => {
    const bridge = createMemoryBridge();
    const unsubscribeFirst = bridge.handle('greet', async () => 'a');
    bridge.handle('greet', async () => 'b'); // replaces
    unsubscribeFirst(); // MUST NOT clear the current (different) handler
    const result = await bridge.request('greet', {}, 'background');
    expect(result).toBe('b');
  });

  it('unsubscribe from the current handler restores NO_HANDLER', async () => {
    const bridge = createMemoryBridge();
    const unsubscribe = bridge.handle('greet', async () => 'a');
    unsubscribe();
    const err = await bridge
      .request('greet', {}, 'background')
      .catch((e) => e);
    expect(isNoHandlerError(err)).toBe(true);
  });
});

describe('createMemoryBridge — events', () => {
  it('delivers events to every registered listener', () => {
    const bridge = createMemoryBridge();
    const a = vi.fn();
    const b = vi.fn();
    bridge.on('ping', a);
    bridge.on('ping', b);
    bridge.emit('ping', { n: 1 }, 'popup');
    expect(a).toHaveBeenCalledWith({ n: 1 });
    expect(b).toHaveBeenCalledWith({ n: 1 });
  });

  it('emit() with zero listeners is a no-op (never throws)', () => {
    const bridge = createMemoryBridge();
    expect(() => bridge.emit('nothing', { n: 1 }, 'popup')).not.toThrow();
  });

  it('on() returns an unsubscribe function', () => {
    const bridge = createMemoryBridge();
    const listener = vi.fn();
    const unsubscribe = bridge.on('ping', listener);
    unsubscribe();
    bridge.emit('ping', { n: 1 }, 'popup');
    expect(listener).not.toHaveBeenCalled();
  });

  it('a throwing listener does not prevent other listeners from running', () => {
    const bridge = createMemoryBridge();
    const a = vi.fn(() => {
      throw new Error('boom');
    });
    const b = vi.fn();
    bridge.on('ping', a);
    bridge.on('ping', b);
    bridge.emit('ping', { n: 1 }, 'popup');
    expect(b).toHaveBeenCalledWith({ n: 1 });
  });
});
