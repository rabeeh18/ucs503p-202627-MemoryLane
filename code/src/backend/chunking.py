import logging
import re
from backend.config import CHUNK_MAX_WORDS, CHUNK_MIN_WORDS, CHUNK_OVERLAP_WORDS

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')


def _units(text: str, max_words: int) -> list[tuple[str, int, bool]]:
    """Split text into sentence units: (text, word_count, starts_paragraph).
    Sentences longer than max_words are hard-split into max_words pieces."""
    units = []
    for para in re.split(r'\n\s*\n', text.strip()):
        first = True
        for sentence in _SENTENCE_SPLIT.split(para.strip()):
            words = sentence.split()
            for i in range(0, len(words), max_words):
                piece = words[i:i + max_words]
                units.append((' '.join(piece), len(piece), first))
                first = False
    return units


def _join(units: list[tuple[str, int, bool]]) -> str:
    out = ''
    for i, (sentence, _, starts_para) in enumerate(units):
        if i:
            out += '\n\n' if starts_para else ' '
        out += sentence
    return out


def _overlap(units: list[tuple[str, int, bool]], overlap_words: int) -> list[tuple[str, int, bool]]:
    """Trailing sentences of a chunk totalling at most overlap_words. If even the
    last sentence is longer, use its last overlap_words words."""
    if overlap_words <= 0 or not units:
        return []
    tail, total = [], 0
    for unit in reversed(units):
        if total + unit[1] > overlap_words:
            break
        tail.insert(0, unit)
        total += unit[1]
    if not tail:
        words = units[-1][0].split()[-overlap_words:]
        tail = [(' '.join(words), len(words), False)]
    return [(t, n, False) for t, n, _ in tail]


def chunk_text(text: str, max_words: int = None, min_words: int = None,
               overlap_words: int = None) -> list[str]:
    """Pack sentences into chunks of at most max_words words.

    Each chunk after the first starts with the trailing sentences of the previous
    chunk (about overlap_words words). A final chunk with fewer than min_words new
    words is merged into the previous chunk, so that one chunk may exceed
    max_words by less than min_words. Empty input returns [].
    """
    if max_words is None:
        max_words = CHUNK_MAX_WORDS
    if min_words is None:
        min_words = CHUNK_MIN_WORDS
    if overlap_words is None:
        overlap_words = CHUNK_OVERLAP_WORDS
    overlap_words = min(overlap_words, max_words // 2)

    if not text or not text.strip():
        return []

    # Each chunk: (units, number of leading overlap units)
    chunks: list[tuple[list, int]] = []
    current, current_overlap, count = [], 0, 0

    for unit in _units(text, max_words):
        if current and count + unit[1] > max_words and count > sum(u[1] for u in current[:current_overlap]):
            chunks.append((current, current_overlap))
            current = _overlap(current, overlap_words)
            # Drop overlap from the front until the new sentence fits.
            while current and sum(u[1] for u in current) + unit[1] > max_words:
                current.pop(0)
            current_overlap = len(current)
            count = sum(u[1] for u in current)
        current.append(unit)
        count += unit[1]

    if current:
        chunks.append((current, current_overlap))

    if len(chunks) > 1:
        last_units, last_overlap = chunks[-1]
        new_words = sum(u[1] for u in last_units[last_overlap:])
        if new_words < min_words:
            chunks.pop()
            prev_units, prev_overlap = chunks[-1]
            chunks[-1] = (prev_units + last_units[last_overlap:], prev_overlap)

    return [_join(units) for units, _ in chunks]
