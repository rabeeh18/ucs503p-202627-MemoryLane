// Service worker: sign-in, saving (on this device or the server, see local.js),
// auto-capture, excluded sites, and the messages the popup, the options page
// and the MemoryLane website send.
import { COGNITO_DOMAIN, WEB_APP_URL } from "./config.js";
import { getSession, signIn, signOut } from "./auth.js";
import { ApiError, apiFetch } from "./api.js";
import {
    assessContent, isAutoCaptureEligible, isExcluded, isSaveableUrl, normalizeHost, sameDocument,
} from "./page_filter.js";
import { fetchYouTubeVideo, youtubeVideoId } from "./youtube.js";
import {
    autoBackup, backupNow, checkOverflow, closeIfIdle, engine, forgetIdentity, isLocal, libraryId,
    moveAllToDevice, moveAllToServer, restoreBackup, saveLocal, storageSettings, STORAGE_DEFAULTS,
} from "./local.js";
import { newRecoveryKey, normalizeRecoveryKey } from "./engine/crypto.js";

const RECENT_CAPTURE_MS = 60 * 1000;
// Auto-saves the popup lists under "Auto-saved today".
const AUTO_SAVES_KEPT = 20;
const AUTO_SAVES_SHOWN_MS = 24 * 60 * 60 * 1000;
const MIN_AUTO_TEXT_CHARS = 200;
const OWN_HOSTS = [normalizeHost(WEB_APP_URL), normalizeHost(COGNITO_DOMAIN)];

const inFlightUrls = new Set();
const recentlyCaptured = new Map(); // url -> time of last auto-capture
const capturedTabUrls = new Map(); // tabId -> url, to ignore repeated "complete" events

const SETTINGS_DEFAULTS = {
    autoCapture: false,
    autoCaptureConfirmed: false,
    excludedSites: [],
    lastAutoSave: null,
    autoSaves: [],
};

async function getSettings() {
    return chrome.storage.local.get(SETTINGS_DEFAULTS);
}

function errorMessage(err) {
    if (err instanceof ApiError) {
        if (err.status === 429) return "Saving too fast. Try again in a moment.";
        if (err.status === 0) return err.message;
        // The server's own explanation: not enough text, page limit reached, not a web page.
        const explained = err.message && err.message !== "Request failed";
        if ([400, 403, 422].includes(err.status) && explained) return err.message;
        if (err.status === 422) return "This page couldn't be saved. Its address or content may be too long.";
    }
    return "Couldn't save this page. Try again.";
}

const MAX_TITLE_CHARS = 2000;

/** The tab's canonical URL (see canonical.js), or null. */
async function tabCanonical(tabId) {
    try {
        const [injection] = await chrome.scripting.executeScript({ target: { tabId }, files: ["canonical.js"] });
        return (injection && injection.result) || null;
    } catch (_err) {
        return null; // pages extensions can't script
    }
}

function isOwnSite(url) {
    return OWN_HOSTS.some((host) => host && isExcluded(url, [host]));
}

/**
 * A video's transcript and details for the API, or null if YouTube gave nothing usable.
 * Runs inside the YouTube tab: YouTube's player API refuses the extension's own origin.
 */
async function youtubeDetails(tabId, videoId) {
    let video;
    try {
        const [injection] = await chrome.scripting.executeScript({
            target: { tabId },
            func: fetchYouTubeVideo,
            args: [videoId],
        });
        video = injection && injection.result;
    } catch (err) {
        console.info(`MemoryLane: couldn't read YouTube video ${videoId}: ${err?.message || err}`);
        return null;
    }
    if (!video) return null;
    if (video.error) console.info(`MemoryLane: YouTube ${videoId}: ${video.error}`);
    const { transcript, language, title, channel, description, duration_seconds } = video;
    if (!transcript && !description && !title) return null;
    return { transcript, language, title, channel, description, duration_seconds };
}

