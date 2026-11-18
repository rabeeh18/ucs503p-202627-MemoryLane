// Injected by background.js when an eligible page finishes loading (auto-capture
// on). Tells the service worker once the page has actually been read, so pages you
// bounce off (redirects, wrong clicks, login walls) are never auto-saved:
//   - 30 seconds with the tab visible, or
//   - scrolled at least halfway down a long page, after 5 seconds in view.
// It sends one message, then stops; reading time pauses while the tab is hidden.
(() => {
    if (window.__memorylaneEngagement) return;
    window.__memorylaneEngagement = true;

    const READ_SECONDS = 30;
    const SCROLL_DEPTH = 0.5;
    const MIN_SECONDS_FOR_SCROLL = 5;

    let seconds = 0;
    let deepestScroll = 0;
    let done = false;

    function scrollDepth() {
        const page = document.documentElement;
        const scrollable = page.scrollHeight - window.innerHeight;
        if (scrollable < window.innerHeight * 0.5) return 0; // short page: reading time decides
        return Math.min(1, (window.scrollY + window.innerHeight) / page.scrollHeight);
    }

    function check() {
        if (done) return;
        if (seconds >= READ_SECONDS || (deepestScroll >= SCROLL_DEPTH && seconds >= MIN_SECONDS_FOR_SCROLL)) {
            done = true;
            clearInterval(timer);
            window.removeEventListener("scroll", onScroll);
            try {
                chrome.runtime.sendMessage({ type: "PAGE_ENGAGED", url: location.href });
            } catch (_err) {
                // The extension was reloaded or removed meanwhile.
            }
        }
    }

    function onScroll() {
        deepestScroll = Math.max(deepestScroll, scrollDepth());
        check();
    }

    const timer = setInterval(() => {
        if (document.visibilityState === "visible") seconds += 1;
        check();
    }, 1000);
    window.addEventListener("scroll", onScroll, { passive: true });
})();
