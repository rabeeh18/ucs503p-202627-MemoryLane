// ==UserScript==
// @name         MemoryLane
// @namespace    http://tampermonkey.net/
// @version      0.4.0
// @description  Automatically save public webpages semantically to MemoryLane
// @author       You
// @match        *://*/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

// Runs on every page. Waits a bit for dynamic content, checks if the page
// looks login-gated or otherwise not worth remembering, extracts the
// article with Readability, POSTs it to the backend. No button, no user
// interaction.
//
// The backend splits saved pages into chunks for retrieval — that's
// entirely server-side. This script still just sends the full extracted
// {url, title, content}, same as before — except for YouTube watch pages,
// which are handled specially (see PLATFORM_RULES below).

const DEBUG_MODE = false; // flip on for a status panel + manual save button

const SAVE_DELAY_MS = 7000; // give JS-rendered pages time to load
const DUPLICATE_WINDOW_MS = 30 * 60 * 1000; // don't re-save the same url within 30 min

const BACKEND_URL = "http://localhost:8000/memory";

// ============================================================================
// WHY THIS FILTERING EXISTS
// ============================================================================
//
// Auto-saving every page means MemoryLane also picks up a lot of pages
// that aren't really "memories" — a Google search results page, a
// chrome:// settings screen, a login form, a Reddit/YouTube/Instagram
// homepage that's really just a feed of many unrelated things.
//
// The fix is NOT to blocklist URLs containing words like "search" or
// "account" — that would reject perfectly good pages too (a GitHub repo,
// a Medium article about authentication, a blog post about search engine
// optimization). Instead, several independent signals are combined into
// one quality decision: URL shape, whether Readability actually found an
// article, how much real text there is, paragraph structure, and how
// link-heavy the page is. A page is only rejected when multiple signals
// agree it's low-value — one weak signal is never enough on its own.
//
// The one deliberate exception is PLATFORM_RULES below: for a short list
// of named platforms (YouTube, Reddit, X/Twitter, Instagram, TikTok,
// LinkedIn), a feed/homepage/listing URL is rejected outright rather than
// scored — "reddit.com/r/programming" is a feed of many posts, not a
// memory, no matter how much text happens to be on it. A SPECIFIC post
// on those same platforms ("reddit.com/r/x/comments/.../actual-post") is
// still a perfectly good memory and goes through the normal flow below.

// ============================================================================
// BROWSER-INTERNAL PAGES — the one hard, non-content-based rule
// ============================================================================

function isBrowserInternalPage(url) {
    return /^(chrome|chrome-extension|edge|about|file|moz-extension|view-source):/i.test(url);
}

// ============================================================================
// PLATFORM RULES — feed/homepage vs. specific content
// ============================================================================
// Narrow and explicit on purpose: only these named hosts are checked this
// way. Everything else falls through to the generic quality scoring
// below, which already gives a weak penalty to any site's bare homepage
// (see evaluateContentQuality) without needing to know the site by name.
//
// `isSpecificContent(url)` returning false means "this is a feed/listing/
// homepage" -> rejected outright. `isVideo: true` (YouTube) means "don't
// bother running Readability here — send title+url only, the backend
// fetches the real transcript."

const PLATFORM_RULES = [
    {
        name: "YouTube",
        hosts: ["youtube.com", "m.youtube.com", "youtu.be"],
        isVideo: true,
        isSpecificContent: (u) => {
            const host = u.hostname.replace(/^www\.|^m\./, "");
            if (host === "youtu.be") return u.pathname.replace(/^\/|\/$/g, "").length > 0;
            return u.pathname.startsWith("/watch") || u.pathname.startsWith("/shorts/");
        },
    },
    {
        name: "Reddit",
        hosts: ["reddit.com"],
        isSpecificContent: (u) => u.pathname.includes("/comments/"),
    },
    {
        name: "X/Twitter",
        hosts: ["twitter.com", "x.com"],
        isSpecificContent: (u) => /\/status\//.test(u.pathname),
    },
    {
        name: "Instagram",
        hosts: ["instagram.com"],
        isSpecificContent: (u) => /^\/(p|reel|reels)\//.test(u.pathname),
    },
    {
        name: "TikTok",
        hosts: ["tiktok.com"],
        isSpecificContent: (u) => /\/video\//.test(u.pathname),
    },
    {
        name: "LinkedIn",
        hosts: ["linkedin.com"],
        isSpecificContent: (u) => /\/(posts|pulse)\//.test(u.pathname),
    },
];

