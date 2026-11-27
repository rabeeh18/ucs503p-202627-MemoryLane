// What a search query says about where and when a page was seen: a port of
// backend/query_intent.py (site words, time phrases, a typed URL). Dates are
// UTC, as on the server.
import { normalizeUrl, urlparse, urlunparse } from "./url.js";
import { pyRegex, pyStrip } from "./pytext.js";

const GENERIC_HOST_LABELS = new Set([
    "www", "m", "mobile", "en", "app", "web", "docs", "doc", "blog", "api", "dev",
    "developer", "developers", "support", "help", "news", "mail", "login", "auth",
    "accounts", "account", "community", "forum", "forums", "old", "new", "beta",
]);
const SECOND_LEVEL_SUFFIXES = new Set(["co", "com", "org", "net", "ac", "gov", "edu", "nic", "res", "gob"]);
const NICKNAMES = { wiki: "wikipedia", yt: "youtube", gh: "github", twitter: "x", insta: "instagram" };
const NICKNAME_TARGETS = new Set(Object.values(NICKNAMES));
const MIN_ALIAS_LENGTH = 3;

export const FILLER_WORDS = new Set([
    "a", "an", "the", "that", "this", "those", "these", "my", "i", "me", "we", "what", "which",
    "from", "on", "in", "at", "of", "about", "for", "with", "to", "by", "during", "back", "and",
    "page", "pages", "site", "website", "webpage", "article", "articles", "post", "posts",
    "thread", "threads", "video", "videos", "link", "links", "one", "thing", "stuff",
    "saved", "save", "read", "seen", "saw", "see", "visited", "visit", "opened", "open",
    "watched", "watch", "looked", "look", "looking", "found", "checked", "check", "viewed",
    "view", "browsed", "browse", "came", "across", "bookmarked",
    "was", "were", "is", "do", "did", "had", "have", "some", "something", "any",
]);

const MONTHS = {
    january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7,
    august: 8, september: 9, october: 10, november: 11, december: 12,
};
const MONTH_ABBR = { jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8, sep: 9, sept: 9, oct: 10, nov: 11, dec: 12 };
const NUMBERS = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, couple: 2, few: 3 };

const byLengthDesc = (list) => [...list].sort((a, b) => b.length - a.length);
const MONTH_NAME = byLengthDesc(Object.keys(MONTHS).concat(Object.keys(MONTH_ABBR))).join("|");
const FULL_MONTH = byLengthDesc(Object.keys(MONTHS)).join("|");
const ORDINAL = "(\\d{1,2})(?:st|nd|rd|th)?";
const NUMBER = "(\\d+|" + Object.keys(NUMBERS).join("|") + ")";

const WORD = /[a-z0-9]+/g;
const URL_LIKE = pyRegex("^(https?://)?([a-z0-9-]+\\.)+[a-z]{2,}(:\\d+)?(/\\S*)?$|^https?://\\S+$", "i");

const TIME_PATTERNS = [
    ["day", `\\b(?:on\\s+)?(?:the\\s+)?${ORDINAL}\\s+(?:of\\s+)?(${MONTH_NAME})\\b(?:\\s+(\\d{4}))?`],
    ["day_md", `\\b(?:on\\s+)?(${MONTH_NAME})\\s+${ORDINAL}\\b(?:,?\\s+(\\d{4}))?`],
    ["ago", `\\b(?:a\\s+)?${NUMBER}\\s+(day|week|month|year)s?\\s+ago\\b`],
    ["named", "\\b(today|yesterday|recently|lately)\\b"],
    ["this_last", "\\b(this|last|past|previous)\\s+(week|month|year|few days|couple of days)\\b"],
    ["month", `\\b(in|from|during|last|back in|early|late|mid)\\s+(${FULL_MONTH})\\b(?:\\s+(\\d{4}))?`],
    ["year", "\\b(in|from|during|back in)\\s+(20\\d\\d|19\\d\\d)\\b"],
].map(([kind, source]) => [kind, pyRegex(source, "g")]);
const SEEN = pyRegex("\\b(saved|save|read|seen|saw|visited|opened|watched|looked|found|bookmarked)\\b");

