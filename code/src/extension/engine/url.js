import { pyStrip } from "./pytext.js";

// backend/url_utils.py in JavaScript, following Python's urllib.parse exactly,
// so a page gets the same id whether it is stored locally or on the server.

const TRACKING_PARAMS = new Set([
    "fbclid", "gclid", "dclid", "msclkid", "twclid", "yclid",
    "igshid", "mc_cid", "mc_eid", "_ga", "_gl", "ref", "ref_src",
]);

const SCHEME_CHARS = /^[A-Za-z][A-Za-z0-9+\-.]*$/;
// urllib strips these from the start of a URL, and removes these anywhere.
const LEADING_C0_AND_SPACE = /^[\x00-\x20]+/;
const UNSAFE = /[\t\r\n]/g;

/** urllib.parse.urlsplit: {scheme, netloc, path, query, fragment}. */
export function urlsplit(url) {
    url = url.replace(LEADING_C0_AND_SPACE, "").replace(UNSAFE, "");
    let scheme = "";
    const colon = url.indexOf(":");
    if (colon > 0 && SCHEME_CHARS.test(url.slice(0, colon))) {
        scheme = url.slice(0, colon).toLowerCase();
        url = url.slice(colon + 1);
    }
    let netloc = "";
    if (url.startsWith("//")) {
        let end = url.length;
        for (const c of "/?#") {
            const i = url.indexOf(c, 2);
            if (i >= 0 && i < end) end = i;
        }
        netloc = url.slice(2, end);
        url = url.slice(end);
    }
    let fragment = "";
    const hash = url.indexOf("#");
    if (hash >= 0) {
        fragment = url.slice(hash + 1);
        url = url.slice(0, hash);
    }
    let query = "";
    const q = url.indexOf("?");
    if (q >= 0) {
        query = url.slice(q + 1);
        url = url.slice(0, q);
    }
    return { scheme, netloc, path: url, query, fragment };
}

/** urllib.parse.urlparse: urlsplit plus ;params on the last path segment. */
export function urlparse(url) {
    const s = urlsplit(url);
    let params = "";
    if (s.path.includes(";")) {
        const slash = s.path.lastIndexOf("/");
        const i = slash >= 0 ? s.path.indexOf(";", slash) : s.path.indexOf(";");
        if (i >= 0) {
            params = s.path.slice(i + 1);
            s.path = s.path.slice(0, i);
        }
    }
    return { ...s, params };
}

export function urlunparse({ scheme, netloc, path, params, query, fragment }) {
    let url = params ? `${path};${params}` : path;
    if (netloc || (["http", "https", "ftp", "ws", "wss", "file", "git", "svn", "sftp"].includes(scheme) && url.slice(0, 2) !== "//")) {
        if (url && url[0] !== "/") url = "/" + url;
        url = "//" + (netloc || "") + url;
    }
    if (scheme) url = scheme + ":" + url;
    if (query) url += "?" + query;
    if (fragment) url += "#" + fragment;
    return url;
}

/** urllib.parse.unquote_plus (UTF-8, invalid sequences replaced). */
function unquotePlus(s) {
    s = s.replace(/\+/g, " ");
    if (!s.includes("%")) return s;
    const bytes = [];
    let out = "";
    const flush = () => {
        if (bytes.length) {
            out += new TextDecoder("utf-8", { fatal: false }).decode(new Uint8Array(bytes));
            bytes.length = 0;
        }
    };
    for (let i = 0; i < s.length; i++) {
        if (s[i] === "%" && /^[0-9A-Fa-f]{2}$/.test(s.slice(i + 1, i + 3))) {
            bytes.push(parseInt(s.slice(i + 1, i + 3), 16));
            i += 2;
        } else {
            flush();
            out += s[i];
        }
    }
    flush();
    return out;
}

/** urllib.parse.quote_plus with safe="" (unreserved: letters, digits, _.-~). */
function quotePlus(s) {
    let out = "";
    for (const byte of new TextEncoder().encode(s)) {
        const c = String.fromCharCode(byte);
        if (/[A-Za-z0-9_.\-~]/.test(c)) out += c;
        else if (byte === 0x20) out += "+";
        else out += "%" + byte.toString(16).toUpperCase().padStart(2, "0");
    }
    return out;
}

/** parse_qsl(keep_blank_values=True). */
function parseQsl(query) {
    const pairs = [];
    for (const field of query.split("&")) {
        if (!field) continue;
        const eq = field.indexOf("=");
        const name = eq >= 0 ? field.slice(0, eq) : field;
        const value = eq >= 0 ? field.slice(eq + 1) : "";
        pairs.push([unquotePlus(name), unquotePlus(value)]);
    }
    return pairs;
}

/** Python's str comparison: by code point. */
function cmp(a, b) {
    const x = Array.from(a);
    const y = Array.from(b);
    for (let i = 0; i < Math.min(x.length, y.length); i++) {
        const d = x[i].codePointAt(0) - y[i].codePointAt(0);
        if (d) return d;
    }
    return x.length - y.length;
}

export function normalizeUrl(url) {
    const parsed = urlparse(pyStrip(url));
    const scheme = parsed.scheme.toLowerCase();
    let netloc = parsed.netloc.toLowerCase();
    if (netloc.startsWith("www.")) netloc = netloc.slice(4);
    if ((scheme === "http" && netloc.endsWith(":80")) || (scheme === "https" && netloc.endsWith(":443"))) {
        netloc = netloc.slice(0, netloc.lastIndexOf(":"));
    }
    let query = parsed.query;
    if (query) {
        const kept = parseQsl(query).filter(([k]) => !TRACKING_PARAMS.has(k.toLowerCase()) && !k.toLowerCase().startsWith("utm_"));
        kept.sort((a, b) => cmp(a[0], b[0]) || cmp(a[1], b[1]));
        query = kept.map(([k, v]) => `${quotePlus(k)}=${quotePlus(v)}`).join("&");
    }
    let path = parsed.path;
    if (path && path !== "/" && path.endsWith("/")) path = path.replace(/\/+$/, "");
    else if (!path) path = "/";
    return urlunparse({ scheme, netloc, path, params: parsed.params, query, fragment: "" });
}

/** sha256(f"{user_id}|{normalized_url}")[:32], as backend/url_utils.generate_page_id. */
export async function generatePageId(userId, normalizedUrl) {
    const data = new TextEncoder().encode(`${userId}|${normalizedUrl}`);
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", data));
    return Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}