async function extractTabContent(tabId) {
    try {
        const [injection] = await chrome.scripting.executeScript({
            target: { tabId },
            files: ["canonical.js", "content.js"],
        });
        const result = injection && injection.result;
        if (result) {
            return {
                html: result.html || null,
                text: result.text || "",
                canonicalUrl: result.canonicalUrl || null,
                url: result.url || null,
                signals: result.signals || null,
            };
        }
    } catch (_err) {
        // Pages Chrome won't let extensions script; the server may still manage (e.g. YouTube).
    }
    return { html: null, text: "", canonicalUrl: null, url: null, signals: null };
}

/**
 * Save a tab for the signed-in user.
 * @returns {Promise<{ok: true, status: string, message: string, page: object|null} | {ok: false, reason: string, error?: string}>}
 */
async function saveTab(tab, { manual }) {
    if (!(await getSession())) {
        return { ok: false, reason: "signed-out" };
    }
    if (!tab || !tab.id || !isSaveableUrl(tab.url) || isOwnSite(tab.url)) {
        return { ok: false, reason: "unsaveable" };
    }

    const key = tab.url.split("#")[0];
    if (!manual) {
        const last = recentlyCaptured.get(key);
        if (last && Date.now() - last < RECENT_CAPTURE_MS) {
            return { ok: false, reason: "recent" };
        }
    }
    if (inFlightUrls.has(key)) {
        return { ok: false, reason: "in-flight" };
    }

    inFlightUrls.add(key);
    try {
        const videoId = youtubeVideoId(tab.url);
        // YouTube blocks the server, so a video's transcript and details are fetched here.
        const [{ html, text, canonicalUrl, url: documentUrl, signals }, youtube] = await Promise.all([
            extractTabContent(tab.id),
            videoId ? youtubeDetails(tab.id, videoId) : null,
        ]);
        // The tab moved on while we were reading it: the text belongs to a different
        // page than tab.url (and that page may be excluded), so send nothing.
        if (documentUrl && !sameDocument(documentUrl, tab.url)) {
            return { ok: false, reason: "navigated", error: "The page changed while it was being saved. Try again." };
        }
        if (!manual && !youtube && text.length < MIN_AUTO_TEXT_CHARS && !html) {
            return { ok: false, reason: "low-content" };
        }
        // Automatic capture keeps only pages that read like content (page_filter.js).
        if (!manual && !youtube) {
            const verdict = assessContent(signals);
            if (!verdict.ok) {
                console.info(`MemoryLane: not auto-saving ${tab.url}: ${verdict.reason}`);
                return { ok: false, reason: "not-content", error: verdict.reason };
            }
        }
        const body = {
            url: tab.url,
            title: (tab.title || tab.url).slice(0, MAX_TITLE_CHARS),
            content: text,
            // The server reads a video from `youtube`, not from the page, so skip the (large) HTML.
            html: youtube ? null : html,
            canonical_url: canonicalUrl,
            is_manual: manual,
        };
        if (youtube) body.youtube = youtube;
        const { storageMode } = await storageSettings();
        const data = storageMode === "device"
            ? await saveLocal(body)
            : await apiFetch("/memory", { method: "POST", body });
        if (!manual) recentlyCaptured.set(key, Date.now());
        if (data.status === "skipped") {
            return { ok: false, reason: "skipped", error: data.message };
        }
        return { ok: true, status: data.status, message: data.message, page: data.page };
    } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
            return { ok: false, reason: "signed-out" };
        }
        return { ok: false, reason: "error", error: errorMessage(err) };
    } finally {
        inFlightUrls.delete(key);
    }
}

async function activeTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab || null;
}