function matchPlatform(urlString) {
    let u;
    try {
        u = new URL(urlString);
    } catch (e) {
        return null;
    }
    const host = u.hostname.replace(/^www\./, "").toLowerCase();
    for (const rule of PLATFORM_RULES) {
        if (rule.hosts.some((h) => host === h || host.endsWith("." + h))) {
            return { rule, parsedUrl: u };
        }
    }
    return null;
}

// ============================================================================
// KNOWN SEARCH-ENGINE RESULTS PAGES
// ============================================================================
// Deliberately narrow: only matches an ACTUAL known search engine
// hostname, on a results-shaped path, with a search query parameter
// present — "search" appearing somewhere in a URL is not enough
// (example.com/blog/search-engine-optimization does not match this).
// Feeds into the quality score below as one signal among several.

const SEARCH_ENGINE_HOSTS = [
    "bing.com",
    "duckduckgo.com",
    "search.yahoo.com",
    "yandex.com",
    "yandex.ru",
    "baidu.com",
    "ecosia.org",
    "startpage.com",
];

function isKnownSearchEngineResultsPage(urlString) {
    let u;
    try {
        u = new URL(urlString);
    } catch (e) {
        return false;
    }

    const host = u.hostname.replace(/^www\./, "").toLowerCase();
    const params = u.searchParams;
    const hasSearchQueryParam = params.has("q") || params.has("query") || params.has("wd") || params.has("p");

    if (!hasSearchQueryParam) return false;

    const isKnownHost =
        SEARCH_ENGINE_HOSTS.some((h) => host === h || host.endsWith("." + h)) ||
        /^google\.[a-z.]+$/.test(host); // google.com, google.co.uk, google.de, ...

    if (!isKnownHost) return false;

    const path = u.pathname.toLowerCase();
    const looksLikeResultsPath = path === "/" || path === "" || path.startsWith("/search") || path.startsWith("/webhp");

    return looksLikeResultsPath;
}

// ============================================================================
// SENSITIVE-DATA DETECTION
// ============================================================================
// Content-based, not domain-based — a public page can leak personal data
// on any site (a shared doc, a pasted screenshot's caption, a leaked
// invoice), and most sites that ARE inherently sensitive (banking,
// health portals) are already behind the login wall the auth heuristic
// catches. This looks for a couple of well-defined, low-false-positive
// patterns directly in the extracted text: SSN-shaped numbers, and
// credit-card-shaped digit runs that pass a Luhn checksum (a plain
// 16-digit run alone — an order number, a tracking ID — will almost
// never pass Luhn, which is what keeps this from being trigger-happy).
// This is a heuristic, not a guarantee, same as the auth detector.

function luhnCheck(digits) {
    let sum = 0;
    let alternate = false;
    for (let i = digits.length - 1; i >= 0; i--) {
        let n = parseInt(digits[i], 10);
        if (alternate) {
            n *= 2;
            if (n > 9) n -= 9;
        }
        sum += n;
        alternate = !alternate;
    }
    return sum % 10 === 0;
}

function detectSensitiveContent(text) {
    const reasons = [];

    if (/\b\d{3}-\d{2}-\d{4}\b/.test(text)) {
        reasons.push("SSN-shaped number found");
    }

    const candidates = text.match(/\b(?:\d[ -]?){13,19}\b/g) || [];
    for (const candidate of candidates) {
        const digits = candidate.replace(/[ -]/g, "");
        if (digits.length >= 13 && digits.length <= 19 && luhnCheck(digits)) {
            reasons.push("credit-card-shaped number found (passed Luhn check)");
            break;
        }
    }

    return { sensitive: reasons.length > 0, reasons };
}

