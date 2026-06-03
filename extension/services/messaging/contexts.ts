/**
 * All extension contexts that can send or receive messages via
 * `webext-bridge`. Content scripts and window scripts are parameterised
 * by tab id because there can be many at once.
 */
export type Context =
  | 'background'
  | 'popup'
  | 'options'
  | 'devtools'
  | 'window'
  | `content-script@${number}`
  | `window@${number}`;
