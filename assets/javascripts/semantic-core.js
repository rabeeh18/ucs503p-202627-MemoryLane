// Meaning-based docs search: the pure parts (no DOM), shared by the page script
// (semantic-search.js) and its tests (code/src/frontend/src/lib/docsSearch.test.js).
//
// The model is static (Model2Vec potion-base-8M): a query's vector is the average
// of its word pieces' vectors, so nothing but a tokenizer and a lookup table runs.
// The tokenizer reproduces Hugging Face's BertNormalizer + BertPreTokenizer +
// WordPiece (lowercase, accents stripped, "##" continuations), exactly as the
// docs build (hooks/semantic_search.py) used for the sections.

const MAX_WORD_CHARS = 100;
const RRF_K = 60;

function isControl(ch) {
  if (ch === '\t' || ch === '\n' || ch === '\r') return false;
  return /\p{Cc}|\p{Cf}/u.test(ch);
}

function isWhitespace(ch) {
  return ch === ' ' || ch === '\t' || ch === '\n' || ch === '\r' || /\p{Zs}/u.test(ch);
}

function isPunctuation(ch) {
  const cp = ch.codePointAt(0);
  if ((cp >= 33 && cp <= 47) || (cp >= 58 && cp <= 64) || (cp >= 91 && cp <= 96) || (cp >= 123 && cp <= 126)) {
    return true;
  }
  return /\p{P}/u.test(ch);
}

function isChinese(cp) {
  return (cp >= 0x4e00 && cp <= 0x9fff) || (cp >= 0x3400 && cp <= 0x4dbf) || (cp >= 0x20000 && cp <= 0x2a6df)
    || (cp >= 0x2a700 && cp <= 0x2b73f) || (cp >= 0x2b740 && cp <= 0x2b81f) || (cp >= 0x2b820 && cp <= 0x2ceaf)
    || (cp >= 0xf900 && cp <= 0xfaff) || (cp >= 0x2f800 && cp <= 0x2fa1f);
}

/** BertNormalizer (clean text, CJK spacing, lowercase, strip accents) + BertPreTokenizer. */
export function basicTokens(text) {
  let cleaned = '';
  for (const ch of String(text || '')) {
    const cp = ch.codePointAt(0);
    if (cp === 0 || cp === 0xfffd || isControl(ch)) continue;
    if (isWhitespace(ch)) cleaned += ' ';
    else if (isChinese(cp)) cleaned += ` ${ch} `;
    else cleaned += ch;
  }
  cleaned = cleaned.toLowerCase().normalize('NFD').replace(/\p{Mn}/gu, '');
  const words = [];
  let word = '';
  for (const ch of cleaned) {
    if (ch === ' ') {
      if (word) words.push(word);
      word = '';
    } else if (isPunctuation(ch)) {
      if (word) words.push(word);
      words.push(ch);
      word = '';
    } else {
      word += ch;
    }
  }
  if (word) words.push(word);
  return words;
}

/** WordPiece: greedy longest match, "##" for pieces after the first; [UNK] if a word can't be split. */
export function wordPieces(word, vocab) {
  const chars = Array.from(word);
  if (chars.length > MAX_WORD_CHARS) return ['[UNK]'];
  const pieces = [];
  let start = 0;
  while (start < chars.length) {
    let end = chars.length;
    let found = null;
    while (start < end) {
      const piece = (start > 0 ? '##' : '') + chars.slice(start, end).join('');
      if (vocab.has(piece)) {
        found = piece;
        break;
      }
      end -= 1;
    }
    if (found === null) return ['[UNK]'];
    pieces.push(found);
    start = end;
  }
  return pieces;
}

/** Token ids for `text` (no special tokens), as the docs build tokenised sections. */
export function tokenize(text, vocab) {
  const ids = [];
  for (const word of basicTokens(text)) {
    for (const piece of wordPieces(word, vocab)) ids.push(vocab.get(piece));
  }
  return ids;
}

/**
 * The model, from the files the docs build wrote.
 * @param {string} vocabText one word piece per line, in id order
 * @param {ArrayBuffer} table int8, one row of `dims` per word piece
 * @param {ArrayBuffer} scales float32, one per word piece
 */
export function loadModel(vocabText, table, scales, dims, maxTokens = 512) {
  const tokens = vocabText.split('\n');
  const vocab = new Map(tokens.map((t, i) => [t, i]));
  return { vocab, table: new Int8Array(table), scales: new Float32Array(scales), dims, maxTokens, unk: vocab.get('[UNK]') };
}

/** Unit-length query vector (mean of its word pieces), or null if no known word. */
export function embed(text, model) {
  const ids = tokenize(text, model.vocab).filter((id) => id !== model.unk && id !== undefined).slice(0, model.maxTokens);
  if (!ids.length) return null;
  const v = new Float32Array(model.dims);
  for (const id of ids) {
    const row = id * model.dims;
    const scale = model.scales[id];
    for (let d = 0; d < model.dims; d += 1) v[d] += model.table[row + d] * scale;
  }
  let norm = 0;
  for (let d = 0; d < model.dims; d += 1) norm += v[d] * v[d];
  norm = Math.sqrt(norm);
  if (!norm) return null;
  for (let d = 0; d < model.dims; d += 1) v[d] /= norm;
  return v;
}

/** Decode the sections file: each section's vector as unit-length floats. */
export function loadSections(list) {
  return list.map((s) => {
    const bytes = Uint8Array.from(atob(s.vector), (c) => c.charCodeAt(0));
    const ints = new Int8Array(bytes.buffer);
    const v = new Float32Array(ints.length);
    let norm = 0;
    for (let d = 0; d < ints.length; d += 1) {
      v[d] = ints[d] * s.scale;
      norm += v[d] * v[d];
    }
    norm = Math.sqrt(norm) || 1;
    for (let d = 0; d < v.length; d += 1) v[d] /= norm;
    return { location: s.location, title: s.title, page: s.page, snippet: s.snippet, vector: v };
  });
}

/** Sections by cosine similarity to the query vector, best first. */
export function rankByMeaning(queryVector, sections, limit = 20) {
  const scored = sections.map((s) => {
    let dot = 0;
    for (let d = 0; d < queryVector.length; d += 1) dot += queryVector[d] * s.vector[d];
    return { ...s, similarity: dot };
  });
  return scored.sort((a, b) => b.similarity - a.similarity).slice(0, limit);
}

/**
 * Reciprocal Rank Fusion of meaning ranks and keyword ranks (locations from the
 * built-in search), as MemoryLane fuses BM25 and vector search: 1 / (60 + rank).
 * Meaning-only results need `minSimilarity`, so weak matches don't pad the list.
 */
export function fuse(byMeaning, keywordLocations, { limit = 5, minSimilarity = 0 } = {}) {
  const scores = new Map();
  const info = new Map();
  byMeaning.forEach((s, i) => {
    info.set(s.location, s);
    if (s.similarity >= minSimilarity) scores.set(s.location, 1 / (RRF_K + i + 1));
  });
  keywordLocations.forEach((location, i) => {
    scores.set(location, (scores.get(location) || 0) + 1 / (RRF_K + i + 1));
  });
  return [...scores.entries()]
    .filter(([location]) => info.has(location))
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([location, score]) => ({ ...info.get(location), score }));
}
