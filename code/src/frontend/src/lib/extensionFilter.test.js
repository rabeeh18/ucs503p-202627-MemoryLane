// Tests for the extension's auto-capture rules (code/src/extension/page_filter.js),
// run here because the extension has no test runner of its own.
import { describe, expect, it } from 'vitest';
import { isAutoCaptureEligible, isEmailUrl, sameDocument } from '../../../extension/page_filter.js';

describe('email pages are never auto-captured', () => {
  const email = [
    'https://mail.google.com/mail/u/0/#inbox',
    'https://mail.google.com/mail/u/0/#inbox/FMfcgzQXJWDsKmvb',
    'https://outlook.live.com/mail/0/inbox',
    'https://outlook.office.com/mail/inbox/id/AAQk',
    'https://mail.proton.me/u/0/inbox',
    'https://mail.yahoo.com/d/folders/1',
    'https://app.fastmail.com/mail/Inbox/',
    'https://www.icloud.com/mail/',
    'https://mail.example-university.edu/inbox',
    'https://webmail.example.com/?_task=mail',
    'https://intranet.example.com/owa/#path=/mail',
  ];
  for (const url of email) {
    it(url, () => {
      expect(isEmailUrl(url)).toBe(true);
      expect(isAutoCaptureEligible(url)).toBe(false);
    });
  }

  it('ordinary pages still pass', () => {
    for (const url of [
      'https://en.wikipedia.org/wiki/Email',
      'https://www.icloud.com/photos/',
      'https://blog.example.com/how-to-write-a-good-email',
      'https://docs.python.org/3/library/email.html',
    ]) {
      expect(isEmailUrl(url)).toBe(false);
      expect(isAutoCaptureEligible(url)).toBe(true);
    }
  });
});

describe('sameDocument', () => {
  it('ignores the fragment', () => {
    expect(sameDocument('https://a.com/x#top', 'https://a.com/x')).toBe(true);
  });

  it('notices a navigation', () => {
    expect(sameDocument('https://a.com/post/2', 'https://a.com/post/1')).toBe(false);
    expect(sameDocument('https://a.com/x?page=2', 'https://a.com/x?page=1')).toBe(false);
  });
});
