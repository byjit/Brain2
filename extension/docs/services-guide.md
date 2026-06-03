# Services Guide

Two reusable chrome-extension service modules live under `services/`:

- **`@/services/storage`** — typed, schema-validated wrapper around `wxt/utils/storage`.
- **`@/services/messaging`** — typed, cross-context messaging layer built on `webext-bridge`.

Both are generic boilerplate primitives. They ship with zero domain knowledge — features define their own stores and message contracts using the factories each service exposes.

## Rules of the road

1. **Import only from the barrel.** `@/services/storage` and `@/services/messaging`. Never reach into internals.
2. **Declare contracts near the feature that owns them**, not inside the services.
3. **Zod schemas are the source of truth.** Types are inferred from them.
4. **Don't import `wxt/utils/storage` or `webext-bridge` directly** anywhere in feature code. The services are the only files that touch either vendor.

## Storage service

### Declaring a store

```ts
// features/theme/store.ts
import { z } from 'zod';
import { defineStore } from '@/services/storage';

export const themeStore = defineStore({
  key: 'theme',
  area: 'local',                               // 'local' | 'sync' | 'session' | 'managed'
  schema: z.enum(['light', 'dark', 'system']),
  defaultValue: 'system',
});
```

### Using it

```ts
import { themeStore } from '@/features/theme/store';

const current = await themeStore.get();    // inferred as 'light' | 'dark' | 'system'
await themeStore.set('dark');               // throws if the value doesn't match the schema
await themeStore.remove();                  // next get() returns the defaultValue

const unwatch = themeStore.watch((next, prev) => {
  console.log('theme changed', prev, '→', next);
});
// later:
unwatch();
```

### What validation does for you

- **On `set`:** the value is validated against the schema. Invalid data throws — corrupt writes fail loud.
- **On `get`:** the stored value is validated. If it fails (older extension version, manual edit, a bug), the store returns `defaultValue` and logs a warning. Your app keeps running.

### Testing stores

```ts
import { defineStore, createMemoryStorage } from '@/services/storage';

const backend = createMemoryStorage();
const store = defineStore({
  key: 'theme',
  area: 'local',
  schema: z.enum(['light', 'dark']),
  defaultValue: 'light',
  _backend: backend,   // swap in the memory backend
});

await store.set('dark');
expect(await store.get()).toBe('dark');
```

`createMemoryStorage()` clones values through `structuredClone` on read and write, mirroring the serialisation semantics of the real `wxt/utils/storage` backend.

## Messaging service

### One-time setup per entry point

`webext-bridge` 6.x requires each extension context (background, popup, content-script, options, devtools) to import its own subpath. The messaging service doesn't hard-code a subpath — instead, each entry point builds a bridge from the matching import and installs it as the default.

```ts
// entrypoints/background.ts
import { sendMessage, onMessage } from 'webext-bridge/background';
import { createWebextBridge, setDefaultBridge } from '@/services/messaging';

setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));

export default defineBackground(() => {
  // register handlers here or via side-effect imports
});
```

```ts
// entrypoints/popup/main.tsx
import { sendMessage, onMessage } from 'webext-bridge/popup';
import { createWebextBridge, setDefaultBridge } from '@/services/messaging';

setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));

// then render your React tree as usual
```

```ts
// entrypoints/content.ts
import { sendMessage, onMessage } from 'webext-bridge/content-script';
import { createWebextBridge, setDefaultBridge } from '@/services/messaging';

export default defineContentScript({
  matches: ['<all_urls>'],
  main() {
    setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));
  },
});
```

Do this once per entry point and every `defineMessage` call in that context will use it automatically.

### Declaring a request/response message

```ts
// features/page/contracts.ts
import { z } from 'zod';
import { defineMessage } from '@/services/messaging';

export const getPageMetadata = defineMessage({
  name: 'page/get-metadata',
  request: z.object({ tabId: z.number() }),
  response: z.object({
    title: z.string(),
    url: z.string().url(),
    description: z.string().optional(),
  }),
});
```

### Handling it

```ts
// features/page/handlers.ts
import { getPageMetadata } from './contracts';

getPageMetadata.handle(async ({ tabId }) => {
  const tab = await browser.tabs.get(tabId);
  return { title: tab.title ?? '', url: tab.url ?? '' };
});
```

Register handlers by importing the module for its side effects:

```ts
// entrypoints/background.ts (after setDefaultBridge)
import '@/features/page/handlers';
```

### Sending it

```ts
import { getPageMetadata } from '@/features/page/contracts';

const meta = await getPageMetadata.send(
  { tabId: 42 },
  { to: 'background' },
);
```

### Declaring a fire-and-forget event

Omit the `response` schema:

```ts
// features/save/events.ts
import { z } from 'zod';
import { defineMessage } from '@/services/messaging';

export const itemSaved = defineMessage({
  name: 'item/saved',
  request: z.object({ id: z.string() }),
  // no response → event mode
});
```

```ts
itemSaved.emit({ id: 'abc' }, { to: 'popup' });

const unsubscribe = itemSaved.on((payload) => {
  console.log('saved', payload.id);
});
```

Events have true broadcast semantics: `emit()` with zero listeners is a no-op (it does not throw). Request/response mode, by contrast, rejects with `NO_HANDLER` when no handler is registered.

### Target contexts

The `to:` field is a typed union:

- `'background'`
- `'popup'`
- `'options'`
- `'devtools'`
- `'window'` — the current window
- `` `content-script@${tabId}` `` — a specific tab's content script
- `` `window@${tabId}` `` — a specific tab's injected window script

Typos are caught at compile time.

### Error handling

Every failure throws a `MessagingError` with a discriminated `code`:

```ts
import { MessagingError } from '@/services/messaging';

try {
  await getPageMetadata.send({ tabId: 42 }, { to: 'background' });
} catch (err) {
  if (err instanceof MessagingError) {
    switch (err.code) {
      case 'INVALID_REQUEST':   // payload failed request schema
      case 'INVALID_RESPONSE':  // handler returned data that failed response schema
      case 'NO_HANDLER':        // no handler registered on the target
      case 'HANDLER_THREW':     // handler threw; original error on err.cause
    }
  }
}
```

### Testing messages

Pass an explicit in-memory bridge via the `bridge` option — no `setDefaultBridge` required in tests:

```ts
import { defineMessage, createMemoryBridge } from '@/services/messaging';

const bridge = createMemoryBridge();
const greet = defineMessage({
  name: 'greet',
  request: z.object({ name: z.string() }),
  response: z.object({ hello: z.string() }),
  bridge,
});

greet.handle(async ({ name }) => ({ hello: name }));
const result = await greet.send({ name: 'ada' }, { to: 'background' });
expect(result).toEqual({ hello: 'ada' });
```

## Swapping vendors

- **Replace `wxt/utils/storage`:** edit `services/storage/defineStore.ts`. It is the only file in the repo that imports it.
- **Replace `webext-bridge`:** edit `services/messaging/bridge.ts` (for the adapter) and each entry point's `setDefaultBridge` call. Feature code — every `defineMessage()` declaration and every `.send()` / `.handle()` / `.emit()` / `.on()` call site — remains untouched.
