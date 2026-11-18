// Tests for the docs site's meaning-based search (docs/assets/javascripts/semantic-core.js).
// The fixture was made from the real potion-base-8M model and its Hugging Face
// tokenizer (same tokens, and a tiny int8 table for the pieces used), so these
// check that the browser tokenises and embeds exactly like the docs build.
import { describe, expect, it } from 'vitest';
import fixture from './fixtures/docsSearch.json';
import {
  basicTokens, embed, fuse, loadModel, rankByMeaning, wordPieces,
} from '../../../../../docs/assets/javascripts/semantic-core.js';

const model = loadModel(
  fixture.vocab.join('\n'),
  Int8Array.from(fixture.table).buffer,
  Float32Array.from(fixture.scales).buffer,
  fixture.dims,
);

describe('tokenizer matches Hugging Face BERT WordPiece', () => {
  for (const { text, tokens } of fixture.cases) {
    it(JSON.stringify(text), () => {
      const ours = basicTokens(text).flatMap((word) => wordPieces(word, model.vocab));
      expect(ours).toEqual(tokens);
    });
  }
});

describe('embedding', () => {
  it('matches the docs build for the same text', () => {
    const v = embed(fixture.probe.text, model);
    fixture.probe.vector.forEach((x, d) => expect(v[d]).toBeCloseTo(x, 4));
  });

  it('is null when no word is known', () => {
    expect(embed('', model)).toBeNull();
  });
});

describe('ranking', () => {
  const section = (location, vector) => ({ location, title: location, page: '', snippet: '', vector: Float32Array.from(vector) });
  const sections = [section('a/', [1, 0]), section('b/', [0.6, 0.8]), section('c/', [0, 1])];

  it('orders sections by similarity', () => {
    expect(rankByMeaning(Float32Array.from([1, 0]), sections).map((s) => s.location)).toEqual(['a/', 'b/', 'c/']);
  });

  it('fuses meaning and keyword ranks, dropping weak meaning-only matches', () => {
    const byMeaning = rankByMeaning(Float32Array.from([1, 0]), sections); // a 1.0, b 0.6, c 0.0
    const fused = fuse(byMeaning, ['c/', 'b/'], { minSimilarity: 0.5 });
    // b is found both ways (2nd in each), so it wins. a (1st by meaning) and c (1st
    // by keyword) tie at 1/61 and keep the meaning list's order.
    expect(fused.map((s) => s.location)).toEqual(['b/', 'a/', 'c/']);
  });

  it('leaves out a meaning-only match below the threshold', () => {
    const byMeaning = rankByMeaning(Float32Array.from([1, 0]), sections);
    expect(fuse(byMeaning, [], { minSimilarity: 0.5 }).map((s) => s.location)).toEqual(['a/', 'b/']);
  });
});
