// "Report a problem": the dialog's open state, and the details sent with a report.
// Every detail is shown in the dialog before sending; nothing else goes out.
import { writable } from 'svelte/store';
import { version as webVersion } from '../package.json';

/** @typedef {{ source: 'web' | 'extension', appVersion: string, lastError: string }} ReportSetup */

/** null when closed. */
export const reportDialog = writable(/** @type {ReportSetup | null} */ (null));

/** The last error message the website showed, so a report can include it. */
let lastError = '';

/** @param {string} message */
export function rememberError(message) {
  if (message && message !== 'Signed out' && message !== 'Cancelled') lastError = message.slice(0, 500);
}

/**
 * Open the dialog. Reports from the website describe the website; the extension
 * opens the website with ?report=extension and its own version and error.
 * @param {Partial<ReportSetup>} [setup]
 */
export function openReport(setup = {}) {
  reportDialog.set({
    source: setup.source || 'web',
    appVersion: setup.appVersion || webVersion,
    lastError: setup.lastError ?? lastError,
  });
}

export function closeReport() {
  reportDialog.set(null);
}

/** The current path only: never the query string (it holds search terms). */
export function currentPage() {
  return window.location.pathname.slice(0, 200);
}

/**
 * Read and remove ?report=extension&v=…&err=… (from the extension's "Report a
 * problem" link). Returns the setup to open the dialog with, or null.
 * @param {URLSearchParams} query
 */
export function reportFromQuery(query) {
  const source = query.get('report');
  if (source !== 'extension' && source !== 'web') return null;
  return {
    source,
    appVersion: (query.get('v') || '').slice(0, 40),
    lastError: (query.get('err') || '').slice(0, 500),
  };
}
