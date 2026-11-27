// Hybrid search on the local store: a step-for-step port of
// backend/retrieval.py's hybrid_search, so a library searched in the browser
// ranks, filters and cuts off exactly as the same library on the server.
//
// The store answers the same questions the server asks Solr (bm25Search,
// knnSearch, recentPages, listDomains, getPageHead) and returns fresh copies
// of chunk documents with a Solr-style `score`.
import { SETTINGS } from "./settings.js";
import { isActive, parseQuery } from "./query_intent.js";
import { buildSnippets, queryTerms, termScore } from "./snippets.js";
import { generatePageId } from "./url.js";

// Read at call time: the extension may refresh SETTINGS from the server.
const S = SETTINGS;

const SIMILARITY_CHECK_MAX_PAGES = 50;
const SIMILARITY_CHECK_CHUNKS_PER_PAGE = 8;
const SIMILARITY_CHECK_MAX_CHUNKS = 300;

export const knnScoreToCosine = (score) => 2.0 * Number(score) - 1.0;

export function rrfFuseLists(rankedLists, k) {
    const fused = new Map();
    for (const [ids, weight] of rankedLists) {
        ids.forEach((id, i) => fused.set(id, (fused.get(id) || 0) + weight / (k + i + 1)));
    }
    return fused;
}

/** Solr dates are whole seconds: the filters the server sends drop fractions. */
const toSecond = (ms) => Math.floor(ms / 1000) * 1000;

export function intentFilters(intent) {
    const filters = {};
    let any = false;
    if (intent.domains.size) {
        filters.domains = new Set(intent.domains);
        any = true;
    }
    if (intent.savedFrom !== null) {
        filters.savedFrom = toSecond(intent.savedFrom);
        filters.savedUntil = toSecond(intent.savedUntil);
        any = true;
    }
    return any ? filters : null;
}

export function groupByWebpage(candidates, fused, secondChunkWeight = S.PAGE_SECOND_CHUNK_WEIGHT) {
    const pages = new Map();
    for (const doc of candidates) {
        const score = fused.get(doc.id) || 0;
        if (!pages.has(doc.page_id)) pages.set(doc.page_id, []);
        pages.get(doc.page_id).push([score, doc]);
    }
    const results = [];
    for (const [pageId, scored] of pages) {
        scored.sort((a, b) => b[0] - a[0]);
        const [bestScore, best] = scored[0];
        const secondScore = scored.length > 1 ? scored[1][0] : 0;
        const sims = scored.map(([, d]) => d._vector_sim).filter((s) => s !== null && s !== undefined);
        results.push({
            page_id: pageId,
            id: best.id,
            url: best.url || "",
            title: best.title || "",
            domain: best.domain || "",
            timestamp: best.timestamp || "",
            text: best.text || "",
            description: best.description || "",
            fused_score: bestScore + secondChunkWeight * secondScore,
            bm25_rank: best._bm25_rank ?? null,
            knn_rank: best._knn_rank ?? null,
            bm25_match: scored.some(([, d]) => d._bm25_rank),
            intent_match: scored.some(([, d]) => d._intent_match),
            vector_similarity: sims.length ? Math.max(...sims) : null,
        });
    }
    results.sort((a, b) => b.fused_score - a.fused_score);
    return results;
}

export function keywordCoverage(page, terms) {
    if (!terms.length) return 1.0;
    return termScore(`${page.title || ""} ${page.text || ""}`, terms) / terms.length;
}

const strongKeywordMatch = (page, terms) => terms === null || keywordCoverage(page, terms) >= S.KEYWORD_FULL_MATCH;

export function applyRelevanceFloor(pages, { minSimilarity = S.MIN_VECTOR_SIMILARITY, terms = null, keywordMinSimilarity = null } = {}) {
    const kwMin = keywordMinSimilarity ?? minSimilarity;
    const similar = (page, threshold) => page.vector_similarity !== null && page.vector_similarity >= threshold;
    return pages.filter((page) => {
        if (page.intent_match) return true;
        if (page.bm25_match) return strongKeywordMatch(page, terms) || similar(page, kwMin);
        return similar(page, minSimilarity);
    });
}

async function fillKeywordSimilarity(store, pages, terms, queryVector) {
    const need = pages.filter((p) => p.bm25_match && !p.intent_match && p.vector_similarity === null
        && !strongKeywordMatch(p, terms)).slice(0, SIMILARITY_CHECK_MAX_PAGES);
    if (!need.length) return 0;
    const ids = need.map((p) => p.page_id);
    const k = Math.min(SIMILARITY_CHECK_CHUNKS_PER_PAGE * ids.length, SIMILARITY_CHECK_MAX_CHUNKS);
    const docs = await store.knnSearch(await queryVector(), { k, pageIds: ids });
    const best = new Map();
    for (const doc of docs) {
        const sim = knnScoreToCosine(doc.score);
        best.set(doc.page_id, Math.max(sim, best.has(doc.page_id) ? best.get(doc.page_id) : -1.0));
    }
    for (const page of need) if (best.has(page.page_id)) page.vector_similarity = best.get(page.page_id);
    return ids.length;
}

