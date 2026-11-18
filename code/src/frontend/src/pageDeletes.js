// The app's single delete queue (see lib/deletes.js).
import { ApiError, deletePage } from './api.js';
import { createDeleteQueue } from './lib/deletes.js';

function tabStorage() {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

export const pageDeletes = createDeleteQueue({
  remove: (pageId, opts) => deletePage(pageId, opts).catch((err) => {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }),
  storage: tabStorage(),
});

/** Ids of pages hidden because they were deleted (or are about to be). */
export const hiddenPageIds = pageDeletes.hidden;
export const deleteToasts = pageDeletes.toasts;
/** Bumped after each delete the server confirmed. */
export const committedDeletes = pageDeletes.committed;

if (typeof window !== 'undefined') {
  // Closing or leaving the tab sends any deletes still waiting on their toast.
  window.addEventListener('pagehide', () => pageDeletes.flush({ keepalive: true }));
  // After a reload: keep hiding (and re-send) the deletes the old page flushed.
  pageDeletes.restore();
}
