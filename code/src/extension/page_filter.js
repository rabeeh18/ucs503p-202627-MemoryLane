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

function isAutoCaptureEligible(url) {
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
