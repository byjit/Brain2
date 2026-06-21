import { defineWebExtConfig } from 'wxt';

// Local runner config (gitignored).
// See https://wxt.dev/runner.md
export default defineWebExtConfig({
  binaries: {
    chrome: '/Applications/chrome.app/Contents/MacOS/Google Chrome',
    // Used by `pnpm dev:edge`. Adjust the path for your OS:
    //   Windows: C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe
    //   Linux:   /usr/bin/microsoft-edge
    edge: '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  },
});
