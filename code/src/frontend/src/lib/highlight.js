// Splits a snippet into plain-text parts so query terms can be emphasised
// without {@html}. Matching is case-insensitive prefix matching ("learn"
// matches "learning") on terms of 3+ characters that aren't stopwords.

const STOPWORDS = new Set([
  'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'any', 'can', 'had',
  'her', 'was', 'one', 'our', 'out', 'has', 'have', 'his', 'how', 'its', 'who',
  'did', 'get', 'him', 'she', 'too', 'use', 'that', 'this', 'with', 'from',
  'they', 'them', 'then', 'than', 'what', 'when', 'where', 'which', 'about',
  'into', 'your', 'some', 'there', 'their', 'were', 'been', 'does', 'also',
  'why', 'way', 'like', 'just',
]);

const WORD = /[\p{L}\p{N}]+/gu;

/** @param {string} query */
export function queryTerms(query) {
  const terms = new Set();
  for (const [word] of (query || '').toLowerCase().matchAll(WORD)) {
    if (word.length >= 3 && !STOPWORDS.has(word)) terms.add(word);
  }
  return [...terms];
}

/**
 * @param {string} text
 * @param {string} query
 * @returns {{ text: string, match: boolean }[]}
 */
export function highlight(text, query) {
  if (!text) return [];
  const terms = queryTerms(query);
  if (!terms.length) return [{ text, match: false }];

  const parts = [];
  let last = 0;
  for (const m of text.matchAll(WORD)) {
    const word = m[0].toLowerCase();
    if (!terms.some((t) => word.startsWith(t))) continue;
    if (m.index > last) parts.push({ text: text.slice(last, m.index), match: false });
    parts.push({ text: m[0], match: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), match: false });
  return parts;
}
