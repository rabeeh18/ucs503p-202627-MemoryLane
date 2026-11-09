import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { closeReport, openReport, rememberError, reportDialog, reportFromQuery } from '../report.js';

describe('reportFromQuery', () => {
  it('reads the extension link', () => {
    const q = new URLSearchParams('report=extension&v=2.1.2&err=Couldn%27t%20save');
    expect(reportFromQuery(q)).toEqual({ source: 'extension', appVersion: '2.1.2', lastError: "Couldn't save" });
  });

  it('ignores unknown sources', () => {
    expect(reportFromQuery(new URLSearchParams('report=admin'))).toBeNull();
    expect(reportFromQuery(new URLSearchParams('q=hello'))).toBeNull();
  });

  it('caps long values', () => {
    const q = new URLSearchParams({ report: 'extension', v: 'x'.repeat(100), err: 'e'.repeat(1000) });
    const setup = reportFromQuery(q);
    expect(setup?.appVersion).toHaveLength(40);
    expect(setup?.lastError).toHaveLength(500);
  });
});

describe('openReport', () => {
  it('fills in the website version and the last error shown', () => {
    rememberError('500 /search: Search failed');
    openReport();
    const setup = get(reportDialog);
    expect(setup?.source).toBe('web');
    expect(setup?.appVersion).toMatch(/^\d+\.\d+\.\d+$/);
    expect(setup?.lastError).toBe('500 /search: Search failed');
    closeReport();
    expect(get(reportDialog)).toBeNull();
  });

  it('does not remember sign-outs as errors', () => {
    rememberError('first real error');
    rememberError('Signed out');
    openReport();
    expect(get(reportDialog)?.lastError).toBe('first real error');
    closeReport();
  });
});
