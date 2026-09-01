importScripts("page_filter.js");

const API_BASE = "http://localhost:8000";
const DEFAULT_CAPTURE_MODE = "manual";

const inFlightUrls = new Set();
const recentlyCaptured = new Map();
const RECENT_CAPTURE_MS = 60 * 1000;

chrome.runtime.onInstalled.addListener(() => {
    console.log("MemoryLane extension installed");
    chrome.storage.local.get({ captureMode: DEFAULT_CAPTURE_MODE }, (stored) => {
        if (!stored.captureMode) {
            chrome.storage.local.set({ captureMode: DEFAULT_CAPTURE_MODE });
        }
    });
});

function extractViaInjection() {
    const clone = document.body.cloneNode(true);
    ["script", "style", "nav", "footer", "aside", "header"].forEach((sel) => {
        clone.querySelectorAll(sel).forEach((el) => el.remove());
    });
    return (clone.innerText || "").trim();
}

async function extractTabContent(tab) {
    let content = "";
    try {
        const extracted = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT_CONTENT" });
        if (extracted && extracted.ok) {
            content = extracted.content || "";
        }
    } catch (_err) {
        content = "";
    }

    if (!content.trim()) {
        const [{ result: injected }] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: extractViaInjection,
        });
        content = injected || "";
    }

    return (content || "").trim();
}

async function saveTab(tab, { skipEligibility = false } = {}) {
    if (!tab || !tab.id || !tab.url) {
        throw new Error("Cannot save this type of page");
    }
    if (tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://")) {
        throw new Error("Cannot save this type of page");
    }
    if (!skipEligibility && !isAutoCaptureEligible(tab.url)) {
        return { ok: true, skipped: true, reason: "ineligible" };
    }

    const key = tab.url.split("#")[0];
    const last = recentlyCaptured.get(key);
    if (last && Date.now() - last < RECENT_CAPTURE_MS) {
        return { ok: true, skipped: true, reason: "recent" };
    }
    if (inFlightUrls.has(key)) {
        return { ok: true, skipped: true, reason: "in-flight" };
    }

    inFlightUrls.add(key);
    try {
        const content = await extractTabContent(tab);
        if (!content) {
            throw new Error("No text content found on page");
        }

        const response = await fetch(`${API_BASE}/memory`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                url: tab.url,
                title: tab.title || tab.url,
                content,
            }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Failed to save memory");
        }

        const data = await response.json();
        recentlyCaptured.set(key, Date.now());
        return { ok: true, data };
    } finally {
        inFlightUrls.delete(key);
    }
}

async function getCaptureMode() {
    const stored = await chrome.storage.local.get({ captureMode: DEFAULT_CAPTURE_MODE });
    return stored.captureMode === "automatic" ? "automatic" : "manual";
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status !== "complete") {
        return;
    }
    (async () => {
        const mode = await getCaptureMode();
        if (mode !== "automatic") {
            return;
        }
        if (!tab || !tab.url || !isAutoCaptureEligible(tab.url)) {
            return;
        }
        try {
            await saveTab(tab, { skipEligibility: true });
        } catch (error) {
            console.warn("Automatic capture failed:", error.message || error);
        }
    })();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message) {
        return;
    }

    if (message.type === "GET_CAPTURE_MODE") {
        getCaptureMode().then((captureMode) => sendResponse({ ok: true, captureMode }));
        return true;
    }

    if (message.type === "SET_CAPTURE_MODE") {
        const captureMode = message.captureMode === "automatic" ? "automatic" : "manual";
        chrome.storage.local.set({ captureMode }, () => {
            sendResponse({ ok: true, captureMode });
        });
        return true;
    }

    if (message.type !== "SAVE_CURRENT_PAGE") {
        return;
    }

    (async () => {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            const result = await saveTab(tab, { skipEligibility: true });
            sendResponse(result);
        } catch (error) {
            sendResponse({ ok: false, error: error.message || String(error) });
        }
    })();

    return true;
});
