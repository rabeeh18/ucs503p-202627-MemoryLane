// Saved pages are opened from links. Only http(s) addresses are linked, so a
// page stored with a `javascript:` (or other) URL can never run as a link.

/**
 * The URL if it's an http(s) address, else undefined (an <a> then has no href).
 * @param {string | null | undefined} url
 * @returns {string | undefined}
 */
export function safeUrl(url) {
  if (typeof url !== 'string') return undefined;
  try {
    const parsed = new URL(url.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}

/** Open a saved page in a new tab, if its URL is safe to open. */
export function openPage(url) {
  const href = safeUrl(url);
  if (href) window.open(href, '_blank', 'noopener');
}
