// Letter shown in a page's tile: the first letter of the site's main domain
// name. Subdomains are skipped, so www, 2-letter language codes, m, mobile,
// docs, blog and app never decide the letter:
//   en.wikipedia.org -> W, docs.python.org -> P, m.youtube.com -> Y, bbc.co.uk -> B.
// Kept identical to frontend/src/lib/domain.js (tested there).

/** Second-level labels used under country TLDs (bbc.co.uk, abc.net.au). */
const SECOND_LEVEL = new Set(['co', 'com', 'net', 'org', 'gov', 'ac', 'edu', 'or', 'ne', 'go', 'gob', 'nic']);

/** Hostname from a URL or bare host ("https://En.Wikipedia.org/wiki/X" -> "en.wikipedia.org"). */
export function hostOf(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return '';
  try {
    return new URL(/^[a-z][a-z0-9+.-]*:\/\//.test(text) ? text : `http://${text}`).hostname.replace(/\.$/, '');
  } catch {
    return '';
  }
}

/** The label that names the site: "en.wikipedia.org" -> "wikipedia". */
export function mainName(value) {
  const host = hostOf(value);
  if (!host) return '';
  if (/^[\d.]+$/.test(host) || host.startsWith('[')) return host; // IP address
  let labels = host.split('.').filter(Boolean);
  const tld = labels[labels.length - 1];

  // Drop the public suffix: the TLD, plus "co"/"com"/... under a country TLD.
  if (labels.length > 1) labels = labels.slice(0, -1);
  if (labels.length > 1 && tld.length === 2 && SECOND_LEVEL.has(labels[labels.length - 1])) {
    labels = labels.slice(0, -1);
  }
  // What's left is [subdomains..., name]; the name is the main domain name.
  return labels[labels.length - 1] || '';
}

/** Upper-case first letter or digit of the site's main domain name, or "?". */
export function domainLetter(value) {
  const match = mainName(value).match(/[\p{L}\p{N}]/u);
  return match ? match[0].toUpperCase() : '?';
}
