// The home page's headline and search-box example, different on each visit.
// The first visit gets the first of each; later visits a random one that isn't
// the one shown last time. Chosen once when the page opens, never while it's open.

export const HEADLINES = [
  'What are you trying to remember?',
  'What was that thing you read?',
  'Where did you see it?',
  "Describe it, and we'll find it.",
  'Half-remember something?',
  "Something you read, but can't find?",
  'What did you come back for?',
  'Remember the idea, not the title?',
  "What's stuck in your head today?",
];

export const EXAMPLES = [
  'that article about sleep and memory…',
  'the reddit thread about mechanical keyboards…',
  'a recipe with miso and butter…',
  'that video explaining black holes…',
  'the docs page about rate limiting…',
  'something I read last week about stoicism…',
];

const STORAGE_KEY = 'ml.greeting';

/**
 * Index into a list of `length` items: 0 when nothing was shown before,
 * otherwise a random one other than `last`.
 * @param {number} length
 * @param {number | null} last
 * @param {() => number} [random]
 */
export function pickIndex(length, last, random = Math.random) {
  if (length <= 1) return 0;
  if (last === null || !Number.isInteger(last) || last < 0 || last >= length) return 0;
  const step = 1 + Math.floor(random() * (length - 1)); // 1 .. length-1, so never `last`
  return (last + step) % length;
}

/**
 * Pick this visit's headline and example, and remember them for next time.
 * Works without storage (private windows): then every visit is a "first" one.
 * @param {Pick<Storage, 'getItem' | 'setItem'> | null} [storage]
 * @param {() => number} [random]
 */
export function nextGreeting(storage = safeLocalStorage(), random = Math.random) {
  let last = { h: null, p: null };
  try {
    const saved = JSON.parse(storage?.getItem(STORAGE_KEY) || 'null');
    if (saved && typeof saved === 'object') last = { h: saved.h ?? null, p: saved.p ?? null };
  } catch {
    /* unreadable: treat as a first visit */
  }
  const h = pickIndex(HEADLINES.length, last.h, random);
  const p = pickIndex(EXAMPLES.length, last.p, random);
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify({ h, p }));
  } catch {
    /* storage full or blocked: fine */
  }
  return { headline: HEADLINES[h], placeholder: EXAMPLES[p] };
}

function safeLocalStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
