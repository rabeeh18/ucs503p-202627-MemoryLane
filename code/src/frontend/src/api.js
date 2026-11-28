// Backend calls. Every request carries the Cognito access token; a 401 refreshes
// the token once and retries, and a second 401 signs the user out locally,
// which takes them back to the sign-in screen.
import { expireSession, getAccessToken, SessionUnavailableError } from './auth.js';
import { rememberError } from './report.js';
import { askExtension } from './lib/extension.js';

const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '');
const TIMEOUT_MS = 15000;
// Summaries wait longer: the backend gives Gemini up to 20 s (backend/summarizer.py).
export const SUMMARY_TIMEOUT_MS = 30000;

export class ApiError extends Error {
  /** @param {string} message @param {number} status */
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function send(path, { method = 'GET', body, signal, token, keepalive = false, timeoutMs = TIMEOUT_MS }) {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), timeoutMs);
  const onAbort = () => timeout.abort();
  signal?.addEventListener('abort', onAbort);
  try {
    return await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: timeout.signal,
      keepalive,
    });
  } catch (err) {
    if (signal?.aborted) {
      const cancelled = new Error('Cancelled');
      cancelled.name = 'CancelledError';
      throw cancelled;
    }
    if (err?.name === 'AbortError') throw new ApiError('The server took too long to respond.', 0);
    throw new ApiError('Network error. Check your connection and try again.', 0);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

/**
 * @param {string} path
 * @param {{ method?: string, body?: unknown, signal?: AbortSignal, raw?: boolean, keepalive?: boolean, timeoutMs?: number }} [opts]
 */
/** getAccessToken, with "Cognito unreachable" reported as a network error (status 0), not a sign-out. */
async function accessToken(opts) {
  try {
    return await getAccessToken(opts);
  } catch (err) {
    if (err instanceof SessionUnavailableError) throw new ApiError(err.message, 0);
    throw err;
  }
}

async function request(path, opts = {}) {
  let token = await accessToken();
  if (!token) throw new ApiError('Signed out', 401);

  let response = await send(path, { ...opts, token });
  if (response.status === 401) {
    token = await accessToken({ force: true });
    if (token) response = await send(path, { ...opts, token });
    if (!token || response.status === 401) {
      expireSession();
      throw new ApiError('Signed out', 401);
    }
  }

  if (!response.ok) {
    let detail = '';
    try {
      detail = (await response.json()).detail || '';
    } catch {
      /* not JSON */
    }
    const error = new ApiError(typeof detail === 'string' && detail ? detail : 'Request failed', response.status);
    rememberError(`${response.status} ${path.split('?')[0]}: ${error.message}`);
    throw error;
  }
  if (opts.raw) return response;
  if (response.status === 204) return null;
  return response.json();
}

/** @returns {Promise<{ query: string, results: Array<{ rank: number, id: string, url: string, title: string, domain: string, timestamp: string, snippet: string | null }> }>} */
/** The API's longest query; a longer one (a hand-edited ?q= link) is cut, not refused. */
const MAX_QUERY_CHARS = 500;

// ---- pages on this device and on the server ----------------------------------
//
// Pages may be kept by the browser extension on this device (extension/local.js)
// or on the server; each page lives whole in one place. Search, the library and
// deletes cover both. With no extension (another browser, a phone) only the
// server's pages are reachable.

let libraryPromise = null;

/** The library this site is signed in to (the extension answers only for it). */
function libraryId() {
  libraryPromise ||= request('/me').then((me) => me.library_id).catch((err) => {
    libraryPromise = null;
    throw err;
  });
  return libraryPromise;
}

/** Ask the extension about this library's device pages; null if it can't answer. */
async function device(type, fields = {}) {
  let library;
  try {
    library = await libraryId();
  } catch {
    return null;
  }
  const reply = await askExtension({ type, library_id: library, ...fields });
  return reply && reply.ok ? reply : null;
}

const RRF_K = 60;
// The server's results count once the device's are in, if they arrive this soon after.
const SERVER_GRACE_MS = 1500;

/** Reciprocal Rank Fusion of ranked result lists (the same k as search itself). */
export function mergeRanked(lists, limit) {
  const scores = new Map();
  const items = new Map();
  for (const list of lists) {
    list.forEach((item, i) => {
      scores.set(item.id, (scores.get(item.id) || 0) + 1 / (RRF_K + i + 1));
      if (!items.has(item.id)) items.set(item.id, item);
    });
  }
  return [...items.values()]
    .sort((a, b) => scores.get(b.id) - scores.get(a.id))
    .slice(0, limit)
    .map((item, i) => ({ ...item, rank: i + 1 }));
}

export async function search(query, signal) {
  const body = { query: query.slice(0, MAX_QUERY_CHARS), num_results: 10, summarize: false };
  const onDevice = device('SEARCH', { query: body.query, num_results: body.num_results });
  const onServer = request('/search', { method: 'POST', body, signal });
  const local = await onDevice;
  if (!local) return onServer;
  let remote = null;
  try {
    remote = await Promise.race([onServer, new Promise((resolve) => setTimeout(() => resolve(null), SERVER_GRACE_MS))]);
  } catch (err) {
    if (err?.name === 'CancelledError') throw err;
    remote = null; // the server is unreachable: this device's pages still answer
  }
  const lists = [local.results.map((r) => ({ ...r, location: 'device' }))];
  if (remote) lists.push(remote.results.map((r) => ({ ...r, location: 'server' })));
  return { query: body.query, results: mergeRanked(lists, body.num_results), partial: !remote };
}

/** @returns {Promise<{ total: number, pages: Array<{ id: string, url: string, title: string, domain: string, timestamp: string, location?: string }> }>} */
export async function listMemories(limit = 20, offset = 0, signal) {
  const [local, remote] = await Promise.all([
    device('LIST', { limit: offset + limit, offset: 0 }),
    request(`/memories?limit=${Math.min(100, offset + limit)}&offset=0`, { signal }),
  ]);
  if (!local || !local.total) return offset ? request(`/memories?limit=${limit}&offset=${offset}`, { signal }) : { ...remote, pages: remote.pages.slice(0, limit) };
  const pages = [
    ...local.pages.map((p) => ({ ...p, location: 'device' })),
    ...remote.pages.map((p) => ({ ...p, location: 'server' })),
  ].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp) || (a.id < b.id ? -1 : 1));
  return { total: local.total + remote.total, pages: pages.slice(offset, offset + limit) };
}

