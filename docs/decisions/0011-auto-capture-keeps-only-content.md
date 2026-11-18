# 0011. Automatic capture keeps only pages that read like content

**Status:** Accepted · **Date:** November 2026 · Replaces "save everything except a blocklist"

## Context

Automatic capture used to save every page that finished loading, except those on a blocklist: social media, banks, login pages, search results, and later email. A Gmail inbox was still saved, by an extension that predated the email rule, and the server accepted it because it trusted the extension completely.

A blocklist can't keep up. Every private web app (Google Docs, Notion, Slack, a college portal, a cloud console, a shop's cart) has to be named one by one, and new ones slip through. Pages you open by mistake, redirects and login walls were also saved, filling the library with things nobody meant to keep.

## Decision

Flip the default. Automatic capture saves a page only when all of these hold:

1. **The address isn't private**: the old blocklist, plus private apps, local and intranet addresses, account areas of any site (dashboard, settings, inbox, cart...), and links carrying a secret (`?token=`, `?code=`...).
2. **The page was read**: 30 seconds in view, or scrolled at least halfway down a long page (`extension/engagement.js`).
3. **It reads like content**: at least 150 words of readable text, not mostly links, and no sign of a private screen (no visible password field, no compose box or editor, not mostly a form, not `noindex`); videos pass on their page type (`assessContent` in `extension/page_filter.js`).

The server applies the address rules and the `noindex` check again to every automatic save (`auto_capture_refusal` in `backend/page_filter.py`), so an outdated or buggy extension can't store these pages. And the popup lists **Auto-saved today**, with **Remove** and **Never this site** for anything that still gets through.

Manual saves (**Remember this page**) are never filtered: choosing to save a page is the user's call.

## Alternatives

| Option | Why not |
| --- | --- |
| Keep growing the blocklist | Whack-a-mole: every private app must be named, and the misses are the ones that hurt |
| Only allow sites the user approves | The safest, but auto-capture becomes manual work; can be added later as a stricter mode |
| A review queue: hold every capture until approved | Same problem: most people would never review it |
| Check password fields on the server too | Many article pages hide a login form in their HTML; only the extension can tell what's visible |

## Consequences

- **Easier:** most private and junk pages are skipped without being named, and outdated extensions are covered by the server.
- **Harder:** some pages worth keeping are now skipped: short posts (under 150 words), link-heavy index pages, and pages you glance at for under 30 seconds. **Remember this page** saves them.
- A private page that looks like an article (an internal wiki, say) can still be saved; **Never this site** handles it in one click.
- The address lists exist in two places (the extension and the server) and must be kept identical; both have tests.
