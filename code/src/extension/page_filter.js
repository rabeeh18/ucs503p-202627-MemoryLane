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

// Webmail: inboxes and messages are private, so automatic capture never sends them.
const EMAIL_HOSTS = [
    "mail.google.com", "inbox.google.com", "outlook.live.com", "outlook.office.com",
    "outlook.office365.com", "outlook.com", "hotmail.com", "mail.yahoo.com",
    "mail.proton.me", "protonmail.com", "mail.zoho.com", "mail.zoho.in", "mail.zoho.eu",
    "fastmail.com", "tuta.com", "tutanota.com", "mail.aol.com", "mail.yandex.com",
    "mail.yandex.ru", "gmx.com", "gmx.net", "web.de", "mail.com", "hey.com",
    "rediffmail.com", "superhuman.com",
];
// Self-hosted and other webmail: mail.example.com, webmail.example.com, /owa/, /webmail/.
const EMAIL_HOST_PREFIXES = ["mail.", "webmail.", "email."];
const EMAIL_PATH_SEGMENTS = ["owa", "webmail", "roundcube", "squirrelmail"];

// Web apps that show your own private things: documents, chats, calendars,
// coursework, cloud consoles. Kept identical to backend/page_filter.py.
const PRIVATE_APP_HOSTS = [
    "docs.google.com", "drive.google.com", "calendar.google.com", "keep.google.com",
    "classroom.google.com", "contacts.google.com", "photos.google.com", "meet.google.com",
    "chat.google.com", "myaccount.google.com", "onedrive.live.com", "sharepoint.com",
    "office.com", "teams.microsoft.com", "teams.live.com", "notion.so", "notion.site",
    "slack.com", "discord.gg", "web.whatsapp.com", "web.telegram.org", "messenger.com",
    "figma.com", "miro.com", "trello.com", "asana.com", "atlassian.net", "monday.com",
    "dropbox.com", "box.com", "icloud.com", "zoom.us", "chatgpt.com", "chat.openai.com",
    "claude.ai", "gemini.google.com", "instructure.com", "blackboard.com",
    "console.aws.amazon.com", "portal.azure.com", "console.cloud.google.com",
    "vercel.com", "netlify.app", "app.netlify.com", "dashboard.stripe.com",
];
// Hosts that are private apps whatever the company (moodle.<university>, lms.<college>).
const PRIVATE_HOST_LABELS = ["moodle", "lms", "intranet", "portal", "erp", "webkiosk"];
// Paths of a site's private area rather than its public pages.
const PRIVATE_PATH_SEGMENTS = [
    "dashboard", "admin", "settings", "preferences", "profile", "inbox", "messages",
    "notifications", "cart", "basket", "orders", "my-account", "myaccount", "console",
];
// Query parameters that carry a secret: opening the link again would reuse it.
const SECRET_PARAMS = [
    "token", "access_token", "id_token", "auth", "code", "session", "sessionid", "sid",
    "key", "apikey", "api_key", "sig", "signature", "otp", "ticket", "secret", "password",
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

/** The same document, ignoring the #fragment (in-page jumps don't change the page). */
export function sameDocument(a, b) {
    return String(a || "").split("#")[0] === String(b || "").split("#")[0];
}

/** Local or intranet addresses: localhost, 10.x, 192.168.x, 172.16-31.x, .local, .internal. */
function isPrivateNetworkHost(host) {
    if (host === "localhost" || host.endsWith(".localhost") || host.endsWith(".local")
        || host.endsWith(".internal") || host.endsWith(".lan") || host.endsWith(".home.arpa")) {
        return true;
    }
    const ip = host.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
    if (ip) {
        const [a, b] = [Number(ip[1]), Number(ip[2])];
        return a === 10 || a === 127 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31)
            || (a === 169 && b === 254) || a === 0;
    }
    return host.startsWith("[");  // IPv6 literals: almost always local in practice
}

/** Pages that show the person's own private things: private apps, local sites,
 * account areas, and links carrying a secret. */
export function isPrivateUrl(url) {
    let parsed = url;
    if (!(parsed instanceof URL)) {
        try {
            parsed = new URL(String(url || "").trim());
        } catch (_err) {
            return false;
        }
    }
    const host = (parsed.hostname || "").toLowerCase().replace(/^www\./, "");
    if (isPrivateNetworkHost(host)) return true;
    if (PRIVATE_APP_HOSTS.some((d) => hostMatches(host, d))) return true;
    if (host.split(".").some((label) => PRIVATE_HOST_LABELS.includes(label))) return true;
    const segments = (parsed.pathname || "").split("/").filter(Boolean).map((s) => s.toLowerCase());
    if (segments.some((seg) => PRIVATE_PATH_SEGMENTS.includes(seg))) return true;
    for (const name of parsed.searchParams.keys()) {
        if (SECRET_PARAMS.includes(name.toLowerCase())) return true;
    }
    return false;
}

// ---- what's on the page -----------------------------------------------------------
//
// content.js measures the page (see pageSignals there); this decides from those
// measurements whether automatic capture should keep it. The idea: only save pages
// that read like something worth keeping (an article, docs, a post, a video), and
// skip anything that looks like an app, a form or a private screen, without having
// to name every such site.

export const MIN_AUTO_WORDS = 150;
const MAX_LINK_RATIO = 0.5;         // more link text than this: a menu, feed or index page
const MAX_EDITOR_AREA = 60000;      // px²: a visible compose box or document editor
const FORM_INPUTS = 8;              // this many visible fields with little text: a form

/**
 * @param {{words: number, linkWords: number, ogType: string, noindex: boolean,
 *          passwordFields: number, editorArea: number, inputs: number}} s
 * @returns {{ok: true} | {ok: false, reason: string}}
 */
export function assessContent(s) {
    if (!s) return { ok: false, reason: "couldn't read the page" };
    if (s.passwordFields > 0) return { ok: false, reason: "it has a password field" };
    if (s.editorArea >= MAX_EDITOR_AREA) return { ok: false, reason: "it's an editor or compose screen" };
    if (s.noindex) return { ok: false, reason: "it asks not to be indexed, as private pages usually do" };
    const type = String(s.ogType || "").toLowerCase();
    if (type.startsWith("video")) return { ok: true };
    if (s.words < MIN_AUTO_WORDS) return { ok: false, reason: "it has too little text to read" };
    if (s.words > 0 && s.linkWords / s.words > MAX_LINK_RATIO) return { ok: false, reason: "it's mostly links" };
    if (s.inputs >= FORM_INPUTS && s.words < 400) return { ok: false, reason: "it's mostly a form" };
    return { ok: true };
}

/** Webmail inboxes and messages, including iCloud Mail (icloud.com/mail). */
export function isEmailUrl(url) {
    let parsed = url;
    if (!(parsed instanceof URL)) {
        try {
            parsed = new URL(String(url || "").trim());
        } catch (_err) {
            return false;
        }
    }
    const host = (parsed.hostname || "").toLowerCase().replace(/^www\./, "");
    if (EMAIL_HOSTS.some((d) => hostMatches(host, d))) return true;
    if (EMAIL_HOST_PREFIXES.some((p) => host.startsWith(p))) return true;
    const segments = (parsed.pathname || "").split("/").filter(Boolean).map((s) => s.toLowerCase());
    if (hostMatches(host, "icloud.com") && segments[0] === "mail") return true;
    return segments.some((seg) => EMAIL_PATH_SEGMENTS.includes(seg));
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
    if (isEmailUrl(parsed)) {
        return false;
    }
    if (isPrivateUrl(parsed)) {
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
