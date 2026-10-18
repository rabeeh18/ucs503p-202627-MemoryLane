import { describe, expect, it } from 'vitest';
import { domainLetter as webLetter, mainName } from './domain.js';
import { domainLetter as extensionLetter } from '../../../extension/domain.js';

const cases = [
  ['en.wikipedia.org', 'W'],
  ['https://en.wikipedia.org/wiki/Sleep', 'W'],
  ['www.example.com', 'E'],
  ['example.com', 'E'],
  ['m.youtube.com', 'Y'],
  ['mobile.twitter.com', 'T'],
  ['docs.python.org', 'P'],
  ['blog.cloudflare.com', 'C'],
  ['app.netlify.com', 'N'],
  ['fr.m.wikipedia.org', 'W'],
  ['www.bbc.co.uk', 'B'],
  ['abc.net.au', 'A'],
  ['x.com', 'X'],
  ['github.io', 'G'],
  ['user.github.io', 'G'],
  ['localhost', 'L'],
  ['192.168.1.10', '1'],
  ['', '?'],
  ['not a url', '?'],
];

describe.each([
  ['web app', webLetter],
  ['extension', extensionLetter],
])('domain letter (%s)', (_name, domainLetter) => {
  it.each(cases)('%s -> %s', (input, letter) => {
    expect(domainLetter(input)).toBe(letter);
  });
});

describe('mainName', () => {
  it('returns the main domain label', () => {
    expect(mainName('en.wikipedia.org')).toBe('wikipedia');
    expect(mainName('news.bbc.co.uk')).toBe('bbc');
  });
});
