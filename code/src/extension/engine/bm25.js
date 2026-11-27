// Keyword (BM25) search that scores exactly as the server's Solr query does:
// edismax over title^2 and text, phrase boosts text^2 and title^3, Lucene 9's
// BM25 (k1 1.2, b 0.75) with its one-byte document lengths and float maths.
// (backend/solr_client.py, bm25_search.)
//
// The index keeps, per field, each term's postings (chunk number and count);
// positions are recomputed from the stored text only for the few chunks that
// contain every word of a phrase.

import { analyzeIndex, analyzeQuery } from "./analyzer.js";

const K1 = Math.fround(1.2);
const B = Math.fround(0.75);
export const FIELDS = [
    { name: "title", boost: 2, phraseBoost: 3 },
    { name: "text", boost: 1, phraseBoost: 2 },
];
const f = Math.fround;

// ---- Lucene's SmallFloat: document lengths stored in one byte ----------------

function longToInt4(i) {
    const numBits = 32 - Math.clz32(i);
    if (numBits < 4) return i;
    const shift = numBits - 4;
    let encoded = (i >>> shift) & 0x07;
    encoded |= (shift + 1) << 3;
    return encoded;
}

function int4ToLong(i) {
    const bits = i & 0x07;
    const shift = (i >>> 3) - 1;
    return shift === -1 ? bits : (bits | 0x08) * 2 ** shift;
}

const NUM_FREE_VALUES = 255 - longToInt4(2 ** 31 - 1);

export function intToByte4(i) {
    if (i < NUM_FREE_VALUES) return i;
    return NUM_FREE_VALUES + longToInt4(i - NUM_FREE_VALUES);
}

function byte4ToInt(b) {
    if (b < NUM_FREE_VALUES) return b;
    return Math.min(NUM_FREE_VALUES + int4ToLong(b - NUM_FREE_VALUES), 2 ** 31 - 1);
}

const LENGTH_TABLE = Array.from({ length: 256 }, (_, i) => byte4ToInt(i));

function idf(docFreq, docCount) {
    return f(Math.log(1 + (docCount - docFreq + 0.5) / (docFreq + 0.5)));
}

// ---- the index ---------------------------------------------------------------

/** Term counts and length of one field's text: {length, terms: Map(term -> freq)}. */
export function fieldStats(text) {
    const terms = new Map();
    const tokens = analyzeIndex(text || "");
    for (const { term } of tokens) terms.set(term, (terms.get(term) || 0) + 1);
    return { length: tokens.length, terms };
}

class FieldIndex {
    constructor() {
        this.postings = new Map(); // term -> Map(doc -> freq)
        this.norms = new Map(); // doc -> norm byte (only docs with the field)
        this.sumTotalTermFreq = 0;
    }

    add(doc, stats) {
        if (!stats.length) return;
        this.norms.set(doc, intToByte4(stats.length));
        this.sumTotalTermFreq += stats.length;
        for (const [term, freq] of stats.terms) {
            let list = this.postings.get(term);
            if (!list) this.postings.set(term, (list = new Map()));
            list.set(doc, freq);
        }
    }

    remove(doc, stats) {
        if (!this.norms.has(doc)) return;
        this.norms.delete(doc);
        this.sumTotalTermFreq -= stats.length;
        for (const term of stats.terms.keys()) {
            const list = this.postings.get(term);
            if (!list) continue;
            list.delete(doc);
            if (!list.size) this.postings.delete(term);
        }
    }

    get docCount() {
        return this.norms.size;
    }

    /** 1 / (k1 * ((1 - b) + b * length / avgdl)) for each of the 256 norm bytes. */
    normCache() {
        if (this._cacheKey === `${this.sumTotalTermFreq}/${this.docCount}`) return this._cache;
        const avgdl = f(this.sumTotalTermFreq / this.docCount);
        const cache = new Float32Array(256);
        for (let i = 0; i < 256; i++) {
            cache[i] = f(1 / f(K1 * f(f(1 - B) + f(f(B * LENGTH_TABLE[i]) / avgdl))));
        }
        this._cacheKey = `${this.sumTotalTermFreq}/${this.docCount}`;
        this._cache = cache;
        return cache;
    }
}

function bm25Score(weight, freq, normInverse) {
    return f(weight - f(weight / f(1 + f(freq * normInverse))));
}

export class Bm25Index {
    constructor() {
        this.fields = { title: new FieldIndex(), text: new FieldIndex() };
        this.stats = new Map(); // doc -> {title, text} field stats
        this.order = new Map(); // doc -> insertion number (ties break by it, as Lucene's doc ids do)
        this.next = 0;
    }