// ============================================================================
// AUTHENTICATION / PROTECTED-PAGE HEURISTIC (runs on the live DOM, before
// Readability, since login pages often don't have "article" content to
// extract in the first place)
// ============================================================================

function detectAuthProtectedPage() {
    let score = 0;
    const reasons = [];

    const passwordInputs = document.querySelectorAll('input[type="password"]');
    if (passwordInputs.length > 0) {
        score += 5;
        reasons.push(`${passwordInputs.length} password input(s) present`);
    }

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

    const path = window.location.pathname.toLowerCase();
    if (/(^|\/)(login|signin|sign-in|log-in|authenticate|auth|sso)(\/|$|\?)/.test(path)) {
        score += 3;
        reasons.push(`URL path looks like an auth route (${path})`);
    }
    if (/(^|\/)(account|dashboard|settings|profile|my-account|inbox)(\/|$|\?)/.test(path)) {
        score += 1;
        reasons.push(`URL path looks like an account area (${path})`);
    }

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

    const BLOCK_THRESHOLD = 4;
    const blocked = score >= BLOCK_THRESHOLD;

    return { blocked, score, reasons };
}

// ============================================================================
// CONTENT QUALITY SCORING (runs after Readability extraction)
// ============================================================================
// A lightweight point system, not a single threshold on any one signal.
// Positive signals (real prose, real paragraphs, a real title, low
// link-to-text ratio) add up; negative signals (link-heavy pages, almost
// no text, a bare homepage path, known search-results shape) subtract.
// Only the combined total decides whether the page gets saved.

function evaluateContentQuality(url, title, content) {
    const positives = [];
    const negatives = [];
    let score = 0;

    const words = (content || "").trim().split(/\s+/).filter(Boolean);
    const wordCount = words.length;

    const paragraphs = Array.from(document.querySelectorAll("p"))
        .map((p) => (p.textContent || "").trim())
        .filter((t) => t.split(/\s+/).filter(Boolean).length >= 20);

    const bodyText = (document.body.innerText || document.body.textContent || "").trim();
    let linkTextLength = 0;
    document.querySelectorAll("a").forEach((a) => {
        linkTextLength += (a.textContent || "").trim().length;
    });
    const linkRatio = bodyText.length > 0 ? linkTextLength / bodyText.length : 0;

    // --- positive signals ---
    if (wordCount >= 150) {
        score += 3;
        positives.push(`${wordCount} words extracted`);
    }
    if (wordCount >= 400) {
        score += 2;
        positives.push("substantial article length");
    }
    if (paragraphs.length >= 3) {
        score += 2;
        positives.push(`${paragraphs.length} real paragraph(s)`);
    }
    if (title && title.trim().length > 0 && title.trim().toLowerCase() !== "untitled") {
        score += 1;
        positives.push("has a real title");
    }
    if (linkRatio < 0.25) {
        score += 2;
        positives.push("mostly prose, not links");
    }

    // --- negative signals ---
    if (wordCount < 40) {
        score -= 4;
        negatives.push("very little extracted text");
    }
    if (linkRatio > 0.5) {
        score -= 3;
        negatives.push("page is mostly links/navigation");
    }
    if (paragraphs.length === 0 && wordCount < 150) {
        score -= 2;
        negatives.push("no real paragraph structure");
    }
    if (isKnownSearchEngineResultsPage(url)) {
        score -= 6;
        negatives.push("looks like a search engine results page");
    }

    // generic "bare homepage" penalty for any site not already covered by
    // PLATFORM_RULES — a weak signal on its own, but a homepage rarely
    // has enough going for it to survive the other signals too
    let path = "/";
    try {
        path = new URL(url).pathname;
    } catch (e) {
        // ignore
    }
    if (path === "/" || path === "") {
        score -= 2;
        negatives.push("looks like a site homepage");
    }

    return { score, positives, negatives, wordCount, linkRatio };
}

const QUALITY_THRESHOLD = 0;

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

function logSaved(title) {
    console.log("[MemoryLane] Saved:");
    console.log(`Title: ${title}`);
}

function logSkipped(reason) {
    console.log("[MemoryLane] Skipped:");
    console.log(reason);
}

