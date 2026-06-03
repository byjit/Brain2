import { defineWebExtConfig } from 'wxt';

// Local runner config (gitignored).
// See https://wxt.dev/runner.md
export default defineWebExtConfig({
  binaries: {
    chrome: '/Applications/chrome.app/Contents/MacOS/Google Chrome',
  },
});