/** @returns {Promise<{ id: string, summary: string }>} */
export async function fetchSummary({ query, id }) {
  const local = await device('PAGE_TEXT', { id });
  if (local && local.page) {
    // A page on this device: its text goes to the server for this summary only.
    const body = { query, title: local.page.title, text: local.page.text.slice(0, 200000) };
    const result = await request('/summarize/text', { method: 'POST', body, timeoutMs: SUMMARY_TIMEOUT_MS });
    return { ...result, id };
  }
  return request('/summarize', { method: 'POST', body: { query, id }, timeoutMs: SUMMARY_TIMEOUT_MS });
}

export async function deleteAllData() {
  await device('DELETE_ALL');
  return request('/me/data', { method: 'DELETE' });
}

/**
 * Delete one saved page wherever it is. `keepalive` lets the server request
 * finish while the tab closes.
 * @param {string} id
 * @param {{ keepalive?: boolean }} [opts]
 */
export async function deletePage(id, { keepalive = false } = {}) {
  if (keepalive) {
    // The tab is closing: there is no time to ask first, so tell both places.
    device('DELETE', { id });
    return request(`/memory/${encodeURIComponent(id)}`, { method: 'DELETE', keepalive }).catch(() => null);
  }
  const local = await device('DELETE', { id });
  if (local && local.deleted) return null;
  return request(`/memory/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/**
 * Send a problem report (see report.js for what goes in `context`).
 * @param {{ message: string, source: 'web' | 'extension', context: { app_version?: string, page?: string, user_agent?: string, last_error?: string } }} report
 * @returns {Promise<{ status: string, id: number }>}
 */
export function sendReport(report) {
  return request('/reports', { method: 'POST', body: report });
}
