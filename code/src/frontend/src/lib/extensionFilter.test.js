// Tests for the extension's auto-capture rules (code/src/extension/page_filter.js),
// run here because the extension has no test runner of its own.
import { describe, expect, it } from 'vitest';
import {
  assessContent, isAutoCaptureEligible, isEmailUrl, isPrivateUrl, sameDocument,
} from '../../../extension/page_filter.js';

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
      'https://developer.mozilla.org/en-US/docs/Web/API/Notification',
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

describe('private pages are never auto-captured', () => {
  const privatePages = [
    'https://docs.google.com/document/d/1abc/edit',
    'https://www.notion.so/My-notes-123',
    'https://app.slack.com/client/T1/C2',
    'https://web.whatsapp.com/',
    'https://www.icloud.com/photos/',
    'https://thapar.instructure.com/courses/12',
    'https://moodle.thapar.edu/course/view.php?id=4',
    'http://localhost:5173/library',
    'http://192.168.1.10/status',
    'https://shop.example.com/cart',
    'https://example.com/account/settings',
    'https://github.com/settings/profile',
    'https://example.com/invite?token=abc123',
    'https://chatgpt.com/c/123',
  ];
  for (const url of privatePages) {
    it(url, () => {
      expect(isPrivateUrl(url)).toBe(true);
      expect(isAutoCaptureEligible(url)).toBe(false);
    });
  }

  it('public pages still pass', () => {
    for (const url of [
      'https://en.wikipedia.org/wiki/Notion',
      'https://www.theverge.com/2026/11/1/some-article',
      'https://github.com/tokio-rs/axum',
      'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    ]) {
      expect(isPrivateUrl(url)).toBe(false);
      expect(isAutoCaptureEligible(url)).toBe(true);
    }
  });
});

describe('only pages that read like content are auto-captured', () => {
  const article = { words: 900, linkWords: 120, ogType: 'article', noindex: false, passwordFields: 0, editorArea: 0, inputs: 1 };

  it('keeps an article', () => {
    expect(assessContent(article)).toEqual({ ok: true });
  });

  it('keeps a video page with little text', () => {
    expect(assessContent({ ...article, words: 20, ogType: 'video.other' })).toEqual({ ok: true });
  });

  it.each([
    ['a password field', { passwordFields: 1 }],
    ['a compose box or editor', { editorArea: 400 * 300 }],
    ['a noindex page', { noindex: true }],
    ['too little text', { words: 80, ogType: '' }],
    ['a page of mostly links', { words: 400, linkWords: 300 }],
    ['a form', { words: 300, inputs: 12 }],
  ])('skips %s', (_label, change) => {
    expect(assessContent({ ...article, ...change }).ok).toBe(false);
  });
});
