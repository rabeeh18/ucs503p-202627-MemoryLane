// The whole local engine in Node: save real pages through Pyodide, store them
// encrypted, reopen the store, search, list, move a page out and back, delete.
//
// Usage (from code/src): node evaluation/parity/engine_check.mjs <pages dir>
import assert from "assert";
import fs from "fs";
import path from "path";
import { createRequire } from "module";
import { pathToFileURL } from "url";
import { LocalEngine } from "../../extension/engine/core.js";
import { MemoryStorage } from "../../extension/engine/store.js";
import { importAesKey } from "../../extension/engine/crypto.js";
import { loadIngest } from "../../extension/engine/ingest.js";

const EXT = path.resolve("extension");
const require = createRequire(import.meta.url);
const t = await import(pathToFileURL(require.resolve("@huggingface/transformers", { paths: [EXT] })).href);
const transformers = t.pipeline ? t : t.default;
transformers.env.cacheDir = process.env.HF_CACHE || path.join(EXT, "node_modules/.hf-cache");
const { loadPyodide } = await import(pathToFileURL(path.join(EXT, "node_modules/pyodide/pyodide.mjs")).href);
const files = {
    url: (rel) => path.join(EXT, rel) + (rel.endsWith("/") ? path.sep : ""),
    bytes: async (rel) => new Uint8Array(fs.readFileSync(path.join(EXT, rel))),
    text: async (rel) => fs.readFileSync(path.join(EXT, rel), "utf8"),
};

let extractorPromise = null;
const embedder = async () => {
    extractorPromise ||= transformers.pipeline("feature-extraction", "Xenova/bge-small-en-v1.5", { dtype: "fp32" });
    const extractor = await extractorPromise;
    const embedPassages = async (texts) => (await extractor(texts, { pooling: "cls", normalize: true })).tolist();
    return {
        embedPassages,
        embedQuery: async (q) => (await embedPassages(["Represent this sentence for searching relevant passages: " + q]))[0],
    };
};

const storage = new MemoryStorage();
const key = await importAesKey(crypto.getRandomValues(new Uint8Array(32)));
const deps = { storage, key, libraryId: "lib-test", embedder, ingest: () => loadIngest(files, loadPyodide) };
let engine = new LocalEngine(deps);
await engine.open();

const dir = process.argv[2];
const saved = [];
const inputs = [];
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".html"))) {
    const html = fs.readFileSync(path.join(dir, file), "utf8");
    const url = fs.readFileSync(path.join(dir, file.replace(".html", ".url")), "utf8").trim();
    const title = (html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ""])[1].trim();
    const t0 = performance.now();
    try {
        const body = { url, title, content: html.replace(/<[^>]+>/g, "\n"), html, is_manual: true };
        const r = await engine.save(body);
        inputs.push(body);
        console.log(`${r.status.padEnd(9)} ${(performance.now() - t0).toFixed(0).padStart(5)} ms  ${r.page.chunks} chunks  ${url}`);
        saved.push(r.page);
    } catch (e) {
        console.log(`refused   ${(performance.now() - t0).toFixed(0).padStart(5)} ms  ${e.detail}  ${url}`);
    }
}
const stats = engine.stats();
console.log(`stored ${stats.pages} pages, ${(stats.bytes / 1024).toFixed(0)} KB encrypted`);

const before = await engine.search("how do you make a sourdough starter", 5);
console.log("search:", before.results.map((r) => `${r.rank}. ${r.title.slice(0, 50)}`).join(" | "));
assert.ok(before.results.length > 0 && /sourdough/i.test(before.results[0].title));
const siteSearch = await engine.search("the wikipedia article", 5);
// Site words boost the site's pages (they are not a filter): the top results are Wikipedia's.
assert.equal(siteSearch.results[0].domain, "en.wikipedia.org");

// Saving the same page again with the same content: unchanged.
const again = await engine.save({ ...inputs[0], is_manual: false });
assert.equal(again.status, "unchanged");

// Reopen from the encrypted records: same results.
engine.close();
engine = new LocalEngine(deps);
await engine.open();
const after = await engine.search("how do you make a sourdough starter", 5);
assert.deepEqual(after.results.map((r) => r.id), before.results.map((r) => r.id));
assert.deepEqual(after.results.map((r) => r.snippet), before.results.map((r) => r.snippet));
console.log("reopened from encrypted storage: same results");

// A wrong key reads nothing.
const stranger = new LocalEngine({ ...deps, key: await importAesKey(new Uint8Array(32)) });
assert.equal((await stranger.open()).pages, 0);
console.log("another key: no pages readable");

// Move a page out (as to the server) and back in: identical chunks.
const first = engine.list(1, 0).pages[0];
const exported = engine.exportPage(first.id);
await engine.deletePage(first.id);
assert.equal(engine.existing([first.id]).length, 0);
const back = await engine.importPage(exported);
assert.equal(back.page.id, first.id);
assert.deepEqual(engine.exportPage(first.id), exported);
console.log("moved out and back in: identical");

const status = await engine.status(first.url, null);
assert.equal(status.saved, true);
console.log("status check, list, delete, export/import: ok");
process.exit(0);
