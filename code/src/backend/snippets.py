"""Search-result snippets.

A snippet is 2-3 consecutive readable sentences from the result's best chunk,
around the sentence that best matches the query, aiming for 200-280 characters.
The best sentence is the one matching the most distinct query terms; ties
(including "no sentence matches") go to the sentence most similar to the query
by embedding. Pages with no readable sentence fall back to their stored
description, and to nothing when that is empty. Snippets are plain text; the
frontend bolds the query terms.
"""
import logging
import re
from collections import OrderedDict
from typing import Callable, Sequence

from backend.cleaning import is_prose, strip_citations, trim_at_word

logger = logging.getLogger(__name__)

SNIPPET_MIN_CHARS = 200
SNIPPET_MAX_CHARS = 280
MAX_SNIPPET_SENTENCES = 3
MAX_TIE_CANDIDATES = 12

# Very common words that would otherwise match almost every sentence.
_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had",
    "her", "was", "one", "our", "out", "has", "have", "his", "how", "its", "who",
    "did", "get", "him", "she", "too", "use", "that", "this", "with", "from",
    "they", "them", "then", "than", "what", "when", "where", "which", "about",
    "into", "your", "some", "there", "their", "were", "been", "does", "also",
}

_WORD = re.compile(r"\w+")


def query_terms(query: str) -> list[str]:
    terms = []
    for term in _WORD.findall((query or "").lower()):
        if len(term) >= 3 and term not in _STOPWORDS and term not in terms:
            terms.append(term)
    return terms


def split_sentences(text: str) -> list[str]:
    """Sentences in reading order; line breaks also end a sentence."""
    parts = re.split(r"(?<=[.!?…])[\"'”’)\]]?\s+|\n+", strip_citations(text or ""))
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and p.strip()]


def term_score(sentence: str, terms: Sequence[str]) -> int:
    """Number of distinct query terms that prefix-match a word in the sentence."""
    words = _WORD.findall(sentence.lower())
    return sum(1 for t in terms if any(w.startswith(t) for w in words))


def window(sentences: Sequence[str], eligible: Sequence[bool], best: int,
           min_chars: int = SNIPPET_MIN_CHARS, max_chars: int = SNIPPET_MAX_CHARS) -> str:
    """Grow a run of consecutive eligible sentences around `best` (next first,
    then previous) until it reaches min_chars, without passing max_chars or
    MAX_SNIPPET_SENTENCES."""
    lo = hi = best
    text_len = len(sentences[best])
    if text_len > max_chars:
        return trim_at_word(sentences[best], max_chars)
    while text_len < min_chars and hi - lo + 1 < MAX_SNIPPET_SENTENCES:
        grown = False
        for j in (hi + 1, lo - 1):
            if 0 <= j < len(sentences) and eligible[j] and text_len + 1 + len(sentences[j]) <= max_chars:
                if j > hi:
                    hi = j
                else:
                    lo = j
                text_len += 1 + len(sentences[j])
                grown = True
                break
        if not grown:
            break
    return " ".join(sentences[lo:hi + 1])


class _Plan:
    """Per-result state between choosing candidates and building the snippet."""

    def __init__(self, sentences, eligible, candidates, description):
        self.sentences = sentences
        self.eligible = eligible
        self.candidates = candidates  # indices tied on term score
        self.description = description
        self.best = candidates[0] if candidates else None


def _plan(text: str, description: str | None, terms: Sequence[str]) -> _Plan:
    sentences = split_sentences(text)
    eligible = [is_prose(s) for s in sentences]
    indices = [i for i, ok in enumerate(eligible) if ok]
    if not indices:
        return _Plan(sentences, eligible, [], description)
    scores = {i: term_score(sentences[i], terms) for i in indices}
    top = max(scores.values())
    tied = [i for i in indices if scores[i] == top][:MAX_TIE_CANDIDATES]
    return _Plan(sentences, eligible, tied, description)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def build_snippets(items: Sequence[tuple[str, str | None]], query: str,
                   query_vector: Sequence[float] | None = None,
                   embed: Callable[[list[str]], list[Sequence[float]]] | None = None) -> list[str | None]:
    """Snippets for (chunk_text, description) pairs. Tied candidate sentences
    across all items are embedded in one `embed` call and compared with the
    (normalized) `query_vector`; without them the first tied sentence wins."""
    terms = query_terms(query)
    plans = [_plan(text, description, terms) for text, description in items]

    tie_texts = []
    if query_vector is not None and embed is not None:
        for plan in plans:
            if len(plan.candidates) > 1:
                tie_texts.extend(plan.sentences[i] for i in plan.candidates)
    if tie_texts:
        unique = list(dict.fromkeys(tie_texts))
        try:
            vectors = dict(zip(unique, embed(unique)))
        except Exception as e:  # snippets must never break search
            logger.warning(f"Snippet sentence embedding failed: {e}")
            vectors = {}
        for plan in plans:
            if vectors and len(plan.candidates) > 1:
                plan.best = max(
                    plan.candidates,
                    key=lambda i: _dot(vectors.get(plan.sentences[i], ()), query_vector),
                )

    snippets = []
    for plan in plans:
        if plan.best is not None:
            snippets.append(window(plan.sentences, plan.eligible, plan.best))
        else:
            fallback = re.sub(r"\s+", " ", plan.description or "").strip()
            snippets.append(trim_at_word(fallback, SNIPPET_MAX_CHARS) or None)
    return snippets


def build_snippet(text: str, query: str, description: str | None = None) -> str | None:
    """Single-result convenience wrapper (term match only, no embeddings)."""
    return build_snippets([(text, description)], query)[0]


class SentenceEmbeddingCache:
    """Small LRU of sentence embeddings so repeated searches don't re-encode."""

    def __init__(self, encode: Callable[[list[str]], list[Sequence[float]]], max_items: int = 4096):
        self._encode = encode
        self._max = max_items
        self._items: OrderedDict[str, tuple[float, ...]] = OrderedDict()

    def __call__(self, texts: list[str]) -> list[tuple[float, ...]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._items]
        if missing:
            for text, vector in zip(missing, self._encode(missing)):
                self._items[text] = tuple(vector)
        out = []
        for text in texts:
            self._items.move_to_end(text)
            out.append(self._items[text])
        while len(self._items) > self._max:
            self._items.popitem(last=False)
        return out
