// Injected on demand by background.js (chrome.scripting.executeScript). The
// value of the final expression is returned to the caller:
//   { html, text, canonicalUrl }
// `html` feeds the server's article extraction; `text` is the fallback.
(() => {
    const MAX_HTML_CHARS = 3_000_000;

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

    const canonical = document.querySelector("link[rel='canonical']");
    return {
        html: document.documentElement.outerHTML.slice(0, MAX_HTML_CHARS),
        text: readableText(),
        canonicalUrl: canonical ? canonical.href : null,
    };
})();
