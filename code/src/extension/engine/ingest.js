// Local saving: the server's Python (backend/ingest.py and the modules it uses)
// run in Pyodide, so a page saved on this device is cleaned and chunked exactly
// as POST /memory would. See py/local_ingest.py.
//
// `files` reads the extension's own files: {url(path), bytes(path), text(path)},
// so the same loader runs in the extension and in Node tests.

let booting = null;

async function boot(files, loadPyodide) {
    const py = await loadPyodide({ indexURL: files.url("vendor/pyodide/"), stdout: () => {}, stderr: () => {} });
    const packages = JSON.parse(await files.text("vendor/pyodide/packages.json"));
    await py.loadPackage(packages.pyodide, { messageCallback: () => {} });
    const sitePackages = py.runPython("import site; site.getsitepackages()[0]");
    for (const wheel of packages.pure) {
        py.unpackArchive(await files.bytes(`vendor/pyodide/pure/${wheel}`), "wheel", { extractDir: sitePackages });
    }
    py.FS.mkdirTree("/memorylane/backend");
    for (const module of JSON.parse(await files.text("vendor/py/modules.json"))) {
        py.FS.writeFile(`/memorylane/backend/${module}`, await files.text(`vendor/py/backend/${module}`));
    }
    py.FS.writeFile("/memorylane/local_ingest.py", await files.text("engine/py/local_ingest.py"));
    py.runPython("import sys; sys.path.insert(0, '/memorylane')");
    return { py, module: py.pyimport("local_ingest") };
}

/** Start Pyodide once (a few seconds); later calls reuse it. */
export function loadIngest(files, loadPyodide) {
    booting ||= boot(files, loadPyodide).catch((err) => {
        booting = null;
        throw err;
    });
    return booting;
}

export function unloadIngest() {
    booting = null;
}

/**
 * Prepare a page the way POST /memory would. `request` is the POST /memory body
 * plus `user_id` (and optionally `chunks`, `content_hash`, `timestamp`,
 * `description` for a page moving in from the server). `lookupHead(pageId)`
 * returns the stored chunk-0 document of that page as JSON, or null.
 * Resolves {result, docs, embed_texts} | {skipped} | {error: {status, detail}}.
 */
export async function preparePage(engine, request, lookupHead) {
    // undefined reaches Python as None (null would arrive as JsNull).
    const out = engine.module.save(JSON.stringify(request), (pageId) => lookupHead(pageId) ?? undefined);
    return JSON.parse(out);
}

/** The id a URL is (or would be) saved under, as GET /memory/status works it out. */
export function pageIdFor(engine, userId, url, canonicalUrl) {
    return engine.module.page_id_for(userId, url, canonicalUrl || null);
}

export function applyIngestSettings(engine, settings) {
    engine.module.apply_settings(JSON.stringify(settings));
}
