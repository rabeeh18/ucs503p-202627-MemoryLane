// The user's library map, shared by the Map page and topic search in Results.
import { get, writable } from 'svelte/store';
import { getMap } from './api.js';

/** { status: 'idle' | 'loading' | 'ok' | 'too_few' | 'error', data, error } */
export const mapState = writable({ status: 'idle', data: null, error: null });

let inflight = null;

/**
 * Load the map (reusing the last one unless `force`). Resolves to the map data,
 * or null when it couldn't be loaded.
 */
export function loadMap({ force = false } = {}) {
  const current = get(mapState);
  if (!force && (current.status === 'ok' || current.status === 'too_few')) return Promise.resolve(current.data);
  if (inflight) return inflight;
  mapState.update((s) => ({ ...s, status: s.data ? s.status : 'loading', error: null }));
  inflight = getMap()
    .then((data) => {
      mapState.set({ status: data.status === 'too_few' ? 'too_few' : 'ok', data, error: null });
      return data;
    })
    .catch((err) => {
      if (err?.status === 401) return null;
      mapState.update((s) => ({ ...s, status: s.data ? s.status : 'error', error: err }));
      throw err;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** A topic of the current map by id, or null. */
export function topicById(id) {
  return get(mapState).data?.topics?.find((t) => t.id === id) || null;
}

/** Forget the map (e.g. after "Delete all my data"). */
export function resetMap() {
  mapState.set({ status: 'idle', data: null, error: null });
}