    /** Add (or replace) a chunk. `doc` is the chunk id; stats from fieldStats(). */
    add(doc, title, text) {
        this.remove(doc);
        const stats = { title: fieldStats(title), text: fieldStats(text) };
        this.addStats(doc, stats);
        return stats;
    }

    addStats(doc, stats) {
        this.remove(doc);
        this.stats.set(doc, stats);
        this.order.set(doc, this.next++);
        this.fields.title.add(doc, stats.title);
        this.fields.text.add(doc, stats.text);
    }

    remove(doc) {
        const stats = this.stats.get(doc);
        if (!stats) return;
        this.fields.title.remove(doc, stats.title);
        this.fields.text.remove(doc, stats.text);
        this.stats.delete(doc);
        this.order.delete(doc);
    }

    get size() {
        return this.stats.size;
    }
}

// ---- edismax query parsing (the subset people type) -------------------------

const OPERATOR = /^(AND|OR|NOT|&&|\|\||!)$/;

/**
 * Split a query into clauses as edismax does: quoted phrases, +required,
 * -excluded, AND / OR / NOT, wildcards. Returns {clauses, normalText}, where
 * normalText is the unquoted words used for the phrase boost.
 */
export function parseQuery(query) {
    const raw = [];
    const re = /([+\-!]?)"([^"]*)"|(\S+)/g;
    let m;
    while ((m = re.exec(query))) {
        if (m[2] !== undefined) {
            raw.push({ word: m[2], sign: m[1], quoted: true });
        } else {
            // Brackets group clauses; they also end a word ("Lp(a)" is "Lp" and "a").
            for (const part of m[3].split(/[()]+/)) if (part) raw.push({ word: part, sign: "", quoted: false });
        }
    }
    const clauses = [];
    const normal = [];
    let pendingNot = false;
    let pendingAnd = false;
    for (let i = 0; i < raw.length; i++) {
        let { word, sign, quoted } = raw[i];
        if (!quoted && OPERATOR.test(word)) {
            if (word === "NOT" || word === "!") pendingNot = true;
            else if (word === "AND" || word === "&&") {
                pendingAnd = true;
                if (clauses.length && clauses[clauses.length - 1].occur === "should") {
                    // a AND b: the clause before becomes required too
                    for (let c = clauses.length - 1; c >= 0 && clauses[c].group === clauses[clauses.length - 1].group; c--) {
                        clauses[c].occur = "must";
                    }
                }
            }
            continue;
        }
        if (!quoted) {
            word = word.replace(/[()]/g, "");
            if (word[0] === "+" || word[0] === "-" || word[0] === "!") {
                sign = word[0];
                word = word.slice(1);
            }
            word = word.replace(/[\^~][\d.]*$/, "");
        }
        if (!word) continue;
        let occur = "should";
        if (sign === "+" || pendingAnd) occur = "must";
        if (sign === "-" || sign === "!" || pendingNot) occur = "mustNot";
        pendingNot = false;
        pendingAnd = false;
        const group = i;
        if (quoted) {
            const positions = analyzeQuery(word);
            if (positions.length) clauses.push({ kind: positions.length > 1 ? "phrase" : "term", positions, occur, group });
            continue;
        }
        normal.push(word);
        if (/[*?]/.test(word) && /[^*?]/.test(word)) {
            clauses.push({ kind: "wildcard", pattern: wildcardRegex(word.toLowerCase()), occur, group });
            continue;
        }
        for (const position of analyzeQuery(word)) {
            clauses.push({ kind: "term", positions: [position], occur, group });
        }
    }
    return { clauses, normalText: normal.join(" ") };
}

function wildcardRegex(pattern) {
    const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
    return new RegExp(`^${escaped}$`);
}

// ---- scoring -----------------------------------------------------------------

/** Score of one term position (a term or its synonyms) in one field, per doc. */
function termScores(field, fieldBoost, terms, docs) {
    const present = terms.map((t) => field.postings.get(t)).filter(Boolean);
    const out = new Map();
    if (!present.length) return out;
    const docCount = field.docCount;
    const docFreq = Math.max(...present.map((p) => p.size));
    const weight = f(fieldBoost * idf(docFreq, docCount));
    const cache = field.normCache();
    const candidates = docs || new Set(present.flatMap((p) => [...p.keys()]));
    for (const doc of candidates) {
        let freq = 0;
        for (const t of terms) {
            const p = field.postings.get(t);
            const n = p && p.get(doc);
            if (n) freq += n;
        }
        if (!freq) continue;
        out.set(doc, bm25Score(weight, f(freq), cache[field.norms.get(doc)]));
    }
    return out;
}

