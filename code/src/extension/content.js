function extractReadableContent() {
    const clone = document.body ? document.body.cloneNode(true) : document.documentElement.cloneNode(true);
    const removeSelectors = [
        "script", "style", "noscript", "nav", "footer", "aside", "header",
        ".nav", ".footer", ".sidebar", ".menu", ".advertisement", ".ads",
        "[role='navigation']", "[role='banner']", "[role='complementary']"
    ];
    removeSelectors.forEach((sel) => {
        clone.querySelectorAll(sel).forEach((el) => el.remove());
    });
    const text = (clone.innerText || clone.textContent || "").replace(/\s+\n/g, "\n").trim();
    return text;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message && message.type === "EXTRACT_CONTENT") {
        try {
            const canonicalLink = document.querySelector("link[rel='canonical']");
            const canonicalUrl = canonicalLink ? canonicalLink.href : null;
            sendResponse({ 
                ok: true, 
                content: extractReadableContent(),
                canonicalUrl
            });
        } catch (error) {
            sendResponse({ ok: false, error: error.message || String(error) });
        }
    }
    return true;
});
