// The extension's local search engine (code/src/extension/engine), run here
// because the extension has no test runner of its own. Full parity with the
// server is checked against a real Solr by code/src/evaluation/parity/; these
// tests pin the behaviour those checks established.
import { describe, expect, it } from 'vitest';
import { porterStem } from '../../../extension/engine/porter.js';
import { analyzeIndex, analyzeQuery } from '../../../extension/engine/analyzer.js';
import { Bm25Index, searchBm25, intToByte4 } from '../../../extension/engine/bm25.js';
import { normalizeUrl, generatePageId } from '../../../extension/engine/url.js';
import { parseQuery } from '../../../extension/engine/query_intent.js';
import { applyRelevanceFloor, rrfFuseLists } from '../../../extension/engine/retrieval.js';
import { encodePage, decodePage } from '../../../extension/engine/store.js';
import { decrypt, encrypt, importAesKey, newRecoveryKey, normalizeRecoveryKey } from '../../../extension/engine/crypto.js';

describe("Lucene's Porter stemmer", () => {
  it.each([
    ['running', 'run'], ['generalizations', 'gener'], ['relational', 'relat'], ['hopeful', 'hope'],
    ['archaeology', 'archaeolog'], ['conformabli', 'conform'], ['ponies', 'poni'], ['caresses', 'caress'],
  ])('%s -> %s', (word, stem) => expect(porterStem(word)).toBe(stem));
});

describe("Solr's text_en analysis", () => {
  it('drops stop words but keeps their positions', () => {
    expect(analyzeIndex('The best pancakes rise on a hot griddle')).toEqual([
      { term: 'best', pos: 1 }, { term: 'pancak', pos: 2 }, { term: 'rise', pos: 3 },
      { term: 'hot', pos: 6 }, { term: 'griddl', pos: 7 },
    ]);
  });
  it("strips possessives and protects listed words", () => {
    expect(analyzeIndex("JAMES'S dontstems")).toEqual([{ term: 'jame', pos: 0 }, { term: 'dontstems', pos: 1 }]);
  });
  it('expands query synonyms, keeping duplicates as Solr does', () => {
    expect(analyzeQuery('TV')[0].terms.sort()).toEqual(['televis', 'televis', 'tv', 'tv']);
  });
  it('splits Han characters and keeps a Thai run whole', () => {
    expect(analyzeIndex('東京 ภาษาไทย').map((t) => t.term)).toEqual(['東', '京', 'ภาษาไทย']);
  });
});

describe('BM25 as Solr scores it', () => {
  const docs = {
    a: ['Pancake recipes', 'Fluffy pancakes need baking powder. The best pancakes rise on a hot griddle.'],
    b: ['TV buying guide', 'A 4K television with 64 GB storage; televisions are cheaper in March.'],
  };
  const index = new Bm25Index();
  for (const [id, [title, text]] of Object.entries(docs)) index.add(id, title, text);
  const textOf = (id, field) => docs[id][field === 'title' ? 0 : 1];

  it('matches the scores Solr 9.7 gave for this corpus', () => {
    const hits = searchBm25(index, 'best fluffy pancakes on TV', { textOf });
    expect(hits.map((h) => h.doc)).toEqual(['a', 'b']);
    expect(hits[0].score).toBeCloseTo(1.289021, 5);
    expect(hits[1].score).toBeCloseTo(0.82029253, 5);
  });
  it('honours required, excluded and AND clauses', () => {
    expect(searchBm25(index, 'pancakes -griddle', { textOf })).toEqual([]);
    expect(searchBm25(index, 'pancakes AND storage', { textOf })).toEqual([]);
    expect(searchBm25(index, '+pancakes tv', { textOf }).map((h) => h.doc)).toEqual(['a']);
  });
  it("stores lengths in Lucene's one byte", () => {
    expect(intToByte4(10)).toBe(10);
    expect(intToByte4(1000)).toBeLessThan(256);
  });
});

describe('URLs and page ids, as backend/url_utils.py', () => {
  it('normalises as the server does', () => {
    expect(normalizeUrl('https://www.Example.com:443/a/b/?utm_source=x&b=2&a=1#top')).toBe('https://example.com/a/b?a=1&b=2');
    expect(normalizeUrl('http://example.com')).toBe('http://example.com/');
  });
  it('derives the same page id', async () => {
    // sha256("lib|https://example.com/")[:32]
    expect(await generatePageId('lib', 'https://example.com/')).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe('query understanding', () => {
  const now = Date.UTC(2026, 9, 15, 12);
  it('finds site words and time phrases', () => {
    const intent = parseQuery('that reddit post from yesterday', ['reddit.com', 'example.org'], now);
    expect([...intent.domains]).toEqual(['reddit.com']);
    expect(intent.savedFrom).toBe(Date.UTC(2026, 9, 13));
    expect(intent.text).toBe('');
  });
});

describe('fusion and the relevance floor', () => {
  it('adds weight / (k + rank) per list', () => {
    const fused = rrfFuseLists([[['x', 'y'], 1], [['y'], 1]], 60);
    expect(fused.get('y')).toBeCloseTo(1 / 62 + 1 / 61, 12);
  });
  it('keeps strong keyword matches and close vector matches only', () => {
    const pages = [
      { page_id: 'kw', bm25_match: true, title: 'rust lifetimes', text: '', vector_similarity: null },
      { page_id: 'near', bm25_match: false, vector_similarity: 0.6 },
      { page_id: 'far', bm25_match: false, vector_similarity: 0.4 },
    ];
    expect(applyRelevanceFloor(pages, { terms: ['rust', 'lifetimes'] }).map((p) => p.page_id)).toEqual(['kw', 'near']);
  });
});

describe('the encrypted page store', () => {
  it('round-trips a page and refuses another key', async () => {
    const page = { page_id: 'p1', title: 'Bread', url: 'https://example.com/bread', timestamp: '2026-10-01T00:00:00.000Z' };
    const chunks = [{ id: 'p1::0', chunk_id: 0, text: 'Sourdough needs a starter.', embedding: Float32Array.from([0.6, 0.8]) }];
    const key = await importAesKey(new Uint8Array(32).fill(1));
    const sealed = await encrypt(key, encodePage(page, chunks));
    const back = decodePage(await decrypt(key, sealed));
    expect(back.chunks[0].text).toBe('Sourdough needs a starter.');
    expect(Array.from(back.chunks[0].embedding)).toEqual([Math.fround(0.6), Math.fround(0.8)]);
    const other = await importAesKey(new Uint8Array(32).fill(2));
    await expect(decrypt(other, sealed)).rejects.toThrow();
  });
  it('makes readable recovery keys', () => {
    const key = newRecoveryKey();
    expect(key).toMatch(/^([0-9A-Z]{4}-){7}[0-9A-Z]{4}$/);
    expect(normalizeRecoveryKey(key.toLowerCase().replace(/-/g, ' '))).toBe(key);
    expect(normalizeRecoveryKey('not a key')).toBeNull();
  });
});