/** Everything the popup needs to pick its state. */
async function popupState() {
    const [session, settings, tab] = await Promise.all([getSession(), getSettings(), activeTab()]);
    const state = {
        signedIn: Boolean(session),
        email: session ? session.email : "",
        autoCapture: settings.autoCapture,
        autoCaptureConfirmed: settings.autoCaptureConfirmed,
        lastAutoSave: settings.lastAutoSave,
        autoSaves: (settings.autoSaves || []).filter((s) => Date.now() - s.at < AUTO_SAVES_SHOWN_MS),
        tab: tab ? { title: tab.title || "", url: tab.url || "", domain: normalizeHost(tab.url) } : null,
        host: tab ? normalizeHost(tab.url) : "",
        saveable: Boolean(tab && isSaveableUrl(tab.url) && !isOwnSite(tab.url)),
        excluded: Boolean(tab && isExcluded(tab.url, settings.excludedSites)),
        status: null,
        statusError: "",
        storageMode: (await storageSettings()).storageMode,
        overflowPrompt: (await storageSettings()).overflowPrompt,
    };
    if (!state.signedIn) {
        return state;
    }
    // Checked alongside the page's status, so the popup waits for one round trip.
    const autoSavesChecked = stillSaved(state.autoSaves).then((list) => { state.autoSaves = list; });
    if (!state.saveable) {
        await autoSavesChecked;
        return state;
    }
    try {
        // Pages are saved under their canonical URL, so check with it too.
        const params = new URLSearchParams({ url: tab.url });
        const canonical = await tabCanonical(tab.id);
        if (canonical) params.set("canonical_url", canonical);
        state.status = await pageStatus(tab.url, canonical, params);
    } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
            state.signedIn = false;
        } else {
            state.statusError = err instanceof ApiError && err.status === 0
                ? err.message
                : "Couldn't check this page. Try again.";
        }
    }
    await autoSavesChecked; // stillSaved never throws
    return state;
}

/** Saved on this device, or else on the server? (A page is stored whole in one place.) */
async function pageStatus(url, canonical, params) {
    let local = null;
    try {
        local = await engine("STATUS", { url, canonical_url: canonical });
    } catch (_err) {
        local = null; // the local store can't open (offline at first sign-in): the server still answers
    }
    if (local && local.saved) return { ...local, location: "device" };
    const remote = await apiFetch(`/memory/status?${params}`);
    return remote.saved ? { ...remote, location: "server" } : remote;
}

/** Delete one page wherever it is. 404 when it is in neither place. */
async function deletePage(id) {
    if (await isLocal(id)) {
        await engine("DELETE", { id });
        return;
    }
    await apiFetch(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
}

async function setSiteExcluded(host, excluded) {
    const site = normalizeHost(host);
    if (!site) return getSettings();
    const { excludedSites } = await getSettings();
    const next = excluded
        ? [...new Set([...excludedSites, site])].sort()
        : excludedSites.filter((s) => s !== site);
    await chrome.storage.local.set({ excludedSites: next });
    return getSettings();
}

// ---- auto-capture -------------------------------------------------------------

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === "loading") {
        // A reload or a new page: allow another capture (RECENT_CAPTURE_MS still
        // stops the same URL being sent twice within a minute).
        capturedTabUrls.delete(tabId);
        return;
    }
    if (changeInfo.status !== "complete" || !tab || !tab.url) {
        return;
    }
    if (capturedTabUrls.get(tabId) === tab.url) {
        return;
    }
    (async () => {
        const settings = await getSettings();
        if (!settings.autoCapture || !(await getSession())) {
            return;
        }
        if (!isAutoCaptureEligible(tab.url) || isExcluded(tab.url, settings.excludedSites) || isOwnSite(tab.url)) {
            return;
        }
        // Don't save yet: engagement.js reports back once the page has been read
        // (30 s in view, or scrolled through), so pages you bounce off aren't kept.
        capturedTabUrls.set(tabId, tab.url); // ignore repeated "complete" events
        try {
            await chrome.scripting.executeScript({ target: { tabId }, files: ["engagement.js"] });
        } catch (_err) {
            capturedTabUrls.delete(tabId); // pages extensions can't script
        }
    })().catch((err) => console.warn("Auto-capture failed:", err));
});

