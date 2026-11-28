# 0016. Encrypt pages on the device, and back them up with a key only the user has

**Status:** Accepted · **Date:** November 2026

## Context

Pages kept on the device ([0012](0012-local-first-storage.md)) sit in the browser's IndexedDB. Anyone using the same browser profile could read them, including another person signing in to MemoryLane on a shared computer. And browser storage can be wiped, so device pages need a backup, which must not hand the pages back to the server.

## Decision

- **At rest:** every page is one record encrypted with AES-256-GCM using a **device key**. The server makes a random key per library and returns it after sign-in (`GET /me`); the extension keeps it in memory for the browser session and forgets it on sign-out. The server has the key but never the pages; the device has the pages but the key only while signed in. Each library has its own database, named by a hash.
- **Backups:** the extension makes a **recovery key** (160 random bits, shown once as eight groups of four characters). The backup is the device's pages, compressed and encrypted with a key derived from the recovery key (HKDF-SHA-256, salted with the library id). The server stores the blob (`PUT /backup`, up to 200 MB) and cannot open it. Restoring needs the recovery key; automatic daily backups keep the key in the browser only if the user turns them on.
- **Deleting all data** also deletes the backup and the device key, so the device copy can't be read again.

## Alternatives

| Option | Why not |
| --- | --- |
| Store pages unencrypted | Readable by anyone using the profile, and by another account signing in there |
| A passphrase to unlock the device copy | Another secret to remember on every browser start; can be added later |
| Back up with the device key | The server holds that key, so it could read the backup |
| Plain backups on the server | The same as storing the pages there |

## Consequences

- **Easier:** a signed-out profile can't read the pages, and backups can't be read by the server or anyone without the recovery key.
- **Harder:** a lost recovery key means the backup can't be restored, by design. Someone with full access to the signed-in browser, or malware, can still read pages, as with any local app.
