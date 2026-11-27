// Keyword-search parity: the extension's BM25 (extension/engine/bm25.js)
// against the server's Solr query, on the corpus solr_corpus.py loaded.
//
// Usage (from code/src): node evaluation/parity/bm25_check.mjs <chunks.json> [solr core URL]
// Prints how many queries returned the same top 50, in the same order, with
// scores equal to Solr's (to 1e-5), and the first differences.
import fs from "fs";
import { Bm25Index, searchBm25 } from "../../extension/engine/bm25.js";

const [, , chunksPath, solr = "http://localhost:8984/solr/parity"] = process.argv;
const chunks = JSON.parse(fs.readFileSync(chunksPath, "utf8"));
const byId = new Map(chunks.map((c) => [c.id, c]));
const index = new Bm25Index();
const t0 = performance.now();
for (const c of chunks) index.add(c.id, c.title, c.text);
console.log(`indexed ${chunks.length} chunks in ${(performance.now() - t0).toFixed(0)} ms`);
const textOf = (doc, field) => byId.get(doc)[field];

const claims = JSON.parse(fs.readFileSync("evaluation/scifact_data/queries.json", "utf8")).map((q) => q.text);
const extra = [
    "pancakes", "TV", "4K television storage", "gene expression in mice", "\"stem cell\" loss",
    "cancer -mice", "+insulin resistance", "obesity AND diabetes", "vitamin D OR calcium", "immun*",
    "the of and", "DNA damage response", "p53 mutations", "what (is) this?", "COVID-19 vaccine",
    "children's health", "β-cell function", "NOT smoking lung", "malaria \"drug resistance\" africa",
];
let same = 0;
let total = 0;
let ms = 0;
const shown = [];
for (const q of claims.concat(extra)) {
    const params = new URLSearchParams({
        q: q, defType: "edismax", qf: "title^2 text", pf: "text^2 title^3", uf: "-*",
        fq: "{!term f=user_id}parity-user", fl: "id,score", rows: "50", wt: "json",
    });
    const res = await fetch(`${solr}/select`, { method: "POST", body: params });
    if (!res.ok) {
        console.log(`Solr refused (${res.status}): ${q}`);
        continue;
    }
    const solrDocs = (await res.json()).response.docs;
    const s0 = performance.now();
    const mine = searchBm25(index, q, { rows: 50, textOf });
    ms += performance.now() - s0;
    total++;
    const ok = solrDocs.length === mine.length && solrDocs.every((d, i) =>
        d.id === mine[i].doc && Math.abs(d.score - mine[i].score) < 1e-5);
    if (ok) same++;
    else if (shown.length < 6) {
        const i = solrDocs.findIndex((d, k) => !mine[k] || d.id !== mine[k].doc || Math.abs(d.score - mine[k].score) >= 1e-5);
        shown.push(`${q}\n   at ${i}: solr ${solrDocs[i] && `${solrDocs[i].id} ${solrDocs[i].score}`} | mine ${mine[i] && `${mine[i].doc} ${mine[i].score}`} (lengths ${solrDocs.length}/${mine.length})`);
    }
}
console.log(`${same}/${total} queries identical (ids, order, scores); mean ${(ms / total).toFixed(1)} ms per query`);
for (const s of shown) console.log(" -", s);
