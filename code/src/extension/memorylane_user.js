// ==UserScript==
// @name         MemoryLane
// @namespace    http://tampermonkey.net/
// @version      0.2.0
// @description  Automatically save public webpages semantically to MemoryLane
// @author       You
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      localhost:8000
// @run-at       document-idle
// ==/UserScript==

// Runs on every page. Waits a bit for dynamic content, checks if the page
// looks login-gated, extracts the article with Readability, POSTs it to
// the backend. No button, no user interaction.

const DEBUG_MODE = false; // flip on for a status panel + manual save button

const SAVE_DELAY_MS = 7000; // give JS-rendered pages time to load
const DUPLICATE_WINDOW_MS = 30 * 60 * 1000; // don't re-save the same url within 30 min

const BACKEND_URL = "http://localhost:8000/memory";

/**
 * Scored heuristic for "is this a login/account page". No browser API
 * gives us this directly, so we guess based on password fields, login
 * forms, url path, and short exact-match login/logout buttons. Weighted
 * so an article that just mentions the word "login" doesn't get blocked.
 */
function detectAuthProtectedPage() {
    let score = 0;
    const reasons = [];

    // an actual password field is basically a guarantee
    const passwordInputs = document.querySelectorAll('input[type="password"]');
    if (passwordInputs.length > 0) {
        score += 5;
        reasons.push(`${passwordInputs.length} password input(s) present`);
    }

    // forms with a password field, or that are clearly named/labeled as login forms
    const forms = document.querySelectorAll("form");
    let loginFormCount = 0;
    forms.forEach((form) => {
        const hasPasswordField = form.querySelector('input[type="password"]') !== null;
        const formSignature = (
            (form.id || "") + " " +
            (form.className || "") + " " +
            (form.getAttribute("action") || "") + " " +
            (form.getAttribute("name") || "")
        ).toLowerCase();
        const looksLikeLoginForm = /login|signin|sign-in|log-in|auth/.test(formSignature);

        if (hasPasswordField || looksLikeLoginForm) {
            loginFormCount++;
        }
    });
    if (loginFormCount > 0) {
        score += 4;
        reasons.push(`${loginFormCount} login-like form(s) present`);
    }

    // url path looks like an auth or account route
    const path = window.location.pathname.toLowerCase();
    if (/(^|\/)(login|signin|sign-in|log-in|authenticate|auth|sso)(\/|$|\?)/.test(path)) {
        score += 3;
        reasons.push(`URL path looks like an auth route (${path})`);
    }
    if (/(^|\/)(account|dashboard|settings|profile|my-account|inbox)(\/|$|\?)/.test(path)) {
        score += 1;
        reasons.push(`URL path looks like an account area (${path})`);
    }

    // short buttons/links whose text is exactly "login"/"sign in" etc — not
    // just any element that happens to contain the word somewhere
    const authPhrases = /^(log ?in|sign ?in|authenticate|account login)$/i;
    const clickable = document.querySelectorAll("button, a, [role='button']");
    let authButtonCount = 0;
    clickable.forEach((el) => {
        const text = (el.textContent || "").trim();
        if (text.length > 0 && text.length <= 20 && authPhrases.test(text)) {
            authButtonCount++;
        }
    });
    if (authButtonCount > 0) {
        score += 2;
        reasons.push(`${authButtonCount} short login/sign-in button(s) or link(s)`);
    }

    // logout/sign-out present = we're probably already inside an account —
    // weak signal on its own since some sites always show "log in" for guests
    const logoutPhrases = /^(log ?out|sign ?out)$/i;
    let logoutCount = 0;
    clickable.forEach((el) => {
        const text = (el.textContent || "").trim();
        if (text.length > 0 && text.length <= 20 && logoutPhrases.test(text)) {
            logoutCount++;
        }
    });
    if (logoutCount > 0) {
        score += 1;
        reasons.push(`${logoutCount} logout/sign-out indicator(s) (already authenticated)`);
    }

    // a password field or real login form alone is enough; loose text/url
    // matches on their own are not
    const BLOCK_THRESHOLD = 4;
    const blocked = score >= BLOCK_THRESHOLD;

    return { blocked, score, reasons };
}

function loadReadability() {
    return new Promise((resolve) => {
        if (typeof Readability !== "undefined") {
            resolve();
            return;
        }
        const script = document.createElement("script");
        script.src = "https://cdn.jsdelivr.net/npm/@mozilla/readability@0.4.2/Readability.js";
        script.onload = resolve;
        script.onerror = () => {
            console.error("[MemoryLane] Failed to load Readability");
            resolve();
        };
        document.head.appendChild(script);
    });
}

