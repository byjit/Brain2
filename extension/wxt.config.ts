import { defineConfig } from 'wxt';
import { loadEnv } from 'vite';
import tailwindcss from '@tailwindcss/vite';

// Derive origin at Node/build time. WXT/Vite only inject VITE_* vars into the
// app's import.meta.env at runtime — they are NOT present on process.env here in
// the config — so we explicitly load the .env files to build host_permissions.
const env = loadEnv(process.env.NODE_ENV ?? 'production', process.cwd(), 'VITE_');
const apiOrigin = env.VITE_BRAIN2_API_URL ?? 'http://localhost:8000';

// See https://wxt.dev/api/config.html
export default defineConfig({
  modules: ['@wxt-dev/module-react'],
  vite: () => ({
    plugins: [tailwindcss()],
  }),
  // Function form so the manifest can vary per target browser (see `key` below).
  manifest: ({ browser }) => ({
    name: 'Brain2',
    permissions: ['activeTab', 'scripting', 'storage', 'identity', 'alarms'],
    // host_permissions makes background service-worker fetches CORS-exempt in MV3
    host_permissions: [`${apiOrigin}/*`],
    // default_title is derived from the popup <title> by WXT; kept here for clarity only
    action: { default_title: 'Save to Brain2' },
    // Pinned public key → deterministic extension ID across every Chromium browser
    // (Chrome + Edge) for dev/unpacked builds. This keeps the OAuth redirect URL
    // (https://<id>.chromiumapp.org/) identical in both, so only one redirect URI
    // must be registered with the backend while developing. The matching private
    // key (brain2-extension.pem) is gitignored; store-published builds get their
    // own store-assigned IDs (see docs/production-setup.md). `key` is a
    // Chromium-only manifest field — Firefox uses browser_specific_settings and
    // AMO rejects `key`, so it is omitted for the Firefox target.
    ...(browser === 'firefox'
      ? {}
      : {
          key: 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmW2kcK7FsgQ0c5AsciaTkOGj4NqgLpmXKQvv9TQWygZRA11qt8dE81Fj1yD968D90XyRpPqhY47v7iDgTR97MkUc1jFxXEgK+inHy/1k18TEfJgIczMuZuWslh62En1IxFTXB4Jf6bytNaU7L4j02tHTEMMJHTCZOTSJQZn6Lm9n4CsTXnyFFybJz5lDQSQGrLimv6a4LQf8XTVpHMu5sGBl//8myaLbNo8jRr6iitfLZWhxoEgg/O0W5Fa0pceh0ej/uPu2cGZlBUDiXeEk4wVTIun2Jg9ITWxKWIgjPqVd11QW9lrZQJ8968M2RVbgH1wo/pPEDRgYYCgl0z6GJQIDAQAB',
        }),
  }),
});
