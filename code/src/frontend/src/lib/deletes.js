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

/**
 * @param {{
 *   remove: (pageId: string, opts?: { keepalive?: boolean }) => Promise<unknown>,
 *   delay?: number,
 *   setTimer?: typeof setTimeout,
 *   clearTimer?: typeof clearTimeout,
 * }} options
 */
export function createDeleteQueue({
  remove, delay = DELETE_DELAY_MS, setTimer = setTimeout, clearTimer = clearTimeout, now = () => Date.now(),
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

  /** Send every pending delete now (used when the page is being closed). */
  function flush(opts) {
    const ids = [...pending.keys()];
    for (const pageId of ids) {
      clearTimer(pending.get(pageId).timer);
      commit(pageId, opts);
    }
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
    hidden, toasts, committed, schedule, undo, flush, dismissToast, notify, reconcile, notInTotal,
    isPending: (id) => pending.has(id),
  };
}
