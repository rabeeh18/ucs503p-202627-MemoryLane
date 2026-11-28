# Storage and Backups

Open the extension's **Settings** (the link at the bottom of the popup) to choose where your pages are kept.

## On this device, or on the server

| | On this device (default) | On the MemoryLane server |
| --- | --- | --- |
| Who can read the pages | Only this browser, while you're signed in; stored encrypted | The server (pages are kept out of logs and shown only to you) |
| Search from | This browser (memorylane.site, with the extension) | Any browser, including your phone |
| If the browser's data is wiped | Gone, unless you have a backup | Kept |

Search is the same in both: the same results, order and snippets. If some pages are on the device and some on the server, memorylane.site searches both and shows them together. In the library, pages on the device are marked **on this device**.

**Move pages here to the server** and **Bring server pages to this device** move everything at once. Each page moves exactly as stored.

## The size limit

**Size limit on this device** (default 100 MB, roughly 5,000 to 8,000 pages) and **Past the limit**:

- **Ask before moving pages**: the popup asks once; you can say **Move oldest pages** or **Keep all here**.
- **Move the oldest pages to the server**: done automatically from then on.
- **Keep everything here**: nothing moves.

The oldest pages move first, so the pages you saved recently stay on the device.

## Encrypted backups

**Back up now** the first time makes a **recovery key**, eight groups of four characters, shown once. Write it down or keep it in a password manager. The backup is locked with it: the server stores the backup but can't open it, and **without the key nobody can restore it**.

- **Back up automatically every day** keeps the recovery key in this browser so backups run on their own.
- **Restore from backup** asks for the recovery key and brings the pages back to this device (pages already here are kept).
- **Delete backup** removes it from the server.

## Signing out

Signing out removes the key that unlocks the device's pages, so they can't be read until you sign in again. **Delete all my data** (website account menu) deletes the pages on the server, the ones in this browser, the backup and the key.
