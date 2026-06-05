/** Typed accessors for Vite environment variables injected at build time. */
export const config = {
  apiUrl: import.meta.env.VITE_BRAIN2_API_URL as string,
  oauthClientId: import.meta.env.VITE_BRAIN2_OAUTH_CLIENT_ID as string,
};
