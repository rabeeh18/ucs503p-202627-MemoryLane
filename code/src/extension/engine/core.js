// The local engine: saving, storing and searching pages on this device, with
// answers shaped like the server's API responses so the extension and the
// website treat both the same way.
//
//   save    -> engine/ingest.js (the server's Python, in Pyodide) + embedder
//   store   -> engine/store.js (encrypted IndexedDB)
//   search  -> engine/retrieval.js over engine/local_index.js
import { LocalIndex } from "./local_index.js";
import { PageStore } from "./store.js";
import { hybridSearch } from "./retrieval.js";
import { normalizeUrl, generatePageId, urlparse } from "./url.js";
import { preparePage } from "./ingest.js";

const VECTOR_CACHE_PAGES = 200;

function pageInfo(head, withChunks = true) {
    return {
        id: head.page_id,
        url: head.url || "",
        title: head.title || "",
        domain: head.domain || "",
        timestamp: String(head.timestamp || ""),
        ...(withChunks ? { chunks: Number(head.total_chunks || 0) } : {}),
    };
}

// backend/ingest.py resolve_canonical_url, for the quick "is this page saved?" check.
function sameSite(a, b) {
    a = a.toLowerCase().replace(/^www\./, "");
    b = b.toLowerCase().replace(/^www\./, "");
    return a === b || a.endsWith("." + b) || b.endsWith("." + a);
}

function isAncestor(canonical, page) {
    const canon = canonical.pathname.split("/").filter(Boolean);
    const path = page.pathname.split("/").filter(Boolean);
    if (!canon.length) return Boolean(path.length || page.search);
    return canon.length < path.length && canon.every((s, i) => path[i] === s);
}

export function resolveCanonicalUrl(url, canonicalUrl) {
    if (canonicalUrl && canonicalUrl.trim()) {
        try {
            const resolved = new URL(canonicalUrl.trim(), url);
            const page = new URL(url);
            if ((resolved.protocol === "http:" || resolved.protocol === "https:") && resolved.hostname && page.hostname
                && sameSite(resolved.hostname, page.hostname) && !isAncestor(resolved, page)) {
                return /^[a-z][a-z0-9+.-]*:/i.test(canonicalUrl.trim()) ? canonicalUrl.trim() : resolved.href;
            }
        } catch (_err) {
            // fall through
        }
    }
    return url;
}

export class LocalEngine {
    /**
     * @param {{storage, key: CryptoKey, libraryId: string, embedder: () => Promise<{embedQuery, embedPassages}>,
     *          ingest: () => Promise<object>}} deps
     */
    constructor({ storage, key, libraryId, embedder, ingest }) {
        this.libraryId = libraryId;
        this.store = new PageStore(storage, key);
        this.getEmbedder = embedder;
        this.getIngest = ingest;
        this.vectorCache = new Map(); // page id -> Map(chunk id -> Float32Array)
        this.index = new LocalIndex((ids) => this._fullVectors(ids));
        this.queue = Promise.resolve(); // one write at a time, as the server's per-user lock
    }

    async open() {
        await this.store.open();
        for (const { page, chunks } of await this.store.loadAll()) this.index.putPage(page.page_id, chunks);
        return this.stats();
    }

    close() {
        this.store.close();
        this.index.clear();
        this.vectorCache.clear();
    }

    stats() {
        return { pages: this.index.pageCount, bytes: this.store.bytes };
    }

    _serial(fn) {
        const run = this.queue.then(fn, fn);
        this.queue = run.catch(() => {});
        return run;
    }

    async _fullVectors(chunkIds) {
        const out = new Map();
        const byPage = new Map();
        for (const id of chunkIds) {
            const pageId = id.split("::")[0];
            if (!byPage.has(pageId)) byPage.set(pageId, []);
            byPage.get(pageId).push(id);
        }
        for (const [pageId, ids] of byPage) {
            let vectors = this.vectorCache.get(pageId);
            if (!vectors) {
                const stored = await this.store.readPage(pageId);
                vectors = new Map((stored ? stored.chunks : []).map((c) => [c.id, Float32Array.from(c.embedding)]));
                this.vectorCache.set(pageId, vectors);
                if (this.vectorCache.size > VECTOR_CACHE_PAGES) this.vectorCache.delete(this.vectorCache.keys().next().value);
            }
            for (const id of ids) out.set(id, vectors.get(id));
        }
        return out;
    }

    // ---- saving --------------------------------------------------------------------