function extractWebpageContent() {
    try {
        // clone so Readability doesn't mutate the live page
        const documentClone = document.cloneNode(true);
        const reader = new Readability(documentClone);
        const article = reader.parse();

        if (!article) {
            console.warn("[MemoryLane] Readability returned null (couldn't parse page)");
            return null;
        }

        const title = article.title || document.title || "Untitled";
        const content = article.textContent || "";
        const url = window.location.href;

        console.log("[MemoryLane] Content extracted:");
        console.log(`  - Title: ${title}`);
        console.log(`  - Length: ${content.length} characters`);
        console.log(`  - URL: ${url}`);

        return { title, content, url };
    } catch (error) {
        console.error("[MemoryLane] Error extracting content:", error);
        return null;
    }
}

function wasRecentlySaved(url) {
    const key = "memorylane_saved_" + url;
    const lastSaved = GM_getValue(key, 0);
    return (Date.now() - lastSaved) < DUPLICATE_WINDOW_MS;
}

function markAsSaved(url) {
    const key = "memorylane_saved_" + url;
    GM_setValue(key, Date.now());
}

function sendToBackend(webpageData) {
    return new Promise((resolve, reject) => {
        console.log("[MemoryLane] Sending to backend...");
        console.log(`[MemoryLane] Backend URL: ${BACKEND_URL}`);

        GM_xmlhttpRequest({
            method: "POST",
            url: BACKEND_URL,
            headers: {
                "Content-Type": "application/json"
            },
            data: JSON.stringify(webpageData),
            onload: function (response) {
                try {
                    const result = JSON.parse(response.responseText);

                    if (result.success) {
                        console.log("[MemoryLane] ✓ Successfully saved to MemoryLane");
                        console.log(`[MemoryLane] Memory ID: ${result.metadata.id}`);
                        resolve(result);
                    } else {
                        console.error("[MemoryLane] Backend returned error:", result);
                        reject(result);
                    }
                } catch (e) {
                    console.error("[MemoryLane] Failed to parse response:", e);
                    reject(e);
                }
            },
            onerror: function (error) {
                console.error("[MemoryLane] Failed to send to backend:", error);
                console.error("[MemoryLane] Make sure the FastAPI server is running: uvicorn backend.main:app --reload");
                reject(error);
            }
        });
    });
}

function injectDebugPanel() {
    const panel = document.createElement("div");
    panel.id = "memorylane-debug-panel";
    panel.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 999999;
        padding: 10px 14px;
        background-color: rgba(0,0,0,0.75);
        color: #fff;
        border-radius: 6px;
        font-size: 12px;
        font-family: monospace;
        max-width: 280px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.2);
    `;
    panel.textContent = "[MemoryLane] debug: idle";
    document.body.appendChild(panel);
    return panel;
}

function setDebugPanelText(panel, text) {
    if (panel) panel.textContent = "[MemoryLane] " + text;
}

async function autoSavePage(debugPanel) {
    const url = window.location.href;

    if (wasRecentlySaved(url)) {
        console.log("[MemoryLane] Already saved recently — skipping:", url);
        setDebugPanelText(debugPanel, "skipped (recently saved)");
        return;
    }

    const authCheck = detectAuthProtectedPage();
    if (authCheck.blocked) {
        console.log("[MemoryLane] Authentication-protected page detected — skipping.");
        console.log("[MemoryLane] Reasons:", authCheck.reasons.join("; "));
        setDebugPanelText(debugPanel, "skipped (auth-protected)");
        return;
    }

    await loadReadability();

    const webpageData = extractWebpageContent();
    if (!webpageData || !webpageData.content || webpageData.content.trim().length < 50) {
        console.log("[MemoryLane] No meaningful content extracted — skipping.");
        setDebugPanelText(debugPanel, "skipped (no content)");
        return;
    }

    try {
        setDebugPanelText(debugPanel, "saving...");
        await sendToBackend(webpageData);
        markAsSaved(url);
        setDebugPanelText(debugPanel, "saved ✓");
    } catch (error) {
        setDebugPanelText(debugPanel, "error (see console)");
    }
}

async function main() {
    console.log("[MemoryLane] Userscript loaded on: " + window.location.href);

    let debugPanel = null;
    if (DEBUG_MODE) {
        debugPanel = injectDebugPanel();

        const button = document.createElement("button");
        button.textContent = "MemoryLane: save now";
        button.style.cssText = "display:block;margin-top:6px;";
        button.onclick = () => autoSavePage(debugPanel);
        debugPanel.appendChild(button);
    }

    setDebugPanelText(debugPanel, `waiting ${SAVE_DELAY_MS / 1000}s for page to settle...`);
    setTimeout(() => autoSavePage(debugPanel), SAVE_DELAY_MS);
}

main();