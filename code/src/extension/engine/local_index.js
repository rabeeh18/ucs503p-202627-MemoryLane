// The in-memory search index of the pages stored on this device. It answers
// the same questions the server asks Solr (see retrieval.js), with the same
// result order and scores:
//
// - keyword search: bm25.js (Solr's edismax and BM25);
// - vector search: exact cosine over every chunk, as Solr's (1 + cos) / 2 score.
//   Vectors are held as int8 (a quarter of the memory) for the scan; the best
//   candidates are then rescored with the full vectors, so the final scores are
//   exact. Full vectors come from `fullVectors(ids)` (IndexedDB in the extension).
import { Bm25Index, searchBm25 } from "./bm25.js";

const f = Math.fround;
// int8 rounding moves a cosine by at most ~0.016 (384 dims); typically ~0.001.
const RESCORE_MARGIN = 0.02;

/** int8 copy of a vector and its scale. */
export function quantize(vector) {
    let max = 0;
    for (const x of vector) max = Math.max(max, Math.abs(x));
    const scale = max / 127 || 1;
    const q = new Int8Array(vector.length);
    for (let i = 0; i < vector.length; i++) q[i] = Math.round(vector[i] / scale);
    return { q, scale };
}

/** Solr's cosine score for two float vectors: (1 + cos) / 2 as a float. */
export function solrCosineScore(a, b) {
    let dot = 0;
    let na = 0;
    let nb = 0;
    for (let i = 0; i < a.length; i++) {
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    const cos = f(dot / Math.sqrt(na * nb));
    return Math.max(f(f(1 + cos) / 2), 0);
}

const META_FIELDS = [
    "id", "page_id", "chunk_id", "total_chunks", "url", "title", "domain", "timestamp",
    "description", "text", "content_hash", "embedding_model",
];

export class LocalIndex {
    /** @param {(ids: string[]) => Promise<Map<string, Float32Array>>} fullVectors */
    constructor(fullVectors) {
        this.fullVectors = fullVectors;
        this.chunks = new Map(); // chunk id -> metadata (incl. text)
        this.vectors = new Map(); // chunk id -> {q, scale}
        this.pages = new Map(); // page id -> [chunk ids in order]
        this.bm25 = new Bm25Index();
        this.order = new Map(); // chunk id -> insertion number
        this.next = 0;
    }

    // ---- writes ----------------------------------------------------------------

    /**
     * Add or replace a page. `chunks` carry the fields above plus `embedding`
     * (Float32Array or array) and optionally precomputed `stats` (bm25 fieldStats).
     */
    putPage(pageId, chunks) {
        this.removePage(pageId);
        const ids = [];
        for (const chunk of chunks) {
            const meta = {};
            for (const k of META_FIELDS) if (chunk[k] !== undefined) meta[k] = chunk[k];
            this.chunks.set(chunk.id, meta);
            this.order.set(chunk.id, this.next++);
            if (chunk.quantized) this.vectors.set(chunk.id, chunk.quantized);
            else this.vectors.set(chunk.id, quantize(chunk.embedding));
            if (chunk.stats) this.bm25.addStats(chunk.id, chunk.stats);
            else this.bm25.add(chunk.id, meta.title, meta.text);
            ids.push(chunk.id);
        }
        this.pages.set(pageId, ids);
    }

    removePage(pageId) {
        for (const id of this.pages.get(pageId) || []) {
            this.chunks.delete(id);
            this.vectors.delete(id);
            this.order.delete(id);
            this.bm25.remove(id);
        }
        this.pages.delete(pageId);
    }

    clear() {
        for (const pageId of [...this.pages.keys()]) this.removePage(pageId);
    }

    // ---- filters (the Solr fq the server builds) --------------------------------

    _passes(meta, { pageIds = null, filters = null } = {}) {
        if (pageIds && !pageIds.has(meta.page_id)) return false;
        if (filters) {
            if (filters.domains && !filters.domains.has(meta.domain)) return false;
            if (filters.savedFrom !== undefined) {
                const t = Date.parse(meta.timestamp);
                if (!(t >= filters.savedFrom && t < filters.savedUntil)) return false;
            }
        }
        return true;
    }

    _copy(id, score) {
        const doc = { ...this.chunks.get(id) };
        if (score !== undefined) doc.score = score;
        return doc;
    }

    // ---- the questions retrieval.js asks ----------------------------------------

    async bm25Search(query, { rows = 30, pageIds = null, filters = null } = {}) {
        const ids = pageIds ? new Set(pageIds) : null;
        const hits = searchBm25(this.bm25, query, {
            rows,
            allowed: (doc) => this._passes(this.chunks.get(doc), { pageIds: ids, filters }),
            textOf: (doc, field) => this.chunks.get(doc)[field] || "",
        });
        return hits.map(({ doc, score }) => this._copy(doc, score));
    }

    async knnSearch(vector, { k = 30, pageIds = null, filters = null } = {}) {
        const ids = pageIds ? new Set(pageIds) : null;
        const query = Float32Array.from(vector);
        const approx = [];
        for (const [id, { q, scale }] of this.vectors) {
            if (!this._passes(this.chunks.get(id), { pageIds: ids, filters })) continue;
            let dot = 0;
            for (let i = 0; i < q.length; i++) dot += query[i] * q[i];
            approx.push([id, dot * scale]);
        }
        if (!approx.length) return [];
        approx.sort((a, b) => b[1] - a[1]);
        const kth = approx[Math.min(k, approx.length) - 1][1];
        const candidates = approx.filter(([, s], i) => i < k || s >= kth - RESCORE_MARGIN).map(([id]) => id);
        const full = await this.fullVectors(candidates);
        const scored = candidates.map((id) => [id, solrCosineScore(query, full.get(id))]);
        scored.sort((a, b) => b[1] - a[1] || this.order.get(a[0]) - this.order.get(b[0]));
        return scored.slice(0, k).map(([id, score]) => this._copy(id, score));
    }

    _heads(filters = null) {
        const heads = [];
        for (const ids of this.pages.values()) {
            const meta = this.chunks.get(ids[0]);
            if (meta && meta.chunk_id === 0 && this._passes(meta, { filters })) heads.push(meta);
        }
        return heads;
    }

    async recentPages(filters, { rows = 30, near = null } = {}) {
        const heads = this._heads(filters);
        const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
        if (near !== null) {
            heads.sort((a, b) => Math.abs(Date.parse(a.timestamp) - near) - Math.abs(Date.parse(b.timestamp) - near) || byId(a, b));
        } else {
            heads.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp) || byId(a, b));
        }
        return heads.slice(0, rows).map((m) => this._copy(m.id));
    }

    /** The sites pages were saved from, most pages first. */
    async listDomains() {
        const counts = new Map();
        for (const m of this._heads()) counts.set(m.domain, (counts.get(m.domain) || 0) + 1);
        return [...counts.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).map(([d]) => d);
    }

    async getPageHead(pageId) {
        const ids = this.pages.get(pageId);
        return ids ? this._copy(ids[0]) : null;
    }

    // ---- the library ----------------------------------------------------------

    /** Pages newest first: {total, pages: [head]}. */
    listPages(limit = 20, offset = 0) {
        const heads = this._heads();
        heads.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp) || (a.id < b.id ? -1 : 1));
        return { total: heads.length, pages: heads.slice(offset, offset + limit).map((m) => ({ ...m })) };
    }

    pageText(pageId) {
        const ids = this.pages.get(pageId);
        if (!ids) return null;
        return ids.map((id) => this.chunks.get(id).text || "").join("\n\n");
    }

    hasPage(pageId) {
        return this.pages.has(pageId);
    }

    get pageCount() {
        return this.pages.size;
    }
}
