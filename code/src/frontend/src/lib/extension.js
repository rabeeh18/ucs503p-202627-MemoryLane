// Whether the MemoryLane extension is installed in this browser. The extension
// injects a tiny content script on this site that sets
// <html data-memorylane-extension="installed">; it can run before or after the
// app starts, so the attribute is watched.
import { readable } from 'svelte/store';

export const EXTENSION_ZIP_URL = '/memorylane-extension.zip';

function isInstalled() {
  return document.documentElement.dataset.memorylaneExtension === 'installed';
}

export const extensionInstalled = readable(false, (set) => {
  if (typeof document === 'undefined') return undefined;
  set(isInstalled());
  const observer = new MutationObserver(() => set(isInstalled()));
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-memorylane-extension'],
  });
  return () => observer.disconnect();
});

// ---- pages kept on this device ----------------------------------------------------
//
// The extension can keep pages in this browser instead of on the server
// (extension/local.js). The website asks it about them by message; it answers
// only for the library this site is signed in to.

/** The installed extension's id (set by its site_marker.js), or null. */
export function extensionId() {
  if (typeof document === 'undefined') return null;
  return document.documentElement.dataset.memorylaneExtensionId || null;
}

const EXTENSION_TIMEOUT_MS = 20000;

/**
 * Send a message to the extension. Resolves its reply ({ok, ...}), or null when
 * there is no extension (no id, no chrome.runtime, no answer in time).
 */
export function askExtension(message, timeoutMs = EXTENSION_TIMEOUT_MS) {
  const id = extensionId();
  const runtime = typeof chrome !== 'undefined' ? chrome.runtime : undefined;
  if (!id || !runtime || !runtime.sendMessage) return Promise.resolve(null);
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs);
    try {
      runtime.sendMessage(id, message, (reply) => {
        clearTimeout(timer);
        void runtime.lastError; // no extension listening: null
        resolve(reply || null);
      });
    } catch {
      clearTimeout(timer);
      resolve(null);
    }
  });
}
