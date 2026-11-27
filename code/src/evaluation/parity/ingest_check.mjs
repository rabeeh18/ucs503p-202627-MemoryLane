// Saving parity: the extension's local saving (Pyodide running the server's
// code, extension/engine/ingest.js) against the server's ingest_page, on the
// cases ingest_reference.py recorded.
//
// Usage (from code/src, after `npm ci && npm run vendor` in extension/):
//   node evaluation/parity/ingest_check.mjs <cases.json>
import fs from "fs";
import path from "path";
import { pathToFileURL } from "url";
import { loadIngest, preparePage } from "../../extension/engine/ingest.js";

const EXT = path.resolve("extension");
const files = {
    url: (rel) => path.join(EXT, rel) + (rel.endsWith("/") ? path.sep : ""),
    bytes: async (rel) => new Uint8Array(fs.readFileSync(path.join(EXT, rel))),
    text: async (rel) => fs.readFileSync(path.join(EXT, rel), "utf8"),
};
const { loadPyodide } = await import(pathToFileURL(path.join(EXT, "node_modules/pyodide/pyodide.mjs")).href);

const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let t0 = performance.now();
const engine = await loadIngest(files, loadPyodide);
console.log(`Pyodide and the server's saving code loaded in ${(performance.now() - t0).toFixed(0)} ms`);

let same = 0;
for (const { request, expected } of cases) {
    t0 = performance.now();
    const got = await preparePage(engine, request, () => null);
    const ms = (performance.now() - t0).toFixed(0);
    const ok = JSON.stringify(got) === JSON.stringify(expected);
    if (ok) same++;
    const what = expected.docs ? `${expected.docs.length} chunks` : expected.error.detail;
    console.log(`${ok ? "same" : "DIFFERENT"}  ${ms} ms  ${request.url}  (${what})`);
    if (!ok) {
        const a = JSON.stringify(expected);
        const b = JSON.stringify(got);
        let i = 0;
        while (a[i] === b[i]) i++;
        console.log(`   server: …${a.slice(Math.max(0, i - 80), i + 120)}`);
        console.log(`   local:  …${b.slice(Math.max(0, i - 80), i + 120)}`);
    }
}
console.log(`${same}/${cases.length} pages saved identically`);
