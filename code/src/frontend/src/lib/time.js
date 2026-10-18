const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/**
 * Relative time for a saved page: "Just now", "5 minutes ago", "2 hours ago",
 * "Yesterday", "3 days ago", "Last week", then a date ("12 Mar" or "12 Mar 2023").
 * @param {string} iso
 * @param {Date} [now]
 */
export function relativeTime(iso, now = new Date()) {
  const then = new Date(iso);
  if (!iso || Number.isNaN(then.getTime())) return '';

  const minutes = Math.floor((now.getTime() - then.getTime()) / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`;

  const days = Math.round((startOfDay(now) - startOfDay(then)) / 86400000);
  if (days <= 0) {
    const hours = Math.floor(minutes / 60);
    return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  }
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 14) return 'Last week';

  const date = `${then.getDate()} ${MONTHS[then.getMonth()]}`;
  return then.getFullYear() === now.getFullYear() ? date : `${date} ${then.getFullYear()}`;
}
