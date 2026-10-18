const SOCIAL_HOSTS = [
    "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "linkedin.com", "reddit.com", "snapchat.com",
    "pinterest.com", "threads.net", "whatsapp.com", "discord.com",
    "tumblr.com", "bsky.app",
];

const BANKING_HOST_MARKERS = [
    "paypal.com", "venmo.com", "stripe.com", "chase.com",
    "bankofamerica.com", "wellsfargo.com", "capitalone.com",
    "americanexpress.com", "amex.com", "citibank.com", "citi.com",
    "hsbc.com", "barclays.com", "revolut.com", "wise.com", "cash.app",
    "discover.com", "schwab.com", "fidelity.com", "tdbank.com",
    "ally.com", "sofi.com",
];

const LOGIN_ACCOUNT_SEGMENTS = [
    "login", "log-in", "signin", "sign-in", "signup", "sign-up",
    "register", "auth", "oauth", "sso", "account", "accounts",
    "password", "forgot", "checkout", "billing", "payment", "wallet",
];

const INTERNAL_SCHEMES = [
    "chrome", "chrome-extension", "edge", "about", "moz-extension",
    "brave", "devtools", "view-source", "file", "data", "javascript",
];

const SEARCH_ENGINE_HOSTS = [
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com",
];

const UTILITY_PATH_SEGMENTS = [
    "404", "error", "privacy", "privacy-policy", "terms", "terms-of-service",
    "tos", "cookie", "cookies", "sitemap", "sitemap.xml",
];

const IGNORED_EXTENSIONS = [
    ".pdf", ".zip", ".exe", ".png", ".jpg", ".jpeg", ".mp4", ".mp3",
    ".gif", ".csv", ".json", ".xml",
];

function hostMatches(host, domain) {
    host = host.toLowerCase().replace(/^www\./, "");
    domain = domain.toLowerCase();
    return host === domain || host.endsWith("." + domain);
}

export function isAutoCaptureEligible(url) {
    if (!url || !String(url).trim()) {
        return false;
    }
    let parsed;
    try {
        parsed = new URL(url.trim());
    } catch (_err) {
        return false;
    }
    const scheme = (parsed.protocol || "").replace(":", "").toLowerCase();
    if (INTERNAL_SCHEMES.includes(scheme) || (scheme !== "http" && scheme !== "https")) {
        return false;
    }

    let host = (parsed.hostname || "").toLowerCase().replace(/^www\./, "");
    if (!host) {
        return false;
    }

    if (SOCIAL_HOSTS.some((d) => hostMatches(host, d))) {
        return false;
    }
    if (host.endsWith(".bank") || host.includes("banking")) {
        return false;
    }
    if (BANKING_HOST_MARKERS.some((d) => hostMatches(host, d))) {
        return false;
    }
    if (host.split(".")[0].includes("bank")) {
        return false;
    }

    const path = parsed.pathname || "/";
    const segments = path.split("/").filter(Boolean).map((s) => s.toLowerCase());
    if (segments.some((seg) => LOGIN_ACCOUNT_SEGMENTS.includes(seg))) {
        return false;
    }
    if (segments.some((seg) => UTILITY_PATH_SEGMENTS.includes(seg))) {
        return false;
    }
    const loweredPath = path.toLowerCase();
    if (loweredPath.includes("/reset-password") || loweredPath.includes("/forgot-password")) {
        return false;
    }

    if (IGNORED_EXTENSIONS.some((ext) => loweredPath.endsWith(ext))) {
        return false;
    }

    // Search engine result pages check
    if (SEARCH_ENGINE_HOSTS.some((d) => hostMatches(host, d))) {
        const query = (parsed.search || "").toLowerCase();
        if (loweredPath.includes("/search") || loweredPath.includes("/results") || query.includes("q=")) {
            return false;
        }
    }

    // YouTube specific checks
    const isYouTube = hostMatches(host, "youtube.com");
    const isYouTuBe = hostMatches(host, "youtu.be");
    if (isYouTube || isYouTuBe) {
        if (isYouTube) {
            if (!loweredPath.startsWith("/watch")) {
                return false;
            }
            if (!parsed.search.includes("v=")) {
                return false;
            }
        }
        if (isYouTuBe) {
            if (path === "/" || path === "") {
                return false;
            }
        }
    }

    if (path === "/" || path === "") {
        return false;
    }

    return true;
}


/** Pages the extension can save at all (manual save): http(s) documents that aren't files like PDFs. */
export function isSaveableUrl(url) {
    let parsed;
    try {
        parsed = new URL(String(url || "").trim());
    } catch (_err) {
        return false;
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return false;
    }
    if (hostMatches(parsed.hostname, "chromewebstore.google.com") ||
        (hostMatches(parsed.hostname, "chrome.google.com") && parsed.pathname.startsWith("/webstore"))) {
        return false; // Chrome blocks scripts on the Web Store
    }
    const path = parsed.pathname.toLowerCase();
    return !IGNORED_EXTENSIONS.some((ext) => path.endsWith(ext));
}

/**
 * "https://www.Example.com/a?b" or "WWW.example.com" -> "example.com".
 * Returns "" when the input isn't a usable hostname.
 */
export function normalizeHost(input) {
    let value = String(input || "").trim().toLowerCase();
    if (!value) {
        return "";
    }
    if (!/^[a-z][a-z0-9+.-]*:\/\//.test(value)) {
        value = `http://${value}`;
    }
    let host;
    try {
        host = new URL(value).hostname;
    } catch (_err) {
        return "";
    }
    host = host.replace(/^www\./, "").replace(/\.$/, "");
    if (!host || !/^[a-z0-9.-]+$/.test(host) || !host.includes(".") || host.startsWith(".") || host.includes("..")) {
        return "";
    }
    return host;
}

/** True when url's host is an excluded site or a subdomain of one. */
export function isExcluded(url, excludedSites) {
    const host = normalizeHost(url);
    return Boolean(host) && (excludedSites || []).some((site) => host === site || host.endsWith(`.${site}`));
}
