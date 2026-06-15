import React from 'react';
import ReactDOM from 'react-dom/client';
import { sendMessage, onMessage } from 'webext-bridge/options';
import { createWebextBridge, setDefaultBridge } from '@/services/messaging';
import App from './App.tsx';
import '@/assets/tailwind.css';

// Install the options-context messaging bridge ONCE, before any render, so every
// `defineMessage` call made from components resolves through it.
setDefaultBridge(createWebextBridge({ sendMessage, onMessage }));

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
