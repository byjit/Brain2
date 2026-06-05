// Picker overlay content script — injected programmatically on user gesture via
// browser.scripting.executeScript (activeTab + scripting permissions).
// registration: 'runtime' means WXT builds the script but does NOT auto-inject it;
// the background service worker injects it explicitly:
//   browser.scripting.executeScript({ target: { tabId }, files: ['content-scripts/picker.js'] })
// WXT automatically adds runtime-registered scripts to web_accessible_resources.
import { sendMessage, onMessage } from 'webext-bridge/content-script';
import { createWebextBridge, setDefaultBridge } from '@/services/messaging';
import { mountPicker } from './picker/picker-overlay';

export default defineContentScript({
  registration: 'runtime', // built, not auto-injected
  matches: [],             // injected programmatically from the background
  main(ctx) {
    setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));
    void mountPicker(ctx);
  },
});
