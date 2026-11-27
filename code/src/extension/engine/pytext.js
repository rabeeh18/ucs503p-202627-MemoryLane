// Python string semantics the ported search code relies on, so the browser
// splits, measures and matches text exactly as the server's Python does.

// Characters str.split() and re's \s treat as whitespace.
export const WS = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
// re's \w for str patterns: letters, digits/numbers, underscore.
export const W = "\\p{L}\\p{N}_";

/** str.split() with no arguments. */
export function pySplit(text) {
    return (text || "").split(new RegExp(`[${WS}]+`, "u")).filter(Boolean);
}

/** str.strip() with no arguments. */
export function pyStrip(text) {
    return (text || "").replace(new RegExp(`^[${WS}]+|[${WS}]+$`, "gu"), "");
}

/** len() of a str: code points, not UTF-16 units. */
export function cpLen(text) {
    let n = 0;
    for (const _ of text || "") n++;
    return n;
}

/** text[start:end] by code points. */
export function cpSlice(text, start, end) {
    return Array.from(text || "").slice(start, end).join("");
}

/** re.findall(r"\w+", text). */
export function words(text) {
    return (text || "").match(new RegExp(`[${W}]+`, "gu")) || [];
}

/** str.isalpha() for one code point. */
export function isAlpha(ch) {
    return /^\p{L}$/u.test(ch);
}

/** str.isspace() for one code point. */
export function isSpace(ch) {
    return new RegExp(`^[${WS}]$`, "u").test(ch);
}

/**
 * Translate a Python regex source to JavaScript: \b becomes a Unicode word
 * boundary and \s Python's whitespace, as Python matches them on str.
 */
export function pyRegex(source, flags = "") {
    const translated = source
        .replace(/\\b/g, `(?:(?<=[${W}])(?![${W}])|(?<![${W}])(?=[${W}]))`)
        .replace(/\\s/g, `[${WS}]`)
        .replace(/\\S/g, `[^${WS}]`);
    return new RegExp(translated, flags.includes("u") ? flags : flags + "u");
}
