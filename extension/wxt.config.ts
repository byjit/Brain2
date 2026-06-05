import { defineConfig } from 'wxt';
import tailwindcss from '@tailwindcss/vite';

// Derive origin at Node/build time; VITE_* env vars are not reliably available
// in this config file via import.meta.env.
const apiOrigin = process.env.VITE_BRAIN2_API_URL ?? 'http://localhost:8000';

// See https://wxt.dev/api/config.html
export default defineConfig({
  modules: ['@wxt-dev/module-react'],
  vite: () => ({
    plugins: [tailwindcss()],
  }),
  manifest: {
    name: 'Brain2',
    permissions: ['activeTab', 'scripting', 'storage', 'identity', 'alarms'],
    // host_permissions makes background service-worker fetches CORS-exempt in MV3
    host_permissions: [`${apiOrigin}/*`],
    // default_title is derived from the popup <title> by WXT; kept here for clarity only
    action: { default_title: 'Save to Brain2' },
  },
});
