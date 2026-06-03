import { describe, it, expect, vi } from 'vitest';
import { z } from 'zod';
import { defineMessage } from '../defineMessage';
import { createMemoryBridge } from '../testing';
import { MessagingError } from '../types';

describe('defineMessage (request/response)', () => {
  it('validates the request, runs the handler, validates the response', async () => {
    const bridge = createMemoryBridge();
    const greet = defineMessage({
      name: 'greet',
      request: z.object({ name: z.string() }),
      response: z.object({ hello: z.string() }),
      bridge,
    });
    greet.handle(async ({ name }) => ({ hello: name.toUpperCase() }));
    const result = await greet.send({ name: 'ada' }, { to: 'background' });
    expect(result).toEqual({ hello: 'ADA' });
  });

  it('throws MessagingError(INVALID_REQUEST) on bad request', async () => {
    const bridge = createMemoryBridge();
    const greet = defineMessage({
      name: 'greet',
      request: z.object({ name: z.string() }),
      response: z.object({ hello: z.string() }),
      bridge,
    });
    greet.handle(async ({ name }) => ({ hello: name }));
    const err = await greet
      .send({ name: 42 } as never, { to: 'background' })
      .catch((e) => e);
    expect(err).toBeInstanceOf(MessagingError);
    expect(err.code).toBe('INVALID_REQUEST');
  });

  it('throws MessagingError(INVALID_RESPONSE) when handler returns bad data', async () => {
    const bridge = createMemoryBridge();
    const greet = defineMessage({
      name: 'greet',
      request: z.object({ name: z.string() }),
      response: z.object({ hello: z.string() }),
      bridge,
    });
    greet.handle(async () => ({ hello: 123 }) as never);
    const err = await greet
      .send({ name: 'ada' }, { to: 'background' })
      .catch((e) => e);
    expect(err).toBeInstanceOf(MessagingError);
    expect(err.code).toBe('INVALID_RESPONSE');
  });

  it('throws MessagingError(HANDLER_THREW) when the handler throws', async () => {
    const bridge = createMemoryBridge();
    const boom = defineMessage({
      name: 'boom',
      request: z.object({}),
      response: z.object({}),
      bridge,
    });
    boom.handle(async () => {
      throw new Error('kaboom');
    });
    const err = await boom.send({}, { to: 'background' }).catch((e) => e);
    expect(err).toBeInstanceOf(MessagingError);
    expect(err.code).toBe('HANDLER_THREW');
    expect((err.cause as Error).message).toBe('kaboom');
  });

  it('throws MessagingError(NO_HANDLER) when no handler is registered', async () => {
    const bridge = createMemoryBridge();
    const orphan = defineMessage({
      name: 'orphan',
      request: z.object({}),
      response: z.object({}),
      bridge,
    });
    const err = await orphan.send({}, { to: 'background' }).catch((e) => e);
    expect(err).toBeInstanceOf(MessagingError);
    expect(err.code).toBe('NO_HANDLER');
  });

  it('handle() returns an unsubscribe function', async () => {
    const bridge = createMemoryBridge();
    const greet = defineMessage({
      name: 'greet',
      request: z.object({}),
      response: z.object({ ok: z.boolean() }),
      bridge,
    });
    const unsub = greet.handle(async () => ({ ok: true }));
    unsub();
    const err = await greet.send({}, { to: 'background' }).catch((e) => e);
    expect(err).toBeInstanceOf(MessagingError);
    expect(err.code).toBe('NO_HANDLER');
  });

  it('throws a clear error when no default bridge and no explicit bridge is provided', () => {
    const orphan = defineMessage({
      name: 'orphan',
      request: z.object({}),
      response: z.object({}),
    });
    expect(() =>
      orphan.handle(async () => ({})),
    ).toThrow(/no bridge available/i);
  });
});

describe('defineMessage (event mode)', () => {
  it('emit() delivers validated payloads to on() listeners', () => {
    const bridge = createMemoryBridge();
    const saved = defineMessage({
      name: 'saved',
      request: z.object({ id: z.string() }),
      bridge,
    });
    const listener = vi.fn();
    saved.on(listener);
    saved.emit({ id: 'abc' }, { to: 'popup' });
    expect(listener).toHaveBeenCalledWith({ id: 'abc' });
  });

  it('emit() throws MessagingError(INVALID_REQUEST) on bad payload', () => {
    const bridge = createMemoryBridge();
    const saved = defineMessage({
      name: 'saved',
      request: z.object({ id: z.string() }),
      bridge,
    });
    saved.on(() => {});
    expect(() =>
      saved.emit({ id: 42 } as never, { to: 'popup' }),
    ).toThrow(MessagingError);
  });

  it('emit() with zero listeners is a no-op (never throws)', () => {
    const bridge = createMemoryBridge();
    const saved = defineMessage({
      name: 'saved',
      request: z.object({ id: z.string() }),
      bridge,
    });
    expect(() =>
      saved.emit({ id: 'abc' }, { to: 'popup' }),
    ).not.toThrow();
  });

  it('on() returns an unsubscribe function', () => {
    const bridge = createMemoryBridge();
    const saved = defineMessage({
      name: 'saved',
      request: z.object({ id: z.string() }),
      bridge,
    });
    const listener = vi.fn();
    const unsub = saved.on(listener);
    unsub();
    saved.emit({ id: 'a' }, { to: 'popup' });
    expect(listener).not.toHaveBeenCalled();
  });
});
