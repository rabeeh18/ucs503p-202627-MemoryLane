import { describe, expect, it, vi } from 'vitest';

vi.mock('../auth.js', () => ({ expireSession: vi.fn(), getAccessToken: vi.fn(), SessionUnavailableError: class extends Error {} }));
vi.mock('../report.js', () => ({ rememberError: vi.fn() }));

const { mergeRanked } = await import('../api.js');

const page = (id) => ({ id, title: id });

describe('merging results from this device and the server', () => {
  it('keeps one list unchanged when the other is empty', () => {
    const list = ['a', 'b', 'c'].map(page);
    expect(mergeRanked([list, []], 10).map((r) => r.id)).toEqual(['a', 'b', 'c']);
  });

  it('interleaves by rank and renumbers', () => {
    const merged = mergeRanked([['a', 'b'].map(page), ['x', 'y'].map(page)], 10);
    expect(merged.map((r) => r.id)).toEqual(['a', 'x', 'b', 'y']);
    expect(merged.map((r) => r.rank)).toEqual([1, 2, 3, 4]);
  });

  it('counts a page found in both lists once', () => {
    const merged = mergeRanked([['a', 'b'].map(page), ['b', 'c'].map(page)], 10);
    expect(merged.map((r) => r.id)).toEqual(['b', 'a', 'c']);
  });

  it('stops at the limit', () => {
    expect(mergeRanked([['a', 'b', 'c'].map(page)], 2)).toHaveLength(2);
  });
});
