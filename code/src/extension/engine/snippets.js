// Search-result snippets: a port of backend/snippets.py. 2-3 consecutive
// readable sentences from the best chunk, around the sentence matching the most
// query terms; when none matches, the first few readable sentences are compared
// with the query by embedding.
import { isProse, stripCitations, trimAtWord } from "./cleaning.js";
import { WS, cpLen, words } from "./pytext.js";

export const SNIPPET_MIN_CHARS = 200;
export const SNIPPET_MAX_CHARS = 280;
const MAX_SNIPPET_SENTENCES = 3;
const MAX_EMBED_CANDIDATES = 3;

const STOPWORDS = new Set([
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "his", "how", "its", "who",
    "did", "get", "him", "she", "too", "use", "that", "this", "with", "from",
    "they", "them", "then", "than", "what", "when", "where", "which", "about",
    "into", "your", "some", "there", "their", "were", "been", "does", "also",
]);

export function queryTerms(query) {
    const terms = [];
    for (const term of words((query || "").toLowerCase())) {
        if (cpLen(term) >= 3 && !STOPWORDS.has(term) && !terms.includes(term)) terms.push(term);
    }
    return terms;
}

const SENTENCE_SPLIT = new RegExp(`(?<=[.!?…])["'”’)\\]]?[${WS}]+|\\n+`, "u");
const SPACES = new RegExp(`[${WS}]+`, "gu");

export function splitSentences(text) {
    return stripCitations(text || "")
        .split(SENTENCE_SPLIT)
        .filter((p) => p && p.replace(SPACES, ""))
        .map((p) => p.replace(SPACES, " ").replace(new RegExp(`^[${WS}]+|[${WS}]+$`, "gu"), ""));
}

/** Number of distinct query terms that prefix-match a word in the sentence. */
export function termScore(sentence, terms) {
    const ws = words(sentence.toLowerCase());
    let n = 0;
    for (const t of terms) if (ws.some((w) => w.startsWith(t))) n++;
    return n;
}

function windowAround(sentences, eligible, best, minChars = SNIPPET_MIN_CHARS, maxChars = SNIPPET_MAX_CHARS) {
    let lo = best;
    let hi = best;
    let textLen = cpLen(sentences[best]);
    if (textLen > maxChars) return trimAtWord(sentences[best], maxChars);
    while (textLen < minChars && hi - lo + 1 < MAX_SNIPPET_SENTENCES) {
        let grown = false;
        for (const j of [hi + 1, lo - 1]) {
            if (j >= 0 && j < sentences.length && eligible[j] && textLen + 1 + cpLen(sentences[j]) <= maxChars) {
                if (j > hi) hi = j;
                else lo = j;
                textLen += 1 + cpLen(sentences[j]);
                grown = true;
                break;
            }
        }
        if (!grown) break;
    }
    return sentences.slice(lo, hi + 1).join(" ");
}

function plan(text, description, terms) {
    const sentences = splitSentences(text);
    const eligible = sentences.map(isProse);
    const indices = eligible.flatMap((ok, i) => (ok ? [i] : []));
    if (!indices.length) return { sentences, eligible, candidates: [], description, best: null };
    const scores = new Map(indices.map((i) => [i, termScore(sentences[i], terms)]));
    const top = Math.max(...scores.values());
    const candidates = top > 0 ? [indices.find((i) => scores.get(i) === top)] : indices.slice(0, MAX_EMBED_CANDIDATES);
    return { sentences, eligible, candidates, description, best: candidates[0] };
}

const dot = (a, b) => {
    let s = 0;
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) s += a[i] * b[i];
    return s;
};

/**
 * Snippets for [text, description] pairs. `embed(texts)` resolves to passage
 * vectors; it is called once, only for results with no term match.
 */
export async function buildSnippets(items, query, queryVector = null, embed = null) {
    const terms = queryTerms(query);
    const plans = items.map(([text, description]) => plan(text, description, terms));

    const candidateTexts = [];
    if (queryVector && embed) {
        for (const p of plans) if (p.candidates.length > 1) candidateTexts.push(...p.candidates.map((i) => p.sentences[i]));
    }
    if (candidateTexts.length) {
        const unique = [...new Set(candidateTexts)];
        let vectors = new Map();
        try {
            const vecs = await embed(unique);
            vectors = new Map(unique.map((t, i) => [t, vecs[i]]));
        } catch (_err) {
            vectors = new Map(); // snippets must never break search
        }
        for (const p of plans) {
            if (vectors.size && p.candidates.length > 1) {
                let best = p.candidates[0];
                let bestScore = dot(vectors.get(p.sentences[best]) || [], queryVector);
                for (const i of p.candidates.slice(1)) {
                    const s = dot(vectors.get(p.sentences[i]) || [], queryVector);
                    if (s > bestScore) {
                        best = i;
                        bestScore = s;
                    }
                }
                p.best = best;
            }
        }
    }

    return plans.map((p) => {
        if (p.best !== null && p.best !== undefined) return windowAround(p.sentences, p.eligible, p.best);
        const fallback = (p.description || "").replace(SPACES, " ").replace(new RegExp(`^[${WS}]+|[${WS}]+$`, "gu"), "");
        return trimAtWord(fallback, SNIPPET_MAX_CHARS) || null;
    });
}
