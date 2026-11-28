// Local-first storage, from the service worker's side: where a save goes, the
// engine that keeps pages on this device (engine.html, an offscreen document),
// moving pages between the device and the server, and encrypted backups.
//
// Pages are stored on this device by default. When the pages here pass the
// size limit (Options), the oldest move to the server, once the user has agreed;
// a page always lives whole in one place. Searches cover both places.
import { ApiError, apiFetch, publicFetch } from "./api.js";
import { getSession } from "./auth.js";
import { backupKey, decrypt, encrypt, gunzip, gzip, normalizeRecoveryKey } from "./engine/crypto.js";

const MB = 1024 * 1024;
export const STORAGE_DEFAULTS = {
    storageMode: "device", // "device" | "server": where new pages are saved
    deviceLimitMb: 100, // pages here beyond this move to the server (with consent)
    overflow: "ask", // "ask" | "on" | "off"
    overflowPrompt: false, // the popup should ask about moving pages
    autoBackup: false,
    recoveryKey: null, // kept only when automatic backups are on
    lastBackup: null,
};
const SETTINGS_TTL_MS = 6 * 60 * 60 * 1000;
const ENGINE_IDLE_MS = 10 * 60 * 1000;
const OVERFLOW_TARGET = 0.9; // move pages until the device is at 90% of its limit

export async function storageSettings() {
    return chrome.storage.local.get(STORAGE_DEFAULTS);
}

// ---- identity: the library id and the device key, held for this browser session ----

async function identity() {
    const { identity: cached } = await chrome.storage.session.get("identity");
    const session = await getSession();
    if (!session) throw new ApiError("signed-out", 401);
    if (cached && cached.email === session.email) return cached;
    const me = await apiFetch("/me");
    const value = { library_id: me.library_id, device_key: me.device_key, email: session.email };
    await chrome.storage.session.set({ identity: value });
    return value;
}

export async function forgetIdentity() {
    await chrome.storage.session.remove("identity");
    await closeEngine();
}

export async function libraryId() {
    return (await identity()).library_id;
}

/** The server's search settings, refreshed every few hours (local search must use the same). */
async function searchSettings() {
    const { searchSettings: cached } = await chrome.storage.local.get("searchSettings");
    if (cached && Date.now() - cached.at < SETTINGS_TTL_MS) return cached.values;
    try {
        const values = await publicFetch("/search-settings");
        await chrome.storage.local.set({ searchSettings: { at: Date.now(), values } });
        return values;
    } catch (_err) {
        return cached ? cached.values : null; // offline: last known, else the built-in defaults
    }
}

// ---- the engine (offscreen document) ------------------------------------------------

let opening = null;
let lastUse = 0;

async function ensureDocument() {
    const existing = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
    if (existing.length) return;
    try {
        await chrome.offscreen.createDocument({
            url: "engine.html",
            reasons: ["WORKERS"],
            justification: "Runs the local search engine for pages saved on this device.",
        });
    } catch (err) {
        if (!/single offscreen/i.test(String(err && err.message))) throw err;
    }
}

function post(type, payload = {}) {
    return chrome.runtime.sendMessage({ target: "engine", type, ...payload }).then((reply) => {
        if (!reply) throw new ApiError("The local store didn't answer", 500);
        if (!reply.ok) throw new ApiError(reply.detail || "Local store error", reply.status || 500);
        return reply.result;
    });
}

async function openEngine() {
    const [id, settings] = await Promise.all([identity(), searchSettings()]);
    await ensureDocument();
    return post("OPEN", { library_id: id.library_id, device_key: id.device_key, settings });
}

/** Send work to the local engine, opening it for the signed-in account first. */
export async function engine(type, payload = {}) {
    lastUse = Date.now();
    opening ||= openEngine().finally(() => { opening = null; });
    await opening;
    try {
        return await post(type, payload);
    } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
            // The document was closed meanwhile: open again once.
            await openEngine();
            return post(type, payload);
        }
        throw err;
    }
}

export async function closeEngine() {
    const existing = await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"] });
    if (existing.length) await chrome.offscreen.closeDocument();
}

/** Called by an alarm: close the engine (freeing the model and Pyodide) after a quiet spell. */
export async function closeIfIdle() {
    if (lastUse && Date.now() - lastUse > ENGINE_IDLE_MS) {
        lastUse = 0;
        await closeEngine();
    }
}

// ---- where pages are -------------------------------------------------------------------

/** Whether this page id is stored on this device. */
export async function isLocal(id) {
    try {
        return (await engine("EXISTING", { ids: [id] })).includes(id);
    } catch (_err) {
        return false;
    }
}