async function sendYoutubeVideo(rawUrl, debugPanel) {
    // don't run Readability on the player UI — comments, recommended
    // videos, and chrome are not what this video is "about". Send just
    // title+url; the backend fetches the real transcript.
    const title = (document.title || "Untitled").replace(/\s*-\s*YouTube\s*$/i, "").trim() || "Untitled";
    const webpageData = { title, content: "", url: rawUrl };

    try {
        setDebugPanelText(debugPanel, "saving (fetching transcript)...");
        await sendToBackend(webpageData);
        markAsSaved(rawUrl);
        logSaved(title);
        setDebugPanelText(debugPanel, "saved ✓");
    } catch (error) {
        setDebugPanelText(debugPanel, "error (see console)");
    }
}

async function autoSavePage(debugPanel) {
    const url = window.location.href;

    if (isBrowserInternalPage(url)) {
        logSkipped("Browser-internal page");
        setDebugPanelText(debugPanel, "skipped (internal page)");
        return;
    }

    if (wasRecentlySaved(url)) {
        console.log("[MemoryLane] Already saved recently — skipping:", url);
        setDebugPanelText(debugPanel, "skipped (recently saved)");
        return;
    }

    // named platforms: reject feeds/homepages outright, and hand video
    // pages off to the transcript path before Readability ever runs
    const platformMatch = matchPlatform(url);
    if (platformMatch) {
        const { rule, parsedUrl } = platformMatch;
        if (!rule.isSpecificContent(parsedUrl)) {
            logSkipped(`${rule.name} feed/listing/homepage — not a specific post`);
            setDebugPanelText(debugPanel, "skipped (feed/homepage)");
            return;
        }
        if (rule.isVideo) {
            await sendYoutubeVideo(url, debugPanel);
            return;
        }
        // a specific post on a known platform (reddit thread, tweet, reel,
        // etc.) — fall through to the normal Readability + quality flow
    }

    const authCheck = detectAuthProtectedPage();
    if (authCheck.blocked) {
        logSkipped("Authentication-protected page detected");
        console.log("[MemoryLane] Reasons:", authCheck.reasons.join("; "));
        setDebugPanelText(debugPanel, "skipped (auth-protected)");
        return;
    }

    await loadReadability();

    const webpageData = extractWebpageContent();
    if (!webpageData || !webpageData.content || webpageData.content.trim().length < 20) {
        logSkipped("Insufficient meaningful content");
        setDebugPanelText(debugPanel, "skipped (no content)");
        return;
    }

    const sensitiveCheck = detectSensitiveContent(webpageData.content);
    if (sensitiveCheck.sensitive) {
        logSkipped("Possible sensitive personal data detected");
        console.log("[MemoryLane] Reasons:", sensitiveCheck.reasons.join("; "));
        setDebugPanelText(debugPanel, "skipped (sensitive data)");
        return;
    }

    const wordCount = webpageData.content.trim().split(/\s+/).filter(Boolean).length;

    // weak account/dashboard URL signal + almost nothing extractable =
    // probably a private area, not an article
    if (authCheck.score >= 2 && wordCount < 60) {
        logSkipped("Authentication-protected page detected");
        console.log("[MemoryLane] Reasons: weak account/dashboard URL signal + very little content");
        setDebugPanelText(debugPanel, "skipped (auth-protected)");
        return;
    }

    const quality = evaluateContentQuality(url, webpageData.title, webpageData.content);
    if (quality.score < QUALITY_THRESHOLD) {
        const reason = quality.negatives.length > 0 ? quality.negatives.join("; ") : "Low content quality score";
        logSkipped(reason.includes("search engine results") ? "Search results page detected" : reason);
        console.log(`[MemoryLane] Quality score: ${quality.score} (positives: ${quality.positives.join(", ") || "none"}; negatives: ${quality.negatives.join(", ") || "none"})`);
        setDebugPanelText(debugPanel, "skipped (low quality)");
        return;
    }

    try {
        setDebugPanelText(debugPanel, "saving...");
        await sendToBackend(webpageData);
        markAsSaved(url);
        logSaved(webpageData.title);
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
