import { describe, expect, it } from 'vitest';
import { safeUrl } from './url.js';

describe('safeUrl', () => {
  it('keeps http and https addresses', () => {
    expect(safeUrl('https://example.com/a?b=1#c')).toBe('https://example.com/a?b=1#c');
    expect(safeUrl('http://localhost:5173/')).toBe('http://localhost:5173/');
    expect(safeUrl('  HTTPS://Example.com/x ')).toBe('https://example.com/x');
  });

  it('drops anything that could run or open something else', () => {
    for (const url of ['javascript:alert(1)', ' JavaScript:alert(1)', 'data:text/html,hi',
      'file:///etc/passwd', 'chrome://settings', 'vbscript:x', 'not a url', '', null, undefined, 42]) {
      expect(safeUrl(url)).toBeUndefined();
    }
  });
});
