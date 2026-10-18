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