/** Phrase (with stop-word gaps and synonyms) in one field: doc -> score. */
function phraseScores(index, fieldName, field, boost, positions, textOf) {
    const out = new Map();
    const lists = positions.map(({ terms }) => terms.map((t) => field.postings.get(t)).filter(Boolean));
    if (lists.some((l) => !l.length)) return out;
    // Chunks holding at least one term of every position.
    let candidates = null;
    for (const list of lists) {
        const docs = new Set(list.flatMap((p) => [...p.keys()]));
        candidates = candidates ? new Set([...candidates].filter((d) => docs.has(d))) : docs;
        if (!candidates.size) return out;
    }
    let idfSum = 0;
    for (const { terms } of positions) {
        for (const t of terms) {
            const p = field.postings.get(t);
            if (p) idfSum += idf(p.size, field.docCount);
        }
    }
    const weight = f(boost * f(idfSum));
    const cache = field.normCache();
    const offsets = positions.map((p) => p.pos - positions[0].pos);
    const sets = positions.map(({ terms }) => new Set(terms));
    for (const doc of candidates) {
        const tokens = analyzeIndex(textOf(doc, fieldName));
        const at = new Map(tokens.map((t) => [t.pos, t.term]));
        let freq = 0;
        for (const { term, pos } of tokens) {
            if (!sets[0].has(term)) continue;
            if (offsets.every((o, i) => sets[i].has(at.get(pos + o)))) freq++;
        }
        if (freq) out.set(doc, bm25Score(weight, f(freq), cache[field.norms.get(doc)]));
    }
    return out;
}

function wildcardScores(field, boost, pattern) {
    const out = new Map();
    for (const [term, list] of field.postings) {
        if (!pattern.test(term)) continue;
        for (const doc of list.keys()) out.set(doc, f(boost));
    }
    return out;
}

/** DisMax (tie 0) over the fields: the best field's score per doc. */
function disMax(perField) {
    const out = new Map();
    for (const scores of perField) {
        for (const [doc, s] of scores) {
            const cur = out.get(doc);
            if (cur === undefined || s > cur) out.set(doc, s);
        }
    }
    return out;
}

function clauseScores(index, clause, textOf) {
    return disMax(FIELDS.map(({ name, boost }) => {
        const field = index.fields[name];
        if (clause.kind === "wildcard") return wildcardScores(field, boost, clause.pattern);
        if (clause.kind === "phrase") return phraseScores(index, name, field, boost, clause.positions, textOf);
        return termScores(field, boost, clause.positions[0].terms);
    }));
}

/**
 * The edismax query: [{doc, score}] best first, at most `rows`, within the
 * chunks `allowed` accepts. `textOf(doc, field)` returns a chunk's stored
 * title or text (for phrase positions).
 */
export function searchBm25(index, query, { rows = 50, allowed = null, textOf }) {
    const { clauses, normalText } = parseQuery(query);
    if (!clauses.length) return [];
    const scored = clauses.map((c) => ({ clause: c, scores: clauseScores(index, c, textOf) }));
    const must = scored.filter((s) => s.clause.occur === "must");
    const should = scored.filter((s) => s.clause.occur === "should");
    const mustNot = scored.filter((s) => s.clause.occur === "mustNot");
    if (!must.length && !should.length) return [];

    let docs;
    if (must.length) {
        docs = new Set(must[0].scores.keys());
        for (const s of must.slice(1)) docs = new Set([...docs].filter((d) => s.scores.has(d)));
    } else {
        docs = new Set(should.flatMap((s) => [...s.scores.keys()]));
    }
    for (const s of mustNot) for (const d of s.scores.keys()) docs.delete(d);
    if (allowed) docs = new Set([...docs].filter((d) => allowed(d)));

    // Phrase boost over the unquoted words (pf), when there are two or more.
    const pfPositions = analyzeQuery(normalText);
    let pf = new Map();
    if (pfPositions.length > 1) {
        pf = disMax(FIELDS.map(({ name, phraseBoost }) =>
            phraseScores(index, name, index.fields[name], phraseBoost, pfPositions, textOf)));
    }

    const results = [];
    for (const doc of docs) {
        let sum = 0; // Lucene sums a disjunction in double, then rounds to float
        for (const s of must.concat(should)) {
            const v = s.scores.get(doc);
            if (v !== undefined) sum += v;
        }
        let score = f(sum);
        const boost = pf.get(doc);
        if (boost !== undefined) score = f(score + boost);
        results.push({ doc, score });
    }
    results.sort((a, b) => b.score - a.score || index.order.get(a.doc) - index.order.get(b.doc));
    return results.slice(0, rows);
}