const DAY = 86400000;
const HOUR = 3600000;
const utc = (y, m, d) => Date.UTC(y, m - 1, d);

export function siteAliases(domain) {
    const host = domain.toLowerCase().split(":")[0].replace(/^\.+|\.+$/g, "");
    let labels = host.split(".");
    if (labels.length > 1) {
        labels = labels.slice(0, -1);
        if (labels.length > 1 && SECOND_LEVEL_SUFFIXES.has(labels[labels.length - 1])) labels = labels.slice(0, -1);
    }
    const label = labels.length ? labels[labels.length - 1] : "";
    const name = label.replace(/-/g, "");
    if (!name || GENERIC_HOST_LABELS.has(label) || FILLER_WORDS.has(name)) return [];
    if (name.length >= MIN_ALIAS_LENGTH || NICKNAME_TARGETS.has(name)) return [name];
    return [];
}

export function aliasIndex(domains) {
    const index = new Map();
    for (const domain of domains) {
        for (const alias of siteAliases(domain)) {
            if (!index.has(alias)) index.set(alias, new Set());
            index.get(alias).add(domain);
        }
    }
    return index;
}

function parts(ms) {
    const d = new Date(ms);
    return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() };
}

function monthsBack(now, month, year) {
    if (year) return year;
    const n = parts(now);
    return month <= n.month ? n.year : n.year - 1;
}

function monthRange(year, month) {
    return [utc(year, month, 1), utc(year + (month === 12 ? 1 : 0), (month % 12) + 1, 1)];
}

function dayRange(now, month, day, year) {
    const n = parts(now);
    const y = year || ((month < n.month || (month === n.month && day <= n.day)) ? n.year : n.year - 1);
    const start = utc(y, month, day);
    const check = new Date(start);
    if (y < 1 || y > 9999 || day < 1 || check.getUTCMonth() + 1 !== month || check.getUTCDate() !== day) return null;
    return [start - DAY, start + 2 * DAY];
}

const number = (word) => (/^\d+$/.test(word) ? parseInt(word, 10) : (NUMBERS[word] ?? 1));

function timeRange(kind, m, now, whole) {
    const today = now - (now % DAY);
    if (kind === "day" || kind === "day_md") {
        const [day, monthName, year] = kind === "day" ? [m[1], m[2], m[3]] : [m[2], m[1], m[3]];
        const month = MONTHS[monthName] || MONTH_ABBR[monthName];
        return dayRange(now, month, parseInt(day, 10), year ? parseInt(year, 10) : null);
    }
    if (kind === "ago") {
        const n = number(m[1]);
        const unit = m[2];
        const days = { day: 1, week: 7, month: 30, year: 365 }[unit] * n;
        const slack = { day: 1, week: 4, month: 15, year: 120 }[unit];
        const center = today - days * DAY;
        return [center - slack * DAY, center + (slack + 1) * DAY];
    }
    if (kind === "named") {
        const word = m[1];
        if (word === "today") return [today - 12 * HOUR, now + HOUR];
        if (word === "yesterday") return [today - 2 * DAY, today + DAY];
        return [now - 14 * DAY, now + HOUR];
    }
    if (kind === "this_last") {
        const [which, unit] = [m[1], m[2]];
        const span = { week: 7, month: 31, year: 366, "few days": 4, "couple of days": 3 }[unit];
        const back = which === "this" || unit === "few days" || unit === "couple of days" ? span : 2 * span;
        return [now - back * DAY, now + HOUR];
    }
    if (kind === "month") {
        const month = MONTHS[m[2]];
        let year = m[3] ? parseInt(m[3], 10) : null;
        if (m[1] === "last" && !year) year = month >= parts(now).month ? parts(now).year - 1 : parts(now).year;
        return monthRange(monthsBack(now, month, year), month);
    }
    if (kind === "year") {
        if (m[1] !== "from" && !SEEN.test(whole)) return null;
        const year = parseInt(m[2], 10);
        return [utc(year, 1, 1), utc(year + 1, 1, 1)];
    }
    return null;
}

