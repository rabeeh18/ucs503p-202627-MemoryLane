// Encryption for what the extension keeps and backs up. AES-256-GCM with a
// fresh 12-byte IV per record.
//
// - Device key: from the server (GET /me) after sign-in, held in memory only.
//   Pages on disk are unreadable while signed out.
// - Recovery key: made in the browser, shown to the user once, never sent to
//   the server. Backups are encrypted with a key derived from it, so the server
//   stores backups it cannot open.

const enc = new TextEncoder();

export function base64urlToBytes(text) {
    const b64 = text.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(text.length / 4) * 4, "=");
    const bin = atob(b64);
    return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

export async function importAesKey(rawBytes) {
    return crypto.subtle.importKey("raw", rawBytes, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

/** iv (12 bytes) followed by ciphertext. */
export async function encrypt(key, bytes) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, bytes));
    const out = new Uint8Array(12 + ct.length);
    out.set(iv);
    out.set(ct, 12);
    return out;
}

export async function decrypt(key, data) {
    const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
    return new Uint8Array(await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, key, bytes.slice(12)));
}

// ---- recovery keys ---------------------------------------------------------------

// Crockford base32: no I, L, O or U, so a written-down key is hard to misread.
const ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/** 20 random bytes as 32 characters in groups of four: XXXX-XXXX-... (160 bits). */
export function newRecoveryKey() {
    const bytes = crypto.getRandomValues(new Uint8Array(20));
    let bits = "";
    for (const b of bytes) bits += b.toString(2).padStart(8, "0");
    let out = "";
    for (let i = 0; i < bits.length; i += 5) out += ALPHABET[parseInt(bits.slice(i, i + 5), 2)];
    return out.match(/.{4}/g).join("-");
}

/** The recovery key as typed: case, spaces and dashes don't matter; O/I/L read as 0/1/1. */
export function normalizeRecoveryKey(text) {
    const cleaned = String(text || "").toUpperCase().replace(/[\s-]/g, "").replace(/O/g, "0").replace(/[IL]/g, "1");
    if (!/^[0-9A-HJKMNP-TV-Z]{32}$/.test(cleaned)) return null;
    return cleaned.match(/.{4}/g).join("-");
}

/** AES key for backups: HKDF-SHA-256 of the recovery key, salted with the library id. */
export async function backupKey(recoveryKey, libraryId) {
    const normalized = normalizeRecoveryKey(recoveryKey);
    if (!normalized) throw new Error("That isn't a valid recovery key");
    const base = await crypto.subtle.importKey("raw", enc.encode(normalized), "HKDF", false, ["deriveKey"]);
    return crypto.subtle.deriveKey(
        { name: "HKDF", hash: "SHA-256", salt: enc.encode(`memorylane:${libraryId}`), info: enc.encode("memorylane-backup-v1") },
        base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"],
    );
}

// ---- compression -------------------------------------------------------------------

async function pipe(bytes, stream) {
    const out = new Blob([bytes]).stream().pipeThrough(stream);
    return new Uint8Array(await new Response(out).arrayBuffer());
}

export const gzip = (bytes) => pipe(bytes, new CompressionStream("gzip"));
export const gunzip = (bytes) => pipe(bytes, new DecompressionStream("gzip"));
