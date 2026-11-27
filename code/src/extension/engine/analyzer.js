// Solr's text_en analysis (Solr 9 _default configset), reproduced so that the
// local index and the server's Solr index see exactly the same words:
//
//   index:  standard tokenizer -> stop -> lowercase -> English possessive
//           -> keyword marker (protwords) -> Porter stem
//   query:  the same, with the synonym graph first
//
// Stop words leave a hole in the positions, as in Lucene, so phrase matching
// lines up with Solr's.

import { porterStem } from "./porter.js";

// lang/stopwords_en.txt from the _default configset, as shipped.
export const STOPWORDS = new Set([
    "stopworda", "stopwordb", "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "if",
    "in", "into", "is", "it", "no", "not", "of", "on", "or", "such", "that", "the", "their", "then",
    "there", "these", "they", "this", "to", "was", "will", "with",
]);

// protwords.txt: never stemmed.
const PROTECTED = new Set(["dontstems", "zwhacky"]);

// synonyms.txt (query side only). Each group's words are equivalent; "a => b"
// rules replace a with b. Matching ignores case.
const SYNONYM_GROUPS = [
    ["fooaaa", "baraaa", "bazaaa"],
    ["gb", "gib", "gigabyte", "gigabytes"],
    ["mb", "mib", "megabyte", "megabytes"],
    ["television", "televisions", "tv", "tvs"],
];
const SYNONYM_RULES = { aaafoo: ["aaabar"], cccfoo: ["cccbar", "cccbaz"], pixima: ["pixma"], bbbfoo: ["bbbfoo"] };

const SYNONYMS = new Map();
for (const group of SYNONYM_GROUPS) {
    for (const word of group) SYNONYMS.set(word, group);
}
for (const [word, out] of Object.entries(SYNONYM_RULES)) SYNONYMS.set(word, out);

const MAX_TOKEN_LENGTH = 255;

const segmenter = new Intl.Segmenter("en", { granularity: "word" });
const SPLIT_EACH = /[\p{Script=Han}\p{Script=Hiragana}]/u;
const EMOJI = /\p{Extended_Pictographic}/u;
const SOUTH_EAST_ASIAN = /^[\p{Script=Thai}\p{Script=Lao}\p{Script=Myanmar}\p{Script=Khmer}]+$/u;

/** Lower-case one code point at a time, as Java's Character.toLowerCase does. */
function lowerCase(token) {
    let out = "";
    for (const ch of token) {
        const cp = ch.codePointAt(0);
        if (cp < 128) {
            out += cp >= 65 && cp <= 90 ? String.fromCharCode(cp + 32) : ch;
        } else if (cp === 0x130) {
            out += "i"; // Java maps İ to a plain i
        } else {
            const lower = ch.toLowerCase();
            out += [...lower].length === 1 ? lower : ch;
        }
    }
    return out;
}

/** Words as Lucene's StandardTokenizer (UAX#29) would split them. */
export function tokenize(text) {
    const tokens = [];
    let seaEnd = -1; // end of the last South-East Asian word, to join runs as Lucene does
    for (const seg of segmenter.segment(text || "")) {
        const word = seg.segment;
        if (!seg.isWordLike) {
            if (EMOJI.test(word)) tokens.push(word);
            continue;
        }
        if (SOUTH_EAST_ASIAN.test(word)) {
            // Thai, Lao, Myanmar, Khmer: Lucene keeps an unbroken run as one token.
            if (seaEnd === seg.index && tokens.length) tokens[tokens.length - 1] += word;
            else tokens.push(word);
            seaEnd = seg.index + word.length;
            continue;
        }
        if (SPLIT_EACH.test(word)) {
            // Han and Hiragana: one token per character, as Lucene emits them.
            let run = "";
            for (const ch of word) {
                if (SPLIT_EACH.test(ch)) {
                    if (run) tokens.push(run);
                    run = "";
                    tokens.push(ch);
                } else {
                    run += ch;
                }
            }
            if (run) tokens.push(run);
            continue;
        }
        if (word.length > MAX_TOKEN_LENGTH) {
            for (let i = 0; i < word.length; i += MAX_TOKEN_LENGTH) tokens.push(word.slice(i, i + MAX_TOKEN_LENGTH));
        } else {
            tokens.push(word);
        }
    }
    return tokens;
}

function possessive(token) {
    if (token.length >= 2) {
        const last = token[token.length - 1];
        const apos = token[token.length - 2];
        if ((last === "s" || last === "S") && (apos === "'" || apos === "’" || apos === "＇")) {
            return token.slice(0, -2);
        }
    }
    return token;
}

function finish(token) {
    const lowered = possessive(lowerCase(token));
    return PROTECTED.has(lowered) ? lowered : porterStem(lowered);
}

/**
 * Index-time analysis: [{term, pos}] with positions counting stop words, so a
 * stop word leaves a gap.
 */
export function analyzeIndex(text) {
    const out = [];
    let pos = -1;
    for (const token of tokenize(text)) {
        pos++;
        if (STOPWORDS.has(lowerCase(token))) continue;
        const term = finish(token);
        if (term) out.push({ term, pos });
    }
    return out;
}

/**
 * Query-time analysis: positions, each with the terms that may stand there
 * (several when the synonym list expands a word). Stop words leave holes.
 * Returns [{terms: [...], pos}], terms possibly repeated as Lucene keeps them.
 */
export function analyzeQuery(text) {
    const out = [];
    let pos = -1;
    for (const token of tokenize(text)) {
        pos++;
        const lowered = lowerCase(token);
        const expanded = SYNONYMS.get(lowered);
        const words = expanded ? expanded : [token];
        const terms = [];
        for (const word of words) {
            if (STOPWORDS.has(lowerCase(word))) continue;
            const term = finish(word);
            if (term) terms.push(term);
        }
        if (terms.length) out.push({ terms, pos });
    }
    return out;
}
