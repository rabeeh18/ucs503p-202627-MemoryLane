// Delayed page deletion with undo.
//
// Deleting hides the page everywhere at once and shows "Page deleted · Undo"
// for 6 seconds. The DELETE request is sent only when that toast expires; Undo
// cancels it. If the request fails the page comes back and an error toast says
// so. Pending deletes are sent straight away if the tab is closed.
//
// A deleted page stays hidden until a list fetched *after* the delete shows it
// again (reconcile): that only happens when the same URL was saved again, since
// page ids come from the URL, so the re-saved page then appears without a reload.
import { writable } from 'svelte/store';

export const DELETE_DELAY_MS = 6000;
export const ERROR_TOAST_MS = 6000;
/** How long after a tab-closing flush a reload still re-sends those deletes. */
export const RESTORE_MS = 30000;
const FLUSHED_KEY = 'ml.flushedDeletes';

/**
 * @param {{
 *   remove: (pageId: string, opts?: { keepalive?: boolean }) => Promise<unknown>,
 *   delay?: number,
 *   setTimer?: typeof setTimeout,
 *   clearTimer?: typeof clearTimeout,
 *   now?: () => number,
 *   storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null,
 * }} options
 */
export function createDeleteQueue({
  remove, delay = DELETE_DELAY_MS, setTimer = setTimeout, clearTimer = clearTimeout, now = () => Date.now(),
  storage = null,
}) {
  /** Ids hidden from every list (pending or deleted). */
  const hidden = writable(new Set());
  /** @type {import('svelte/store').Writable<Array<{ id: number, kind: 'undo' | 'error', message: string, pageId?: string }>>} */
  const toasts = writable([]);
  /** Bumped after every delete the server confirmed (e.g. to refetch a list). */
  const committed = writable(0);
  /** pageId -> { timer, toastId } */
  const pending = new Map();
  /** pageId -> when the server confirmed its delete */
  const committedAt = new Map();
  let nextToastId = 1;

  const setHidden = (pageId, isHidden) =>
    hidden.update((ids) => {
      const next = new Set(ids);
      if (isHidden) next.add(pageId);
      else next.delete(pageId);
      return next;
    });

  function addToast(toast) {
    const id = nextToastId++;
    toasts.update((list) => [...list, { ...toast, id }]);
    return id;
  }

  function dismissToast(toastId) {
    toasts.update((list) => list.filter((t) => t.id !== toastId));
  }

  async function commit(pageId, opts) {
    const entry = pending.get(pageId);
    if (!entry) return;
    pending.delete(pageId);
    dismissToast(entry.toastId);
    try {
      await remove(pageId, opts);
      committedAt.set(pageId, now());
      committed.update((n) => n + 1);
    } catch {
      setHidden(pageId, false);
      const errorId = addToast({ kind: 'error', message: "Couldn't delete the page. It's back in your library." });
      setTimer(() => dismissToast(errorId), ERROR_TOAST_MS);
    }
  }

  /** Hide the page now and delete it when the undo window closes. */
  function schedule(pageId) {
    if (!pageId || pending.has(pageId)) return;
    setHidden(pageId, true);
    const toastId = addToast({ kind: 'undo', message: 'Page deleted', pageId });
    const timer = setTimer(() => commit(pageId), delay);
    pending.set(pageId, { timer, toastId });
  }

  /** Cancel a pending delete and show the page again. */
  function undo(pageId) {
    const entry = pending.get(pageId);
    if (!entry) return;
    clearTimer(entry.timer);
    pending.delete(pageId);
    dismissToast(entry.toastId);
    setHidden(pageId, false);
  }

  /**
   * Send every pending delete now (used when the page is being closed). The ids
   * are also written to `storage`, so if this is a reload the new page keeps
   * them hidden and sends them again (see restore): a delete sent while the
   * page unloads may not have reached the server when the list is fetched.
   */
  function flush(opts) {
    const ids = [...pending.keys()];
    if (ids.length && storage) {
      const at = now();
      const kept = readFlushed().filter((entry) => !ids.includes(entry.id));
      writeFlushed([...kept, ...ids.map((id) => ({ id, at }))]);
    }
    for (const pageId of ids) {
      clearTimer(pending.get(pageId).timer);
      commit(pageId, opts);
    }
    return ids.length;
  }

  function readFlushed() {
    try {
      const list = JSON.parse(storage.getItem(FLUSHED_KEY) || '[]');
      return Array.isArray(list) ? list.filter((e) => e && typeof e.id === 'string' && typeof e.at === 'number') : [];
    } catch {
      return [];
    }
  }

  function writeFlushed(list) {
    try {
      if (list.length) storage.setItem(FLUSHED_KEY, JSON.stringify(list));
      else storage.removeItem(FLUSHED_KEY);
    } catch {
      /* storage unavailable: the reload just won't know */
    }
  }

  /**
   * On load: deletes the previous page sent while unloading (in the last
   * RESTORE_MS) stay hidden and are sent again. Deleting is idempotent, and a
   * 404 counts as done, so a delete that already arrived costs one request.
   */
  async function restore() {
    if (!storage) return 0;
    const fresh = readFlushed().filter((entry) => now() - entry.at < RESTORE_MS);
    writeFlushed([]);
    const ids = [...new Set(fresh.map((entry) => entry.id))];
    for (const id of ids) setHidden(id, true);
    await Promise.all(ids.map(async (id) => {
      try {
        await remove(id);
        committedAt.set(id, now());
        committed.update((n) => n + 1);
      } catch {
        setHidden(id, false);
      }
    }));
    return ids.length;
  }

  /**
   * A list was fetched from the server, starting at `fetchedAt`, and holds `ids`.
   * A page deleted before that fetch but listed again was saved again: show it.
   */
  function reconcile(ids, fetchedAt) {
    const back = [...ids].filter((id) => committedAt.has(id) && committedAt.get(id) < fetchedAt);
    if (!back.length) return;
    for (const id of back) committedAt.delete(id);
    hidden.update((current) => {
      const next = new Set(current);
      for (const id of back) next.delete(id);
      return next;
    });
  }

  /**
   * Is this hidden page's delete missing from a total fetched at `fetchedAt`?
   * True while it's pending, or if the server confirmed it after that fetch began.
   */
  function notInTotal(id, fetchedAt) {
    if (pending.has(id)) return true;
    const at = committedAt.get(id);
    return at !== undefined && at >= fetchedAt;
  }

  /** Show a short error toast that dismisses itself. */
  function notify(message) {
    const id = addToast({ kind: 'error', message });
    setTimer(() => dismissToast(id), ERROR_TOAST_MS);
    return id;
  }

  return {
    hidden, toasts, committed, schedule, undo, flush, restore, dismissToast, notify, reconcile, notInTotal,
    isPending: (id) => pending.has(id),
  };
}
