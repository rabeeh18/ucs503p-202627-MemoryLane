// Where local pages live on disk: one encrypted record per page in IndexedDB,
// in a database per account. A record holds everything search needs (text,
// keyword statistics, vectors), so opening the store never re-analyses text.
// Only the page id (a hash) is stored in the clear.
import { decrypt, encrypt } from "./crypto.js";
import { fieldStats } from "./bm25.js";

const RECORD_VERSION = 1;

// ---- page record codec ------------------------------------------------------------

function packStats(stats) {
    return { length: stats.length, terms: [...stats.terms.keys()], freqs: [...stats.terms.values()] };
}

function unpackStats(packed) {
    return { length: packed.length, terms: new Map(packed.terms.map((t, i) => [t, packed.freqs[i]])) };
}

/**
 * A page as bytes: 4-byte header length, JSON header, padding to 4 bytes, then
 * every chunk's vector as float32. `page` is the chunk-0 metadata; `chunks`
 * carry {id, chunk_id, text, embedding}.
 */
export function encodePage(page, chunks) {
    const titleStats = fieldStats(page.title);
    const header = {
        v: RECORD_VERSION,
        page,
        title: packStats(titleStats),
        chunks: chunks.map((c) => ({ id: c.id, chunk_id: c.chunk_id, text: c.text, stats: packStats(fieldStats(c.text)) })),
        dim: chunks[0].embedding.length,
    };
    const json = new TextEncoder().encode(JSON.stringify(header));
    const pad = (4 - ((4 + json.length) % 4)) % 4;
    const vectors = new Float32Array(chunks.length * header.dim);
    chunks.forEach((c, i) => vectors.set(c.embedding, i * header.dim));
    const out = new Uint8Array(4 + json.length + pad + vectors.byteLength);
    new DataView(out.buffer).setUint32(0, json.length, true);
    out.set(json, 4);
    out.set(new Uint8Array(vectors.buffer), 4 + json.length + pad);
    return out;
}

/** The record back as index-ready chunks: [{...meta, text, stats, embedding}], plus the page. */
export function decodePage(bytes) {
    const length = new DataView(bytes.buffer, bytes.byteOffset).getUint32(0, true);
    const header = JSON.parse(new TextDecoder().decode(bytes.subarray(4, 4 + length)));
    const pad = (4 - ((4 + length) % 4)) % 4;
    const start = bytes.byteOffset + 4 + length + pad;
    const vectors = new Float32Array(bytes.buffer.slice(start, start + header.chunks.length * header.dim * 4));
    const title = unpackStats(header.title);
    const chunks = header.chunks.map((c, i) => ({
        ...header.page,
        id: c.id,
        chunk_id: c.chunk_id,
        text: c.text,
        stats: { title, text: unpackStats(c.stats) },
        embedding: vectors.subarray(i * header.dim, (i + 1) * header.dim),
    }));
    return { page: header.page, chunks };
}

// ---- storage backends ----------------------------------------------------------------

/** IndexedDB: database `name`, object store "pages" keyed by page_id. */
export class IdbStorage {
    constructor(name) {
        this.name = name;
        this.db = null;
    }

    async open() {
        this.db = await new Promise((resolve, reject) => {
            const req = indexedDB.open(this.name, 1);
            req.onupgradeneeded = () => req.result.createObjectStore("pages", { keyPath: "page_id" });
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    _tx(mode, fn) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction("pages", mode);
            const result = fn(tx.objectStore("pages"));
            tx.oncomplete = () => resolve(result && "result" in result ? result.result : undefined);
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error);
        });
    }

    getAll() { return this._tx("readonly", (s) => s.getAll()); }
    get(pageId) { return this._tx("readonly", (s) => s.get(pageId)); }
    put(record) { return this._tx("readwrite", (s) => s.put(record)); }
    delete(pageId) { return this._tx("readwrite", (s) => s.delete(pageId)); }
    clear() { return this._tx("readwrite", (s) => s.clear()); }

    close() {
        if (this.db) this.db.close();
        this.db = null;
    }

    async destroy() {
        this.close();
        await new Promise((resolve, reject) => {
            const req = indexedDB.deleteDatabase(this.name);
            req.onsuccess = resolve;
            req.onerror = () => reject(req.error);
            req.onblocked = resolve;
        });
    }
}

/** The same interface in memory (tests, Node). */
export class MemoryStorage {
    constructor() { this.records = new Map(); }
    async open() {}
    async getAll() { return [...this.records.values()]; }
    async get(pageId) { return this.records.get(pageId); }
    async put(record) { this.records.set(record.page_id, record); }
    async delete(pageId) { this.records.delete(pageId); }
    async clear() { this.records.clear(); }
    close() {}
    async destroy() { this.records.clear(); }
}

// ---- encrypted page store -----------------------------------------------------------

export class PageStore {
    /** @param storage IdbStorage | MemoryStorage  @param key CryptoKey (the device key) */
    constructor(storage, key) {
        this.storage = storage;
        this.key = key;
        this.sizes = new Map(); // page id -> bytes on disk
    }

    async open() {
        await this.storage.open();
    }

    /** Every stored page, decrypted: [{page, chunks}]. Records that can't be read are skipped. */
    async loadAll() {
        const pages = [];
        for (const record of await this.storage.getAll()) {
            try {
                pages.push(decodePage(await decrypt(this.key, record.data)));
                this.sizes.set(record.page_id, record.data.byteLength);
            } catch (_err) {
                // Encrypted with another key (a different account's or a reset key): unreadable.
            }
        }
        return pages;
    }

    async putPage(page, chunks) {
        const data = await encrypt(this.key, encodePage(page, chunks));
        await this.storage.put({ page_id: page.page_id, data });
        this.sizes.set(page.page_id, data.byteLength);
    }

    async readPage(pageId) {
        const record = await this.storage.get(pageId);
        return record ? decodePage(await decrypt(this.key, record.data)) : null;
    }

    async deletePage(pageId) {
        await this.storage.delete(pageId);
        this.sizes.delete(pageId);
    }

    get bytes() {
        let total = 0;
        for (const n of this.sizes.values()) total += n;
        return total;
    }

    close() {
        this.storage.close();
    }
}