/** engagement.js says this tab's page has been read: save it if it still qualifies. */
async function autoCaptureEngaged(tab, url) {
    if (!tab || !tab.id || !tab.url || !sameDocument(url, tab.url)) return;
    const settings = await getSettings();
    if (!settings.autoCapture || !(await getSession())) return;
    if (!isAutoCaptureEligible(tab.url) || isExcluded(tab.url, settings.excludedSites) || isOwnSite(tab.url)) return;
    const result = await saveTab(tab, { manual: false });
    if (result.ok && result.status === "saved" && result.page) {
        await rememberAutoSave(result.page, tab);
    }
}

/** Newest first, the last day's auto-saves, for the popup's "Auto-saved today". */
async function rememberAutoSave(page, tab) {
    const { autoSaves = [] } = await chrome.storage.local.get({ autoSaves: [] });
    const entry = { id: page.id, title: page.title || tab.title || tab.url, url: tab.url, at: Date.now() };
    const next = [entry, ...autoSaves.filter((s) => s.id !== page.id)]
        .filter((s) => Date.now() - s.at < AUTO_SAVES_SHOWN_MS)
        .slice(0, AUTO_SAVES_KEPT);
    await chrome.storage.local.set({ autoSaves: next, lastAutoSave: { title: entry.title, url: entry.url, at: entry.at } });
}

/**
 * The list lives only in the extension, so it doesn't hear about pages deleted
 * on the website: ask the server which are still saved and forget the rest.
 * If the server can't be reached, show the list as it is.
 */
async function stillSaved(entries) {
    if (!entries.length) return entries;
    try {
        const all = entries.map((s) => s.id);
        let local = [];
        try {
            local = await engine("EXISTING", { ids: all });
        } catch (_err) {
            local = [];
        }
        const rest = all.filter((id) => !local.includes(id));
        const { ids } = rest.length
            ? await apiFetch("/memory/existing", { method: "POST", body: { ids: rest } })
            : { ids: [] };
        const kept = new Set([...local, ...ids]);
        const gone = entries.filter((s) => !kept.has(s.id)).map((s) => s.id);
        if (gone.length) {
            const { autoSaves = [] } = await chrome.storage.local.get({ autoSaves: [] });
            await chrome.storage.local.set({ autoSaves: autoSaves.filter((s) => !gone.includes(s.id)) });
        }
        return entries.filter((s) => kept.has(s.id));
    } catch (_err) {
        return entries;
    }
}

async function forgetAutoSave(id) {
    const { autoSaves = [] } = await chrome.storage.local.get({ autoSaves: [] });
    await chrome.storage.local.set({ autoSaves: autoSaves.filter((s) => s.id !== id) });
}

chrome.tabs.onRemoved.addListener((tabId) => {
    capturedTabUrls.delete(tabId);
});

// ---- keyboard shortcut ----------------------------------------------------------

chrome.commands.onCommand.addListener((command) => {
    if (command === "open-search") {
        chrome.tabs.create({ url: WEB_APP_URL });
    }
});

// ---- messages ----------------------------------------------------------------

