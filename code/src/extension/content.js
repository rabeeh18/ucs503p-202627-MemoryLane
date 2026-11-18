// Injected on demand by background.js (chrome.scripting.executeScript), right
// after canonical.js. The value of the final expression is returned to the caller:
//   { html, text, canonicalUrl, url, signals }
// `html` feeds the server's article extraction; `text` is the fallback.
(() => {
    // The API's limits (backend/models.py).
    const MAX_HTML_CHARS = 3_000_000;
    const MAX_TEXT_CHARS = 500_000;

    function readableText() {
        const root = document.body || document.documentElement;
        const clone = root.cloneNode(true);
        const removeSelectors = [
            "script", "style", "noscript", "nav", "footer", "aside", "header",
            ".nav", ".footer", ".sidebar", ".menu", ".advertisement", ".ads",
            "[role='navigation']", "[role='banner']", "[role='complementary']",
        ];
        removeSelectors.forEach((sel) => clone.querySelectorAll(sel).forEach((el) => el.remove()));
        return (clone.innerText || clone.textContent || "").replace(/\s+\n/g, "\n").trim();
    }

    const visible = (el) => Boolean(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    const wordCount = (t) => (String(t || "").match(/\S+/g) || []).length;

    // Measurements for automatic capture (page_filter.js assessContent decides).
    function pageSignals(text) {
        const meta = (selector) => document.querySelector(selector)?.getAttribute("content") || "";
        const robots = `${meta('meta[name="robots" i]')} ${meta('meta[name="googlebot" i]')}`.toLowerCase();
        let linkWords = 0;
        for (const a of document.querySelectorAll("main a, article a, body a")) {
            if (!a.closest("nav, header, footer, aside")) linkWords += wordCount(a.innerText);
        }
        let editorArea = 0;
        for (const el of document.querySelectorAll('textarea, [contenteditable=""], [contenteditable="true"], [role="textbox"]')) {
            if (visible(el)) editorArea = Math.max(editorArea, el.offsetWidth * el.offsetHeight);
        }
        const inputs = [...document.querySelectorAll("input, select, textarea")]
            .filter((el) => el.type !== "hidden" && visible(el)).length;
        return {
            words: wordCount(text),
            linkWords,
            ogType: meta('meta[property="og:type"]'),
            noindex: robots.includes("noindex"),
            passwordFields: [...document.querySelectorAll('input[type="password"]')].filter(visible).length,
            editorArea,
            inputs,
        };
    }

    const text = readableText();
    return {
        html: document.documentElement.outerHTML.slice(0, MAX_HTML_CHARS),
        text: text.slice(0, MAX_TEXT_CHARS),
        signals: pageSignals(text),
        // eslint-disable-next-line no-undef
        canonicalUrl: typeof memorylaneCanonical === "function" ? memorylaneCanonical() : null,
        // The document this text came from, so the caller can tell if the tab navigated meanwhile.
        url: location.href,
    };
})();