async function intentLists(store, intent, rows, queryVector, userId) {
    const lists = [];
    const filters = intentFilters(intent);
    if (filters) {
        if (intent.text) {
            const bm25 = S.BM25_WEIGHT > 0 ? store.bm25Search(intent.text, { rows, filters }) : null;
            if (S.VECTOR_WEIGHT > 0) {
                const knn = await store.knnSearch(await queryVector(), { k: rows, filters });
                lists.push([knn, S.VECTOR_WEIGHT * S.INTENT_WEIGHT, "knn"]);
            }
            if (bm25 !== null) lists.push([await bm25, S.BM25_WEIGHT * S.INTENT_WEIGHT, "bm25"]);
        } else {
            const near = intent.savedNear !== null ? toSecond(intent.savedNear) : null;
            lists.push([await store.recentPages(filters, { rows, near }), 2 * (S.BM25_WEIGHT + S.VECTOR_WEIGHT) * S.INTENT_WEIGHT, "recent"]);
        }
    }
    if (intent.url) {
        const head = await store.getPageHead(await generatePageId(userId, intent.url));
        if (head) lists.push([[head], 10 * (S.BM25_WEIGHT + S.VECTOR_WEIGHT), "url"]);
    }
    return lists;
}

/**
 * The full pipeline: [{rank, page_id, url, title, domain, timestamp, snippet, ...}].
 * `embedQuery(text)` and `embedPassages(texts)` return normalised vectors.
 */
export async function hybridSearch(query, store, {
    userId, embedQuery, embedPassages, topK = S.DEFAULT_TOP_K, candidatePool = S.DEFAULT_CANDIDATE_POOL,
    timings = null, snippets = true, now = Date.now(),
}) {
    const start = performance.now();
    let vectorPromise = null;
    const queryVector = () => (vectorPromise ||= embedQuery(query));

    const bm25Promise = S.BM25_WEIGHT > 0 ? store.bm25Search(query, { rows: candidatePool }) : Promise.resolve([]);
    const knnPromise = S.VECTOR_WEIGHT > 0
        ? queryVector().then((v) => store.knnSearch(v, { k: candidatePool }))
        : Promise.resolve([]);

    let intentListsFound = [];
    let intent = null;
    try {
        intent = S.QUERY_INTENT_ENABLED ? parseQuery(query, await store.listDomains(), now) : null;
    } catch (_err) {
        intent = null;
    }
    if (intent && isActive(intent)) {
        try {
            intentListsFound = await intentLists(store, intent, candidatePool, queryVector, userId);
        } catch (_err) {
            intentListsFound = [];
        }
    }
    const [bm25Docs, knnDocs] = await Promise.all([bm25Promise, knnPromise]);
    const searched = performance.now();

    const candidates = new Map();
    bm25Docs.forEach((doc, i) => {
        doc._bm25_rank = i + 1;
        doc._knn_rank = null;
        candidates.set(doc.id, doc);
    });
    knnDocs.forEach((doc, i) => {
        const sim = knnScoreToCosine(doc.score);
        const cur = candidates.get(doc.id);
        if (cur) {
            cur._knn_rank = i + 1;
            cur._vector_sim = sim;
        } else {
            doc._bm25_rank = null;
            doc._knn_rank = i + 1;
            doc._vector_sim = sim;
            candidates.set(doc.id, doc);
        }
    });
    for (const [docs, , kind] of intentListsFound) {
        for (const doc of docs) {
            let cur = candidates.get(doc.id);
            if (!cur) {
                if (!("_bm25_rank" in doc)) doc._bm25_rank = null;
                if (!("_knn_rank" in doc)) doc._knn_rank = null;
                candidates.set(doc.id, (cur = doc));
            }
            if (kind === "knn") {
                cur._vector_sim = Math.max(knnScoreToCosine(doc.score), cur._vector_sim || -1.0);
            } else {
                cur._intent_match = true;
            }
        }
    }

    const fused = rrfFuseLists(
        [[bm25Docs.map((d) => d.id), S.BM25_WEIGHT], [knnDocs.map((d) => d.id), S.VECTOR_WEIGHT]]
            .concat(intentListsFound.map(([docs, weight]) => [docs.map((d) => d.id), weight])),
        S.RRF_K,
    );

    const terms = queryTerms(query);
    const allPages = groupByWebpage([...candidates.values()], fused);
    try {
        await fillKeywordSimilarity(store, allPages, terms, queryVector);
    } catch (_err) {
        // as on the server: the floor then drops them
    }
    const grouped = applyRelevanceFloor(allPages, { terms });
    const results = grouped.slice(0, topK);
    const fusedAt = performance.now();

    const texts = snippets
        ? await buildSnippets(results.map((r) => [r.text || "", r.description]), query, await queryVector(), embedPassages)
        : results.map(() => null);
    results.forEach((r, i) => {
        r.rank = i + 1;
        r.snippet = texts[i];
    });
    if (timings) {
        timings.search_ms = Math.round((searched - start) * 10) / 10;
        timings.fuse_ms = Math.round((fusedAt - searched) * 10) / 10;
        timings.total_ms = Math.round((performance.now() - start) * 10) / 10;
    }
    return results;
}
