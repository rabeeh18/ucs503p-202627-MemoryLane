// Injected on demand by background.js, before content.js when saving and on its
// own when the popup checks whether a page is saved. The value of the final
// expression is returned to the caller: the page's canonical URL, or null.
//
// Single-page apps (Reddit, YouTube, GitHub, ...) change the address without a
// reload and can leave the first page's canonical link in place. After such a
// navigation the canonical is trusted only if it describes the current page:
// the same host and path, and every parameter it has matching the address.
// So `watch?v=X` is kept on `watch?v=X&t=90s`, but post A's canonical is
// dropped while viewing post B.

// eslint-disable-next-line no-unused-vars
function memorylaneCanonical() {
    const link = document.querySelector("link[rel='canonical']");
    if (!link || !link.href) return null;
    const strip = (u) => String(u).split("#")[0];
    const nav = performance.getEntriesByType("navigation")[0];
    if (!nav || !nav.name || strip(nav.name) === strip(location.href)) return link.href;
    try {
        const canonical = new URL(link.href);
        const here = new URL(location.href);
        const host = (h) => h.toLowerCase().replace(/^www\./, "");
        const path = (p) => p.replace(/\/+$/, "") || "/";
        if (host(canonical.hostname) !== host(here.hostname) || path(canonical.pathname) !== path(here.pathname)) {
            return null;
        }
        for (const [key, value] of canonical.searchParams) {
            if (here.searchParams.get(key) !== value) return null;
        }
        return link.href;
    } catch (_err) {
        return null;
    }
}

memorylaneCanonical();