function namesOneDay(kind, m) {
    return kind === "day" || kind === "day_md" || (kind === "named" && (m[1] === "today" || m[1] === "yesterday"))
        || (kind === "ago" && m[2] === "day");
}

function findTime(query, now) {
    for (const [kind, pattern] of TIME_PATTERNS) {
        pattern.lastIndex = 0;
        let m;
        while ((m = pattern.exec(query))) {
            const found = timeRange(kind, m, now, query);
            if (found) {
                const [start, end] = found;
                const near = namesOneDay(kind, m) ? start + (end - start) / 2 : null;
                return { start, end, near, span: [m.index, m.index + m[0].length] };
            }
            if (m[0] === "") pattern.lastIndex++;
        }
    }
    return null;
}

function urlIntent(query, domains) {
    const token = pyStrip(query);
    if (token.includes(" ") || !URL_LIKE.test(token)) return [null, new Set()];
    const parsed = urlparse(token.includes("://") ? token : "https://" + token);
    parsed.scheme = parsed.scheme.toLowerCase();
    parsed.netloc = parsed.netloc.toLowerCase();
    const host = parsed.netloc.startsWith("www.") ? parsed.netloc.slice(4) : parsed.netloc;
    const saved = new Set([...domains].filter((d) => d === host));
    const hasPath = !["", "/"].includes(parsed.path) || Boolean(parsed.query);
    return [hasPath ? normalizeUrl(urlunparse(parsed)) : null, saved];
}

/**
 * {text, domains, savedFrom, savedUntil, savedNear, url}; times are ms since
 * the epoch (UTC) or null. `domains` are the sites the user has saved pages from.
 */
export function parseQuery(query, domains, now = Date.now()) {
    let lowered = (query || "").toLowerCase();
    const intent = { text: "", domains: new Set(), savedFrom: null, savedUntil: null, savedNear: null, url: null };

    const [url, urlDomains] = urlIntent(query || "", domains);
    if (url || urlDomains.size) {
        intent.url = url;
        intent.domains = urlDomains;
        const path = url ? urlparse(url).path.toLowerCase() : "";
        intent.text = (path.match(WORD) || []).filter((w) => !FILLER_WORDS.has(w)).join(" ");
        return intent;
    }

    const time = findTime(lowered, now);
    if (time) {
        intent.savedFrom = time.start;
        intent.savedUntil = time.end;
        intent.savedNear = time.near;
        lowered = lowered.slice(0, time.span[0]) + " " + lowered.slice(time.span[1]);
    }

    const words = lowered.match(WORD) || [];
    const aliases = aliasIndex(domains);
    const used = words.map(() => false);
    for (const size of [3, 2, 1]) {
        for (let i = 0; i + size <= words.length; i++) {
            if (used.slice(i, i + size).some(Boolean)) continue;
            let name = words.slice(i, i + size).join("");
            if (size === 1) {
                if (name in NICKNAMES) name = NICKNAMES[name];
                else if (name.length < MIN_ALIAS_LENGTH) continue;
            }
            if (aliases.has(name)) {
                for (const d of aliases.get(name)) intent.domains.add(d);
                for (let k = i; k < i + size; k++) used[k] = true;
            }
        }
    }
    intent.text = words.filter((w, i) => !used[i] && !FILLER_WORDS.has(w)).join(" ");
    return intent;
}

export function isActive(intent) {
    return Boolean(intent.domains.size || intent.savedFrom !== null || intent.url);
}
