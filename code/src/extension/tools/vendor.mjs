// Put the runtimes local storage needs into extension/vendor/, so the
// extension loads no code from the internet (Manifest V3 forbids it):
//
//   vendor/pyodide/     Pyodide (Python in WebAssembly), the compiled packages it
//                       needs (lxml, regex, ...), and pure-Python wheels
//                       (trafilatura and its dependencies), pinned and hash-checked
//   vendor/py/backend/  the server's own cleaning, chunking and saving code
//   vendor/transformers/, vendor/ort/   transformers.js and its WebAssembly runtime
//
// Usage: cd code/src/extension && npm ci --ignore-scripts && npm run vendor
// The search model's weights are not code: the extension downloads them once
// from the MemoryLane site (https://<domain>/models/), see deploy/caddy/Dockerfile.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const EXT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.resolve(EXT, "..");
const VENDOR = path.join(EXT, "vendor");
const NODE = path.join(EXT, "node_modules");

// Compiled for Pyodide; fetched from Pyodide's release files with their lock-file hashes.
const PYODIDE_PACKAGES = ["lxml", "regex", "python-dateutil", "pytz", "six", "certifi"];
// Pure Python, from PyPI (the versions trafilatura 2.3.1 resolves to on Pyodide).
const PURE_WHEELS = {
    "trafilatura": "2.3.1",
    "lxml-html-clean": "0.4.7",
    "courlan": "1.5.0",
    "htmldate": "1.11.0",
    "justext": "3.0.2",
    "dateparser": "1.5.1",
    "tzlocal": "5.4.5",
    "charset-normalizer": "3.5.3",
    "urllib3": "2.8.0",
};
// The server modules local saving runs (see engine/py/local_ingest.py).
const BACKEND_MODULES = [
    "__init__.py", "config.py", "cleaning.py", "chunking.py", "url_utils.py", "ingest.py",
    "embeddings.py", "solr_client.py", "youtube_utils.py", "page_filter.py",
];

const sha256 = (buf) => crypto.createHash("sha256").update(buf).digest("hex");

async function download(url, expectedSha256) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status} for ${url}`);
    const buf = Buffer.from(await res.arrayBuffer());
    if (expectedSha256 && sha256(buf) !== expectedSha256) throw new Error(`hash mismatch for ${url}`);
    return buf;
}

function copy(from, to) {
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(from, to);
}

async function pyodide() {
    const pkgDir = path.join(NODE, "pyodide");
    const version = JSON.parse(fs.readFileSync(path.join(pkgDir, "package.json"), "utf8")).version;
    const out = path.join(VENDOR, "pyodide");
    for (const file of ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]) {
        copy(path.join(pkgDir, file), path.join(out, file));
    }
    const lock = JSON.parse(fs.readFileSync(path.join(pkgDir, "pyodide-lock.json"), "utf8"));
    const needed = new Set();
    const add = (name) => {
        const key = name.toLowerCase();
        if (needed.has(key)) return;
        const pkg = lock.packages[key];
        if (!pkg) throw new Error(`${name} is not in Pyodide ${version}`);
        needed.add(key);
        for (const dep of pkg.depends || []) add(dep);
    };
    PYODIDE_PACKAGES.forEach(add);
    const base = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
    for (const key of needed) {
        const pkg = lock.packages[key];
        const target = path.join(out, pkg.file_name);
        if (fs.existsSync(target) && sha256(fs.readFileSync(target)) === pkg.sha256) continue;
        fs.writeFileSync(target, await download(base + pkg.file_name, pkg.sha256));
        console.log(`  pyodide package ${pkg.name} ${pkg.version}`);
    }
    const pure = path.join(out, "pure");
    fs.mkdirSync(pure, { recursive: true });
    const wheels = [];
    for (const [name, version] of Object.entries(PURE_WHEELS)) {
        const meta = await (await fetch(`https://pypi.org/pypi/${name}/${version}/json`)).json();
        const wheel = meta.urls.find((u) => u.packagetype === "bdist_wheel" && /-none-any\.whl$/.test(u.filename));
        if (!wheel) throw new Error(`no pure wheel for ${name} ${version}`);
        const target = path.join(pure, wheel.filename);
        if (!(fs.existsSync(target) && sha256(fs.readFileSync(target)) === wheel.digests.sha256)) {
            fs.writeFileSync(target, await download(wheel.url, wheel.digests.sha256));
            console.log(`  wheel ${wheel.filename}`);
        }
        wheels.push(wheel.filename);
    }
    fs.writeFileSync(path.join(out, "packages.json"), JSON.stringify({
        pyodide: [...needed].map((k) => lock.packages[k].name), pure: wheels,
    }, null, 1));
}

function backend() {
    const out = path.join(VENDOR, "py", "backend");
    fs.rmSync(out, { recursive: true, force: true });
    for (const file of BACKEND_MODULES) copy(path.join(SRC, "backend", file), path.join(out, file));
    fs.writeFileSync(path.join(VENDOR, "py", "modules.json"), JSON.stringify(BACKEND_MODULES));
}

function transformers() {
    const dist = path.join(NODE, "@huggingface", "transformers", "dist");
    copy(path.join(dist, "transformers.min.js"), path.join(VENDOR, "transformers", "transformers.min.js"));
    for (const file of fs.readdirSync(dist).filter((f) => /^ort-wasm-simd-threaded\.jsep\.(mjs|wasm)$/.test(f))) {
        copy(path.join(dist, file), path.join(VENDOR, "ort", file));
    }
}

function sizeOf(dir) {
    let total = 0;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, entry.name);
        total += entry.isDirectory() ? sizeOf(p) : fs.statSync(p).size;
    }
    return total;
}

console.log("Vendoring the extension's runtimes into", VENDOR);
await pyodide();
backend();
transformers();
console.log(`Done: vendor/ is ${(sizeOf(VENDOR) / 1e6).toFixed(1)} MB`);
