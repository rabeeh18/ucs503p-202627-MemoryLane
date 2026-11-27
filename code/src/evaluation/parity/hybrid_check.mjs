// End-to-end parity: the browser engine's hybrid search (extension/engine)
// against what the server returned (server_results.py) for the same pages and
// queries. The browser side embeds with transformers.js, as the extension does.
//
// Usage (from code/src, after `npm install` in extension/):
//   node evaluation/parity/hybrid_check.mjs <chunks.json> <server.json>
import fs from "fs";
import { createRequire } from "module";
import { pathToFileURL } from "url";
import { LocalIndex } from "../../extension/engine/local_index.js";
import { hybridSearch } from "../../extension/engine/retrieval.js";

const require = createRequire(import.meta.url);
const transformers = await import(pathToFileURL(require.resolve("@huggingface/transformers", { paths: ["extension"] })).href);
const { pipeline, env } = transformers.pipeline ? transformers : transformers.default;
env.cacheDir = process.env.HF_CACHE || "extension/node_modules/.hf-cache";

const [, , chunksPath, serverPath] = process.argv;
const chunks = JSON.parse(fs.readFileSync(chunksPath, "utf8"));
const server = JSON.parse(fs.readFileSync(serverPath, "utf8"));
const now = Date.parse(server.now);

const full = new Map();
const index = new LocalIndex(async (ids) => new Map(ids.map((id) => [id, full.get(id)])));
const byPage = new Map();
for (const c of chunks) {
    full.set(c.id, Float32Array.from(c.embedding));
    if (!byPage.has(c.page_id)) byPage.set(c.page_id, []);
    byPage.get(c.page_id).push(c);
}
let t0 = performance.now();
for (const [pageId, list] of byPage) index.putPage(pageId, list);
console.log(`indexed ${byPage.size} pages in ${(performance.now() - t0).toFixed(0)} ms`);

const extractor = await pipeline("feature-extraction", "Xenova/bge-small-en-v1.5", { dtype: "fp32" });
const PREFIX = "Represent this sentence for searching relevant passages: ";
const embed = async (texts) => (await extractor(texts, { pooling: "cls", normalize: true })).tolist();
const embedQuery = async (q) => (await embed([PREFIX + q]))[0];

let sameOrder = 0;
let sameSnippets = 0;
let n = 0;
let ms = 0;
const diffs = [];
for (const [q, expected] of Object.entries(server.results)) {
    t0 = performance.now();
    const mine = await hybridSearch(q, index, {
        userId: "parity-user", embedQuery, embedPassages: embed, topK: server.top_k, now,
    });
    ms += performance.now() - t0;
    n++;
    const a = expected.map((r) => r.page_id).join(",");
    const b = mine.map((r) => r.page_id).join(",");
    if (a === b) sameOrder++;
    else diffs.push(`${q}\n   server: ${a}\n   local:  ${b}`);
    if (a === b && expected.every((r, i) => r.snippet === mine[i].snippet)) sameSnippets++;
    else if (a === b) diffs.push(`${q} (snippet differs)\n   server: ${expected.find((r, i) => r.snippet !== mine[i].snippet)?.snippet}\n   local:  ${mine.find((r, i) => r.snippet !== expected[i].snippet)?.snippet}`);
}
console.log(`${sameOrder}/${n} queries: same pages in the same order; ${sameSnippets}/${n} also same snippets; mean ${(ms / n).toFixed(0)} ms per search`);
for (const d of diffs.slice(0, 8)) console.log(" -", d);