/** Save a page on this device (same body and answer as POST /memory). */
export async function saveLocal(body) {
    try {
        const result = await engine("SAVE", { body });
        if (result.status === "saved") checkOverflow().catch((err) => console.warn("Overflow check failed:", err));
        return result;
    } catch (err) {
        if (err instanceof ApiError) throw err;
        throw new ApiError(err.detail || "Couldn't save this page", err.status || 500);
    }
}

// ---- overflow to the server -----------------------------------------------------------

export async function checkOverflow() {
    const settings = await storageSettings();
    const { bytes } = await engine("STATS");
    const limit = settings.deviceLimitMb * MB;
    if (bytes <= limit) {
        if (settings.overflowPrompt) await chrome.storage.local.set({ overflowPrompt: false });
        return { moved: 0 };
    }
    if (settings.overflow === "on") return moveOldestToServer(limit * OVERFLOW_TARGET);
    if (settings.overflow === "ask") await chrome.storage.local.set({ overflowPrompt: true });
    return { moved: 0 };
}

/** Move one page from this device to the server: stored there exactly as here, then removed here. */
export async function moveToServer(id) {
    const page = await engine("EXPORT_PAGE", { id });
    if (!page) return false;
    await apiFetch("/memory/transfer", { method: "POST", body: page });
    await engine("DELETE", { id });
    return true;
}

/** Oldest first, until the pages here take at most `targetBytes`. */
export async function moveOldestToServer(targetBytes) {
    const pages = await engine("OLDEST");
    let { bytes } = await engine("STATS");
    let moved = 0;
    for (const page of pages) {
        if (bytes <= targetBytes) break;
        await moveToServer(page.id);
        bytes -= page.bytes;
        moved++;
    }
    await chrome.storage.local.set({ overflowPrompt: false });
    return { moved };
}

/** Move every page here to the server (Options: "Move pages to the server"). */
export async function moveAllToServer(onProgress) {
    const pages = await engine("OLDEST");
    let moved = 0;
    for (const page of pages) {
        await moveToServer(page.id);
        onProgress && onProgress(++moved, pages.length);
    }
    return { moved };
}

/** Bring every server page to this device (Options: "Keep my pages on this device"). */
export async function moveAllToDevice(onProgress) {
    const ids = [];
    for (let offset = 0; ; offset += 100) {
        const { pages, total } = await apiFetch(`/memories?limit=100&offset=${offset}`);
        ids.push(...pages.map((p) => p.id));
        if (offset + 100 >= total) break;
    }
    let moved = 0;
    for (const id of ids) {
        const page = await apiFetch(`/memory/${encodeURIComponent(id)}/content`);
        await engine("IMPORT_PAGE", { page });
        await apiFetch(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
        onProgress && onProgress(++moved, ids.length);
    }
    return { moved };
}

// ---- encrypted backups ------------------------------------------------------------------

/** Back up this device's pages, encrypted with the recovery key (the server can't read it). */
export async function backupNow(recoveryKey) {
    const key = normalizeRecoveryKey(recoveryKey);
    if (!key) throw new ApiError("That isn't a valid recovery key", 400);
    const pages = await engine("EXPORT_ALL");
    const plain = new TextEncoder().encode(JSON.stringify({ version: 1, pages }));
    const sealed = await encrypt(await backupKey(key, await libraryId()), await gzip(plain));
    const info = await apiFetch("/backup", { method: "PUT", body: sealed, bytes: true });
    await chrome.storage.local.set({ lastBackup: { at: Date.now(), pages: pages.length, bytes: info.bytes } });
    return { pages: pages.length, bytes: info.bytes };
}

/** Restore pages from the backup onto this device (pages already here are kept). */
export async function restoreBackup(recoveryKey, onProgress) {
    const key = normalizeRecoveryKey(recoveryKey);
    if (!key) throw new ApiError("That isn't a valid recovery key", 400);
    const sealed = await apiFetch("/backup", { binary: true });
    let data;
    try {
        data = JSON.parse(new TextDecoder().decode(await gunzip(await decrypt(await backupKey(key, await libraryId()), sealed))));
    } catch (_err) {
        throw new ApiError("That recovery key doesn't open this backup", 400);
    }
    let restored = 0;
    for (const page of data.pages || []) {
        await engine("IMPORT_PAGE", { page });
        onProgress && onProgress(++restored, data.pages.length);
    }
    return { restored };
}

/** Called by the daily alarm. */
export async function autoBackup() {
    const settings = await storageSettings();
    if (!settings.autoBackup || !settings.recoveryKey || !(await getSession())) return;
    const day = 24 * 60 * 60 * 1000;
    if (settings.lastBackup && Date.now() - settings.lastBackup.at < day) return;
    await backupNow(settings.recoveryKey);
}
