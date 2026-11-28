// Runs in the extension's offscreen document (engine.html), which can hold the
// search model, Pyodide and the index in memory across requests; the service
// worker (background.js) sends it work. It only ever talks to this extension.
import { WEB_APP_URL } from "../config.js";
import { LocalEngine } from "./core.js";
import { IdbStorage } from "./store.js";
import { base64urlToBytes, importAesKey } from "./crypto.js";
import { createEmbedder } from "./embedder.js";
import { applyIngestSettings, loadIngest, unloadIngest } from "./ingest.js";
import { applySettings, SETTINGS } from "./settings.js";

const files = {
    url: (rel) => chrome.runtime.getURL(rel),
    bytes: async (rel) => new Uint8Array(await (await fetch(chrome.runtime.getURL(rel))).arrayBuffer()),
    text: async (rel) => (await fetch(chrome.runtime.getURL(rel))).text(),
};

let engine = null; // for the signed-in library
let libraryId = null;
let embedderPromise = null;
let ingestPromise = null;

function embedder() {
    embedderPromise ||= (async () => {
        const transformers = await import(chrome.runtime.getURL("vendor/transformers/transformers.min.js"));
        return createEmbedder(transformers, {
            modelHost: `${WEB_APP_URL}/models/`,
            wasmPath: chrome.runtime.getURL("vendor/ort/"),
        });
    })().catch((err) => {
        embedderPromise = null;
        throw err;
    });
    return embedderPromise;
}

function ingest() {
    ingestPromise ||= (async () => {
        const { loadPyodide } = await import(chrome.runtime.getURL("vendor/pyodide/pyodide.mjs"));
        const loaded = await loadIngest(files, loadPyodide);
        applyIngestSettings(loaded, SETTINGS);
        return loaded;
    })().catch((err) => {
        ingestPromise = null;
        throw err;
    });
    return ingestPromise;
}

/** A database per library, named by a hash so the id itself isn't on disk in the clear. */
async function databaseName(id) {
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`memorylane:${id}`)));
    return "memorylane-" + Array.from(digest.slice(0, 12), (b) => b.toString(16).padStart(2, "0")).join("");
}

function requireEngine() {
    if (!engine) throw Object.assign(new Error("closed"), { status: 409, detail: "The local store isn't open" });
    return engine;
}

const handlers = {
    async OPEN({ library_id: id, device_key: key, settings }) {
        if (settings) applySettings(settings);
        if (engine && libraryId === id) return engine.stats();
        if (engine) engine.close();
        libraryId = id;
        engine = new LocalEngine({
            storage: new IdbStorage(await databaseName(id)),
            key: await importAesKey(base64urlToBytes(key)),
            libraryId: id,
            embedder,
            ingest,
        });
        return engine.open();
    },
    async CLOSE() {
        if (engine) engine.close();
        engine = null;
        libraryId = null;
        return true;
    },
    async FORGET_DEVICE_DATA({ library_id: id }) {
        // Delete this library's local database entirely (after "delete all my data").
        if (engine && libraryId === id) engine.close();
        engine = null;
        libraryId = null;
        await new IdbStorage(await databaseName(id)).destroy();
        return true;
    },
    async STATS() { return requireEngine().stats(); },
    async SAVE({ body }) { return requireEngine().save(body); },
    async IMPORT_PAGE({ page }) { return requireEngine().importPage(page); },
    async EXPORT_PAGE({ id }) { return requireEngine().exportPage(id); },
    async EXPORT_ALL() { return requireEngine().exportAll(); },
    async STATUS({ url, canonical_url }) { return requireEngine().status(url, canonical_url); },
    async EXISTING({ ids }) { return requireEngine().existing(ids); },
    async DELETE({ id }) { return requireEngine().deletePage(id); },
    async DELETE_ALL() { await requireEngine().deleteAll(); return true; },
    async LIST({ limit, offset }) { return requireEngine().list(limit, offset); },
    async OLDEST() { return requireEngine().oldestFirst(); },
    async PAGE_TEXT({ id }) {
        const e = requireEngine();
        const text = e.pageText(id);
        return text === null ? null : { title: e.pageTitle(id), text };
    },
    async SEARCH({ query, num_results }) { return requireEngine().search(query, num_results || 10); },
    async WARM() {
        await Promise.all([embedder(), ingest()]);
        return true;
    },
    async UNLOAD_RUNTIMES() {
        // Free Pyodide and the model when idle; they load again on the next save or search.
        embedderPromise = null;
        ingestPromise = null;
        unloadIngest();
        return true;
    },
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (sender.id !== chrome.runtime.id || !message || message.target !== "engine" || !handlers[message.type]) {
        return false;
    }
    handlers[message.type](message)
        .then((result) => sendResponse({ ok: true, result }))
        .catch((err) => sendResponse({
            ok: false,
            status: err?.status ?? 500,
            detail: err?.detail || String(err?.message || err),
        }));
    return true;
});
