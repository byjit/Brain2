/** Typed accessors for Vite environment variables injected at build time. */
export const config = {
  apiUrl: import.meta.env.VITE_BRAIN2_API_URL as string,
  oauthClientId: import.meta.env.VITE_BRAIN2_OAUTH_CLIENT_ID as string,
  // Origin of the web platform/dashboard (no trailing slash). Falls back to the
  // local dev server port when the env var is unset.
  platformUrl:
    (import.meta.env.VITE_BRAIN2_PLATFORM_URL as string | undefined) ??
    "http://localhost:3000",
};

/** Absolute URL of the platform dashboard page. */
export const dashboardUrl = `${config.platformUrl.replace(/\/$/, "")}/dashboard`;
