// The parts of backend/cleaning.py that search uses (snippets, keyword coverage).
import { WS, cpLen, cpSlice, isAlpha, isSpace, pySplit, pyStrip } from "./pytext.js";

const CITATION = new RegExp(
    "\\[(?:[1-9]\\d{0,3}(?:\\s*[,–-]\\s*\\d{1,4})*|[a-z]|note \\d+|nb \\d+|citation needed|clarification needed"
    + "|according to whom\\?|by whom\\?|who\\?|when\\?|which\\?|where\\?|dubious[^\\]]{0,20}|failed verification"
    + "|better source needed|verification needed|page needed|full citation needed|original research\\?)\\]",
    "giu",
);

export function stripCitations(text) {
    return (text || "").replace(CITATION, "").replace(/[ \t]+([.,;:!?])/gu, "$1");
}

export function letterRatio(text) {
    let total = 0;
    let letters = 0;
    for (const ch of text) {
        if (isSpace(ch)) continue;
        total++;
        if (isAlpha(ch)) letters++;
    }
    return total ? letters / total : 0;
}

const PROSE_END = /[.!?…]["'”’)\]]?$/u;

/** A readable sentence: 8+ words, 70% letters, no table pipes, ends like a sentence. */
export function isProse(sentence) {
    const s = pyStrip(sentence || "");
    return pySplit(s).length >= 8 && letterRatio(s) >= 0.7 && !s.includes("|") && PROSE_END.test(s);
}

const TRIM_CHARS = new Set([" ", ",", ";", ":", "-", "–"]);

/** Cut to at most maxChars (plus an ellipsis) at a word boundary. */
export function trimAtWord(text, maxChars) {
    const t = pyStrip(text || "");
    if (cpLen(t) <= maxChars) return t;
    let cut = cpSlice(t, 0, maxChars);
    const chars = Array.from(cut);
    const space = chars.lastIndexOf(" ");
    if (space > Math.floor(maxChars / 2)) cut = chars.slice(0, space).join("");
    const out = Array.from(cut);
    while (out.length && TRIM_CHARS.has(out[out.length - 1])) out.pop();
    return out.join("") + "…";
}

export { WS };
