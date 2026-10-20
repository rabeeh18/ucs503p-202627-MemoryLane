// Backend calls. Every request carries the Cognito access token; a 401 refreshes
// the token once and retries, and a second 401 signs the user out locally,
// which takes them back to the sign-in screen.
import { expireSession, getAccessToken } from './auth.js';

const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '');
const TIMEOUT_MS = 15000;

export class ApiError extends Error {
  /** @param {string} message @param {number} status */
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function send(path, { method = 'GET', body, signal, token, keepalive = false }) {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), TIMEOUT_MS);
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
 * @param {{ method?: string, body?: unknown, signal?: AbortSignal, raw?: boolean, keepalive?: boolean }} [opts]
 */
async function request(path, opts = {}) {
  let token = await getAccessToken();
  if (!token) throw new ApiError('Signed out', 401);

  let response = await send(path, { ...opts, token });
  if (response.status === 401) {
    token = await getAccessToken({ force: true });
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
    throw new ApiError(typeof detail === 'string' && detail ? detail : 'Request failed', response.status);
  }
  if (opts.raw) return response;
  if (response.status === 204) return null;
  return response.json();
}

/** @returns {Promise<{ query: string, results: Array<{ rank: number, id: string, url: string, title: string, domain: string, timestamp: string, snippet: string | null }> }>} */
export function search(query, signal, { topic = null } = {}) {
  const body = { query, num_results: 10, summarize: false };
  if (topic) body.topic = topic;
  return request('/search', { method: 'POST', body, signal });
}

/** The library map: topics, page positions and links (or { status: 'too_few' }). */
export function getMap(signal) {
  return request('/map', { signal });
}

/** Topics and pages of the map close to `q` in meaning. */
export function mapSearch(q, signal) {
  return request(`/map/search?q=${encodeURIComponent(q)}`, { signal });
}

/** Up to `k` of the user's pages most similar to one page. */
export function getRelated(id, k = 5, signal) {
  return request(`/memory/${encodeURIComponent(id)}/related?k=${k}`, { signal });
}

/** @returns {Promise<{ total: number, pages: Array<{ id: string, url: string, title: string, domain: string, timestamp: string }> }>} */
export function listMemories(limit = 20, offset = 0, signal) {
  return request(`/memories?limit=${limit}&offset=${offset}`, { signal });
}

/** @returns {Promise<{ id: string, summary: string }>} */
export function fetchSummary({ query, id }) {
  return request('/summarize', { method: 'POST', body: { query, id } });
}

/** Download every saved page as a JSON file. */
export async function exportData() {
  const response = await request('/me/export', { raw: true });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `memorylane-export-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function deleteAllData() {
  return request('/me/data', { method: 'DELETE' });
}

/**
 * Delete one saved page. `keepalive` lets the request finish while the tab closes.
 * @param {string} id
 * @param {{ keepalive?: boolean }} [opts]
 */
export function deletePage(id, { keepalive = false } = {}) {
  return request(`/memory/${encodeURIComponent(id)}`, { method: 'DELETE', keepalive });
}