const handlers = {
    async GET_POPUP_STATE() {
        return popupState();
    },
    async SIGN_IN({ provider }) {
        try {
            await signIn(provider || undefined);
            return { ok: true };
        } catch (err) {
            const cancelled = /did not approve|cancel|closed/i.test(String(err && err.message));
            return { ok: false, error: cancelled ? "" : "Sign-in didn't complete. Try again." };
        }
    },
    async SIGN_OUT() {
        await forgetIdentity(); // the device key goes: local pages are unreadable until sign-in
        await signOut();
        return { ok: true };
    },
    async SAVE_CURRENT_PAGE() {
        return saveTab(await activeTab(), { manual: true });
    },
    async UNDO_SAVE({ id }) {
        try {
            await deletePage(id);
            await forgetAutoSave(id);
            return { ok: true };
        } catch (err) {
            if (err instanceof ApiError && err.status === 401) return { ok: false, reason: "signed-out" };
            // Already deleted (e.g. from the website): that's what was asked for.
            if (err instanceof ApiError && err.status === 404) return { ok: true };
            return { ok: false, error: "Couldn't remove the page. Try again." };
        }
    },
    async SET_AUTO_CAPTURE({ enabled }) {
        const update = { autoCapture: Boolean(enabled) };
        if (enabled) update.autoCaptureConfirmed = true;
        await chrome.storage.local.set(update);
        return { ok: true };
    },
    /** "Auto-saved today": remove a page, and optionally never auto-save its site again. */
    async REMOVE_AUTO_SAVE({ id, url, excludeSite }) {
        if (excludeSite && url) await setSiteExcluded(url, true);
        try {
            await deletePage(id);
        } catch (err) {
            if (err instanceof ApiError && err.status === 401) return { ok: false, reason: "signed-out" };
            if (!(err instanceof ApiError && err.status === 404)) {
                return { ok: false, error: "Couldn't remove the page. Try again." };
            }
        }
        await forgetAutoSave(id);
        return { ok: true };
    },
    async SET_SITE_EXCLUDED({ host, excluded }) {
        const settings = await setSiteExcluded(host, excluded);
        return { ok: true, excludedSites: settings.excludedSites };
    },

    // ---- storage on this device (popup and options page) ----
    /** The popup's answer to "move older pages to the server?". */
    async OVERFLOW_ANSWER({ allow }) {
        await chrome.storage.local.set({ overflow: allow ? "on" : "off", overflowPrompt: false });
        return wrap(allow ? checkOverflow() : Promise.resolve({ moved: 0 }));
    },
    async GET_STORAGE_STATE() {
        const settings = await storageSettings();
        const state = {
            ok: true, signedIn: Boolean(await getSession()),
            storageMode: settings.storageMode, deviceLimitMb: settings.deviceLimitMb, overflow: settings.overflow,
            autoBackup: settings.autoBackup, lastBackup: settings.lastBackup, device: null, server: null, backup: null,
        };
        if (!state.signedIn) return state;
        await Promise.all([
            engine("STATS").then((s) => { state.device = s; }).catch(() => {}),
            apiFetch("/memories?limit=1&offset=0").then((r) => { state.server = { pages: r.total }; }).catch(() => {}),
            apiFetch("/backup/info").then((b) => { state.backup = b; }).catch(() => {}),
        ]);
        return state;
    },
    async SET_STORAGE({ storageMode, deviceLimitMb, overflow }) {
        const update = {};
        if (storageMode === "device" || storageMode === "server") update.storageMode = storageMode;
        if (Number.isFinite(deviceLimitMb) && deviceLimitMb >= 10 && deviceLimitMb <= 10000) update.deviceLimitMb = Math.round(deviceLimitMb);
        if (["ask", "on", "off"].includes(overflow)) update.overflow = overflow;
        await chrome.storage.local.set(update);
        if (update.deviceLimitMb || update.overflow === "on") checkOverflow().catch(() => {});
        return { ok: true };
    },
    async MOVE_ALL_TO_SERVER() { return wrap(moveAllToServer()); },
    async MOVE_ALL_TO_DEVICE() { return wrap(moveAllToDevice()); },
    /** A new recovery key, to show the user once. Kept only if automatic backups are on. */
    async NEW_RECOVERY_KEY() { return { ok: true, recoveryKey: newRecoveryKey() }; },
    async SET_AUTO_BACKUP({ enabled, recoveryKey }) {
        const key = recoveryKey ? normalizeRecoveryKey(recoveryKey) : null;
        if (enabled && !key) return { ok: false, error: "That isn't a valid recovery key." };
        await chrome.storage.local.set({ autoBackup: Boolean(enabled), recoveryKey: enabled ? key : null });
        return { ok: true };
    },
    async BACKUP_NOW({ recoveryKey }) {
        const key = recoveryKey || (await storageSettings()).recoveryKey;
        return wrap(backupNow(key));
    },
    async RESTORE_BACKUP({ recoveryKey }) { return wrap(restoreBackup(recoveryKey)); },
    async DELETE_BACKUP() { return wrap(apiFetch("/backup", { method: "DELETE" }).then(() => ({}))); },
};

