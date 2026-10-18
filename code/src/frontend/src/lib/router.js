// Tiny router: the current location as a store, plus navigate() and a `link`
// action for in-app anchors. Caddy serves index.html for unknown paths.
import { writable } from 'svelte/store';

function read() {
  return { path: window.location.pathname, query: new URLSearchParams(window.location.search) };
}

export const route = writable(read());

window.addEventListener('popstate', () => route.set(read()));

/** @param {string} url @param {{ replace?: boolean }} [opts] */
export function navigate(url, { replace = false } = {}) {
  const current = window.location.pathname + window.location.search;
  if (url !== current) {
    if (replace) window.history.replaceState({}, '', url);
    else window.history.pushState({}, '', url);
  }
  route.set(read());
  window.scrollTo(0, 0);
}

/** Svelte action: <a href="/library" use:link> navigates without a reload. */
export function link(node) {
  function onClick(event) {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const href = node.getAttribute('href');
    if (!href || !href.startsWith('/')) return;
    event.preventDefault();
    navigate(href);
  }
  node.addEventListener('click', onClick);
  return { destroy: () => node.removeEventListener('click', onClick) };
}
