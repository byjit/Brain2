/**
 * Public API for the messaging service.
 *
 * Consumers MUST import only from this file. Reaching into internals
 * (`./bridge`, `./defineMessage`, etc.) is forbidden — it breaks the
 * service boundary and defeats the point of the adapter.
 */
export { defineMessage, setDefaultBridge } from './defineMessage';
export type { DefineMessageConfig } from './defineMessage';
export { createWebextBridge } from './bridge';
export type { WebextBridgeTransport } from './bridge';
export { createMemoryBridge } from './testing';
export {
  MessagingError,
  isNoHandlerError,
} from './types';
export type {
  Bridge,
  Context,
  Message,
  MessagingErrorCode,
  RequestResponseMessage,
  EventMessage,
} from './types';
