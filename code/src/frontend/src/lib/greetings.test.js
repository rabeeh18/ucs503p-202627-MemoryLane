import { describe, expect, it } from 'vitest';
import { EXAMPLES, HEADLINES, nextGreeting, pickIndex } from './greetings.js';

function memoryStorage() {
  const items = new Map();
  return { getItem: (k) => items.get(k) ?? null, setItem: (k, v) => items.set(k, String(v)) };
}

describe('pickIndex', () => {
  it('starts with the first item', () => {
    expect(pickIndex(9, null)).toBe(0);
  });

  it('never repeats the last one', () => {
    for (let last = 0; last < 9; last++) {
      for (const r of [0, 0.25, 0.5, 0.999]) expect(pickIndex(9, last, () => r)).not.toBe(last);
    }
  });

  it('reaches every other item', () => {
    const seen = new Set();
    for (let i = 0; i < 8; i++) seen.add(pickIndex(9, 0, () => i / 8));
    expect(seen).toEqual(new Set([1, 2, 3, 4, 5, 6, 7, 8]));
  });

  it('treats a bad stored value as a first visit', () => {
    expect(pickIndex(9, 42)).toBe(0);
    expect(pickIndex(9, -1)).toBe(0);
  });
});

describe('nextGreeting', () => {
  it('shows the original pair first, then changes on the next visit', () => {
    const storage = memoryStorage();
    expect(nextGreeting(storage, () => 0.5)).toEqual({ headline: HEADLINES[0], placeholder: EXAMPLES[0] });
    const second = nextGreeting(storage, () => 0.5);
    expect(second.headline).not.toBe(HEADLINES[0]);
    expect(second.placeholder).not.toBe(EXAMPLES[0]);
    const third = nextGreeting(storage, () => 0.5);
    expect(third.headline).not.toBe(second.headline);
  });

  it('works without storage or with broken storage', () => {
    expect(nextGreeting(null).headline).toBe(HEADLINES[0]);
    const broken = { getItem: () => '{not json', setItem: () => { throw new Error('full'); } };
    expect(nextGreeting(broken).headline).toBe(HEADLINES[0]);
  });

  it('keeps every line short enough to sit on one or two lines', () => {
    for (const line of [...HEADLINES, ...EXAMPLES]) expect(line.length).toBeLessThanOrEqual(46);
  });
});