/** A long-running storage action as {ok, ...result} or {ok: false, error}. */
async function wrap(promise) {
    try {
        return { ok: true, ...(await promise) };
    } catch (err) {
        if (err instanceof ApiError && err.status === 401) return { ok: false, reason: "signed-out" };
        return { ok: false, error: (err && err.message) || "Something went wrong. Try again." };
    }
}

// ---- timers -------------------------------------------------------------------

chrome.alarms.create("engine-idle", { periodInMinutes: 5 });
chrome.alarms.create("auto-backup", { periodInMinutes: 60 });
chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "engine-idle") closeIfIdle().catch(() => {});
    if (alarm.name === "auto-backup") autoBackup().catch((err) => console.warn("Automatic backup failed:", err));
});

chrome.runtime.onInstalled.addListener(async () => {
    // New settings get their defaults; existing choices stay.
    const current = await chrome.storage.local.get(Object.keys(STORAGE_DEFAULTS));
    const missing = Object.fromEntries(Object.entries(STORAGE_DEFAULTS).filter(([k]) => !(k in current)));
    if (Object.keys(missing).length) await chrome.storage.local.set(missing);
});

// ---- the MemoryLane website ------------------------------------------------------
//
// memorylane.site asks the extension about the pages kept on this device
// (externally_connectable lets only that site connect). Each request names the
// library the website is signed in to; the extension answers only for its own,
// so two different accounts in one browser never see each other's pages.

const SITE_ORIGIN = new URL(WEB_APP_URL).origin;

async function forThisLibrary(message, fn) {
    if (!(await getSession())) return { ok: false, reason: "signed-out" };
    if (message.library_id !== (await libraryId())) return { ok: false, reason: "other-account" };
    return wrap(fn());
}

const siteHandlers = {
    async HELLO() {
        const settings = await storageSettings();
        return { ok: true, version: chrome.runtime.getManifest().version, storageMode: settings.storageMode };
    },
    SEARCH: (m) => forThisLibrary(m, async () => engine("SEARCH", { query: String(m.query || "").slice(0, 500), num_results: Math.min(20, Number(m.num_results) || 10) })),
    LIST: (m) => forThisLibrary(m, async () => engine("LIST", { limit: Math.min(100, Number(m.limit) || 20), offset: Math.max(0, Number(m.offset) || 0) })),
    PAGE_TEXT: (m) => forThisLibrary(m, async () => ({ page: await engine("PAGE_TEXT", { id: String(m.id || "") }) })),
    DELETE: (m) => forThisLibrary(m, async () => ({ deleted: await engine("DELETE", { id: String(m.id || "") }) })),
    DELETE_ALL: (m) => forThisLibrary(m, async () => {
        await engine("FORGET_DEVICE_DATA", { library_id: m.library_id });
        await forgetIdentity();
        return {};
    }),
};

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
    if (sender.origin !== SITE_ORIGIN || !message || !siteHandlers[message.type]) return false;
    siteHandlers[message.type](message)
        .then(sendResponse)
        .catch((err) => sendResponse({ ok: false, error: String((err && err.message) || err) }));
    return true;
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // From engagement.js, running in a page's top frame: that page has been read.
    if (message && message.type === "PAGE_ENGAGED") {
        if (sender.id === chrome.runtime.id && sender.tab && sender.frameId === 0) {
            autoCaptureEngaged(sender.tab, String(message.url || ""))
                .catch((err) => console.warn("Auto-capture failed:", err));
        }
        return false;
    }
    // Only this extension's own pages may drive it.
    if (sender.id !== chrome.runtime.id || !message || !handlers[message.type]) {
        return false;
    }
    handlers[message.type](message)
        .then(sendResponse)
        .catch((err) => sendResponse({ ok: false, error: String((err && err.message) || err) }));
    return true;
});
