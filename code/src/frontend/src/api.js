/**
 * api.js — Backend communication for MemoryLane.
 *
 * Dev requests go to /api/* and Vite rewrites them to FastAPI routes on :8000.
 */

const SEARCH_TIMEOUT_MS = 10000;

function mapSearchResponse(payload) {
    const items = payload.results ?? payload.webpages ?? [];
  return {
    ...payload,
    webpages: items.map((item) => ({
      id: item.id ?? '',
      url: item.url ?? '',
      title: item.title ?? '',
      domain: item.domain ?? '',
      timestamp: item.timestamp ?? '',
    })),
  };
}

/**
 * Search saved webpages by semantic query.
 * @param {string} query
 * @param {AbortSignal} [signal]
 * @returns {Promise<{ webpages: Array<{ url: string, title: string, timestamp: string }> }>}
 */
export async function search(query, signal) {
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), SEARCH_TIMEOUT_MS);

  const onCallerAbort = () => timeoutController.abort();
  if (signal) signal.addEventListener('abort', onCallerAbort);

  try {
    const response = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, summarize: false }),
      signal: timeoutController.signal,
    });

    if (!response.ok) {
      const err = new Error('Search failed');
      err.status = response.status;
      throw err;
    }

    return mapSearchResponse(await response.json());
  } catch (err) {
    if (err.name === 'AbortError') {
      if (signal?.aborted) {
        const cancelled = new Error('Search cancelled');
        cancelled.name = 'CancelledError';
        throw cancelled;
      }
      const timeout = new Error('Search took too long. Please try again.');
      timeout.name = 'TimeoutError';
      throw timeout;
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
    if (signal) signal.removeEventListener('abort', onCallerAbort);
  }
}

/**
 * Save a webpage into memory (same Vite /api prefix as search).
 * @param {{ url: string, title: string, content: string }} payload
 */
export async function saveMemory(payload) {
  const response = await fetch('/api/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const err = new Error('Save failed');
    err.status = response.status;
    throw err;
  }

  return response.json();
}

/**
 * Summarize a single indexed webpage (on-demand).
 * @param {{ query: string, id: string }} payload
 * @returns {Promise<{ id: string, summary: string }>}
 */
export async function fetchSummary({ query, id }) {
  const response = await fetch('/api/summarize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, id }),
  });

  if (!response.ok) {
    const err = new Error('Summarization failed');
    err.status = response.status;
    throw err;
  }

  return response.json();
}
