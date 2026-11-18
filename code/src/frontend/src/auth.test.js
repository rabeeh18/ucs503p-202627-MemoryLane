// Rapid reloads used to sign people out: a refresh cancelled by the reload was
// treated like a refused refresh token. Only Cognito saying no (400/401) ends it.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const SESSION = JSON.stringify({ refreshToken: 'old-refresh', email: 'someone@example.com' });

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    removeItem: (k) => map.delete(k),
  };
}

async function loadAuth(fetchImpl) {
  vi.resetModules();
  const storage = memoryStorage({ 'ml.session': SESSION });
  vi.stubGlobal('window', { location: { origin: 'http://localhost:5173' } });
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('fetch', vi.fn(fetchImpl));
  const auth = await import('./auth.js');
  return { auth, storage };
}

const reply = (status, body = {}) => async () => ({ ok: status < 400, status, json: async () => body });

describe('refreshing the session', () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it('keeps the session when the request is cancelled or fails (tab reloading)', async () => {
    const { auth, storage } = await loadAuth(async () => { throw new TypeError('Failed to fetch'); });
    await expect(auth.getAccessToken()).rejects.toBeInstanceOf(auth.SessionUnavailableError);
    expect(storage.getItem('ml.session')).toBe(SESSION);
  });

  it.each([429, 500, 503])('keeps the session when Cognito answers %i', async (status) => {
    const { auth, storage } = await loadAuth(reply(status));
    await expect(auth.getAccessToken()).rejects.toBeInstanceOf(auth.SessionUnavailableError);
    expect(storage.getItem('ml.session')).toBe(SESSION);
  });

  it.each([400, 401])('signs out when Cognito refuses the refresh token (%i)', async (status) => {
    const { auth, storage } = await loadAuth(reply(status, { error: 'invalid_grant' }));
    await expect(auth.getAccessToken()).resolves.toBeNull();
    expect(storage.getItem('ml.session')).toBeNull();
  });

  it('stores a rotated refresh token, and keeps the old one otherwise', async () => {
    let { auth, storage } = await loadAuth(reply(200, { access_token: 'a1', expires_in: 3600, refresh_token: 'new-refresh' }));
    await expect(auth.getAccessToken()).resolves.toBe('a1');
    expect(JSON.parse(storage.getItem('ml.session')).refreshToken).toBe('new-refresh');

    ({ auth, storage } = await loadAuth(reply(200, { access_token: 'a2', expires_in: 3600 })));
    await expect(auth.getAccessToken()).resolves.toBe('a2');
    expect(JSON.parse(storage.getItem('ml.session')).refreshToken).toBe('old-refresh');
  });
});
