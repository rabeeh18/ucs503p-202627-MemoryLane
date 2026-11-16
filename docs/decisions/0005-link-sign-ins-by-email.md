# 0005. Link Google and email sign-ins by verified email

**Status:** Accepted · **Date:** November 2026

## Context

Every page belongs to a library identified by the Cognito user id (`sub`). But Cognito gives a Google sign-in and an email + password sign-in **different** `sub`s, even for the same address. Someone who signed up with email and later clicked "Continue with Google" found an empty library and thought their pages were lost.

Linking by email is only safe if the email is proven. Otherwise anyone could sign up with someone else's address and reach their pages.

## Decision

`backend/accounts.py` maps each `sub` to a library, stored in SQLite (`accounts.db`):

- The first time a `sub` is seen, the backend asks Cognito's `/oauth2/userInfo` for its email, **using that user's own access token**, so the browser can't supply a fake address.
- The email links only if it's verified (`email_verified` is `"true"`, or the sign-in came through Google). The first verified sign-in for an address gives the library its id.
- An unverified sign-in keeps a library of its own, and is checked again after 5 minutes.
- If Cognito can't be reached for a new `sub`, the request fails with `503`, so pages never land in the wrong library.

## Alternatives

| Option | Why not |
| --- | --- |
| Cognito's own account linking (a pre-sign-up Lambda) | More AWS setup, and it only helps new sign-ups, not the accounts that already existed |
| Tell users to always use the same sign-in method | Easy to get wrong, and the failure looks like data loss |
| Use the email itself as the library id | Changing an email would orphan a library, and unverified emails would be trusted |

## Consequences

- **Easier:** both sign-in methods open the same library, with no change to Solr data: the library id is still the first `sub`.
- **Harder:** the server now stores email addresses, which the [privacy page](../privacy.md) states, and **Delete all** removes them. `accounts.db` has to be backed up with Solr's data.
- A first request for a new sign-in costs one call to Cognito; known sign-ins are answered from SQLite.
