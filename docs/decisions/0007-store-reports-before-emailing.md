# 0007. Store problem reports before emailing them

**Status:** Accepted · **Date:** November 2026

## Context

Users needed a way to report bugs from the website and the extension, and the maintainer wanted them by email. Email is unreliable to send from an app: the mail server can be down, credentials can expire, and the backend can restart mid-send. A lost report is worse than a late one, and a user shouldn't wait on an SMTP server to get a reply.

Reports also carry context (the page, the browser, the last error), which must not include search terms or anything the user didn't see.

## Decision

`POST /reports` writes the report to SQLite (`reports.db`) **before** replying `202`. A background thread then emails unsent reports through **Amazon SES** over SMTP. It wakes on each new report and sweeps every 60 seconds, and retries failures with backoff (1 minute, doubling, at most 6 hours, 12 attempts). The reply-to address comes from the server's record of the sign-in, never from the request. The page is kept as a path only, with any query string dropped.

## Alternatives

| Option | Why not |
| --- | --- |
| Send the email inside the request | The user waits on SMTP, and a failure loses the report |
| A hosted form or issue tracker | Users would need another account, and the app's context couldn't be attached safely |
| A message queue (SQS, Redis) | A whole extra service for a handful of reports a week |

## Consequences

- **Easier:** reports survive restarts and email outages, and the user gets an instant reply. Without SMTP settings, reports are still stored.
- **Harder:** the server holds reports, so **Delete all** removes them. (**Export my data** used to include them, until it was removed: [0010](0010-remove-export.md).) SES's sandbox only delivers to verified addresses, which is fine for emailing the maintainer.
- Rate-limited to 5 reports an hour per user, so the form can't be used to spam the maintainer.
