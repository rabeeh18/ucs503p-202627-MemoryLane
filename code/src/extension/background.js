// Service worker: sign-in, saving, auto-capture, excluded sites, and the
// messages the popup and options page send.
import { COGNITO_DOMAIN, WEB_APP_URL } from "./config.js";
import { getSession, signIn, signOut } from "./auth.js";
import { ApiError, apiFetch } from "./api.js";
import { isAutoCaptureEligible, isExcluded, isSaveableUrl, normalizeHost } from "./page_filter.js";

const RECENT_CAPTURE_MS = 60 * 1000;
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
};

async function getSettings() {
    return chrome.storage.local.get(SETTINGS_DEFAULTS);
}

function errorMessage(err) {
    if (err instanceof ApiError) {
        if (err.status === 422) return "Not enough readable text on this page";
        if (err.status === 429) return "Saving too fast. Try again in a moment.";
        if (err.status === 0) return err.message;
    }
    return "Couldn't save this page. Try again.";
}

function isOwnSite(url) {
    return OWN_HOSTS.some((host) => host && isExcluded(url, [host]));
}

async function extractTabContent(tabId) {
    try {
        const [injection] = await chrome.scripting.executeScript({
            target: { tabId },
            files: ["content.js"],
        });
        const result = injection && injection.result;
        if (result) {
            return { html: result.html || null, text: result.text || "", canonicalUrl: result.canonicalUrl || null };
        }
    } catch (_err) {
        // Pages Chrome won't let extensions script; the server may still manage (e.g. YouTube).
    }
    return { html: null, text: "", canonicalUrl: null };
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
        const { html, text, canonicalUrl } = await extractTabContent(tab.id);
        if (!manual && text.length < MIN_AUTO_TEXT_CHARS && !html) {
            return { ok: false, reason: "low-content" };
        }
        const data = await apiFetch("/memory", {
            method: "POST",
            body: {
                url: tab.url,
                title: tab.title || tab.url,
                content: text,
                html,
                canonical_url: canonicalUrl,
                is_manual: manual,
            },
        });
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
        tab: tab ? { title: tab.title || "", url: tab.url || "", domain: normalizeHost(tab.url) } : null,
        host: tab ? normalizeHost(tab.url) : "",
        saveable: Boolean(tab && isSaveableUrl(tab.url) && !isOwnSite(tab.url)),
        excluded: Boolean(tab && isExcluded(tab.url, settings.excludedSites)),
        status: null,
        statusError: "",
    };
    if (!state.signedIn || !state.saveable) {
        return state;
    }
    try {
        state.status = await apiFetch(`/memory/status?url=${encodeURIComponent(tab.url)}`);
    } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
            state.signedIn = false;
        } else {
            state.statusError = err instanceof ApiError && err.status === 0
                ? err.message
                : "Couldn't check this page. Try again.";
        }
    }
    return state;
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
        capturedTabUrls.set(tabId, tab.url);
        const result = await saveTab(tab, { manual: false });
        if (result.ok) {
            await chrome.storage.local.set({
                lastAutoSave: { title: tab.title || tab.url, url: tab.url, at: Date.now() },
            });
        }
    })().catch((err) => console.warn("Auto-capture failed:", err));
});

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
        await signOut();
        return { ok: true };
    },
    async SAVE_CURRENT_PAGE() {
        return saveTab(await activeTab(), { manual: true });
    },
    async UNDO_SAVE({ id }) {
        try {
            await apiFetch(`/memory/${encodeURIComponent(id)}`, { method: "DELETE" });
            return { ok: true };
        } catch (err) {
            if (err instanceof ApiError && err.status === 401) return { ok: false, reason: "signed-out" };
            return { ok: false, error: "Couldn't undo. Try again." };
        }
    },
    async SET_AUTO_CAPTURE({ enabled }) {
        const update = { autoCapture: Boolean(enabled) };
        if (enabled) update.autoCaptureConfirmed = true;
        await chrome.storage.local.set(update);
        return { ok: true };
    },
    async SET_SITE_EXCLUDED({ host, excluded }) {
        const settings = await setSiteExcluded(host, excluded);
        return { ok: true, excludedSites: settings.excludedSites };
    },
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Only this extension's own pages may drive it.
    if (sender.id !== chrome.runtime.id || !message || !handlers[message.type]) {
        return false;
    }
    handlers[message.type](message)
        .then(sendResponse)
        .catch((err) => sendResponse({ ok: false, error: String((err && err.message) || err) }));
    return true;
});