    /**
     * Save a page as POST /memory does: same body. Resolves the API's response
     * {status, message, page} or throws {status, detail} like an HTTP error.
     */
    save(body) {
        return this._serial(async () => {
            const ingest = await this.getIngest();
            const prepared = await preparePage(ingest, { ...body, user_id: this.libraryId }, (pageId) => {
                const head = this.index.chunks.get(this.index.pages.get(pageId)?.[0]);
                return head ? JSON.stringify(head) : null;
            });
            if (prepared.error) throw prepared.error;
            if (prepared.skipped) return { status: "skipped", message: prepared.skipped, page: null };
            const { result, docs, embed_texts: texts } = prepared;
            if (result.status === "saved") {
                const { embedPassages } = await this.getEmbedder();
                const vectors = await embedPassages(texts);
                const chunks = docs.map((d, i) => ({ ...d, embedding: Float32Array.from(vectors[i]) }));
                await this.store.putPage(chunks[0], chunks);
                this.vectorCache.delete(result.page_id);
                this.index.putPage(result.page_id, chunks);
            }
            return {
                status: result.status,
                message: result.message,
                page: {
                    id: result.page_id, url: result.url, title: result.title, domain: result.domain,
                    timestamp: result.timestamp, chunks: result.chunks,
                },
            };
        });
    }

    /** Store a page moving in from the server ({url, title, chunks, description, timestamp, content_hash}). */
    importPage(page) {
        return this.save({
            url: page.url, title: page.title, content: "", is_manual: true,
            chunks: page.chunks, content_hash: page.content_hash || null,
            timestamp: page.timestamp, description: page.description ?? "",
        });
    }

    /** What moving a page to the server sends (POST /memory/transfer). */
    exportPage(pageId) {
        const ids = this.index.pages.get(pageId);
        if (!ids) return null;
        const head = this.index.chunks.get(ids[0]);
        return {
            url: head.url, title: head.title, description: head.description || "",
            timestamp: head.timestamp, content_hash: head.content_hash || null,
            chunks: ids.map((id) => this.index.chunks.get(id).text),
        };
    }

    deletePage(pageId) {
        return this._serial(async () => {
            if (!this.index.hasPage(pageId)) return false;
            await this.store.deletePage(pageId);
            this.index.removePage(pageId);
            this.vectorCache.delete(pageId);
            return true;
        });
    }

    deleteAll() {
        return this._serial(async () => {
            await this.store.storage.clear();
            this.store.sizes.clear();
            this.index.clear();
            this.vectorCache.clear();
        });
    }

    // ---- reading -------------------------------------------------------------------

    /** GET /memory/status for a page on this device. */
    async status(url, canonicalUrl) {
        const normalized = normalizeUrl(resolveCanonicalUrl(url, canonicalUrl));
        const head = await this.index.getPageHead(await generatePageId(this.libraryId, normalized));
        return head ? { saved: true, page: pageInfo(head) } : { saved: false, page: null };
    }

    existing(ids) {
        return ids.filter((id) => this.index.hasPage(id));
    }

    /** GET /memories. */
    list(limit = 20, offset = 0) {
        const { total, pages } = this.index.listPages(limit, offset);
        return { total, pages: pages.map((p) => pageInfo(p, false)) };
    }

    /** Every page, oldest first: [{id, bytes, timestamp}] (for moving the oldest to the server). */
    oldestFirst() {
        const heads = this.index.listPages(Number.MAX_SAFE_INTEGER, 0).pages.reverse();
        return heads.map((h) => ({ id: h.page_id, bytes: this.store.sizes.get(h.page_id) || 0, timestamp: h.timestamp }));
    }

    pageText(pageId) {
        return this.index.pageText(pageId);
    }

    pageTitle(pageId) {
        const ids = this.index.pages.get(pageId);
        return ids ? this.index.chunks.get(ids[0]).title || "" : "";
    }

    /** POST /search. */
    async search(query, numResults = 10) {
        const { embedQuery, embedPassages } = await this.getEmbedder();
        const results = await hybridSearch(query, this.index, {
            userId: this.libraryId, embedQuery, embedPassages, topK: numResults,
        });
        return {
            query,
            results: results.map((r) => ({
                rank: r.rank, id: r.page_id, title: r.title || "", url: r.url || "", domain: r.domain || "",
                timestamp: String(r.timestamp || ""), snippet: r.snippet, summary: null, location: "device",
            })),
        };
    }

    /** Everything needed to rebuild this device's pages elsewhere (encrypted backups). */
    exportAll() {
        return [...this.index.pages.keys()].map((id) => this.exportPage(id));
    }
}

export { urlparse };
