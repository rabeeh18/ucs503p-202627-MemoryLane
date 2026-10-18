import logging
import re

logger = logging.getLogger(__name__)

MIN_EXTRACTED_WORDS = 50
DESCRIPTION_MAX_CHARS = 300

# Wikipedia-style citation and maintenance markers: [4], [12][13], [a], [citation needed], [note 2]
_CITATION = re.compile(
    r"\[(?:[1-9]\d{0,3}(?:\s*[,–-]\s*\d{1,4})*|[a-z]|note \d+|nb \d+|citation needed|clarification needed"
    r"|according to whom\?|by whom\?|who\?|when\?|which\?|where\?|dubious[^\]]{0,20}|failed verification"
    r"|better source needed|verification needed|page needed|full citation needed|original research\?)\]",
    re.IGNORECASE,
)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs, strip each line, and cap blank lines at one."""
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n').replace(' ', ' ')
    lines = [re.sub(r'[ \t\f\v]+', ' ', line).strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def word_count(text: str) -> int:
    return len((text or '').split())


def strip_citations(text: str) -> str:
    """Remove citation markers such as [4] and [citation needed]."""
    return re.sub(r"[ \t]+([.,;:!?])", r"\1", _CITATION.sub("", text or ""))


def letter_ratio(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(c.isalpha() for c in chars) / len(chars)


def _is_junk_line(line: str) -> bool:
    """A line that is mostly symbols (dividers, table rules, icon rows) or a single word."""
    stripped = line.strip()
    if not stripped:
        return False  # blank lines separate paragraphs
    return len(stripped.split()) <= 1 or letter_ratio(stripped) < 0.5


def drop_junk_lines(text: str) -> str:
    return '\n'.join(line for line in (text or '').split('\n') if not _is_junk_line(line))


def tidy_text(text: str) -> str:
    """Citation markers out, junk lines out, whitespace normalized."""
    return normalize_whitespace(drop_junk_lines(strip_citations(normalize_whitespace(text))))


def extract_main_text(html: str) -> str | None:
    """Main article text from raw HTML via trafilatura, or None if extraction fails."""
    try:
        import trafilatura
        return trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
    except Exception as e:
        logger.warning(f"trafilatura extraction failed: {e}")
        return None


def clean_content(html: str | None, text: str) -> str:
    """Prefer trafilatura's extraction of `html` when it yields at least 50 words;
    otherwise fall back to the extension-provided `text`. Either way citation
    markers and symbol-only / single-word lines are removed."""
    if html and html.strip():
        extracted = extract_main_text(html)
        if extracted:
            extracted = tidy_text(extracted)
            if word_count(extracted) >= MIN_EXTRACTED_WORDS:
                return extracted
    return tidy_text(text)


def is_prose(sentence: str) -> bool:
    """A readable sentence: 8+ words, at least 70% letters, no table pipes, ends
    with sentence punctuation (optionally followed by a closing quote/bracket)."""
    s = (sentence or '').strip()
    return (
        len(s.split()) >= 8
        and letter_ratio(s) >= 0.7
        and '|' not in s
        and re.search(r'[.!?…]["\'”’)\]]?$', s) is not None
    )


def trim_at_word(text: str, max_chars: int) -> str:
    """Cut to at most max_chars (plus an ellipsis) at a word boundary."""
    text = (text or '').strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    space = cut.rfind(' ')
    if space > max_chars // 2:
        cut = cut[:space]
    return cut.rstrip(' ,;:-–') + '…'


def _meta_description(html: str) -> str:
    try:
        import trafilatura
        meta = trafilatura.extract_metadata(html)
        return (getattr(meta, 'description', None) or '').strip() if meta else ''
    except Exception as e:
        logger.debug(f"trafilatura metadata failed: {e}")
        return ''


def first_prose_paragraph(text: str) -> str:
    """The first paragraph whose text reads as prose (see is_prose)."""
    for paragraph in re.split(r'\n\s*\n|\n', text or ''):
        paragraph = re.sub(r'\s+', ' ', paragraph).strip()
        if is_prose(paragraph):
            return paragraph
    return ''


def extract_description(html: str | None, cleaned_text: str) -> str:
    """Page description for snippets: the meta description, otherwise the first
    clean prose paragraph, at most 300 characters. Empty when neither exists."""
    description = _meta_description(html) if html and html.strip() else ''
    description = re.sub(r'\s+', ' ', strip_citations(description)).strip()
    if len(description.split()) < 4:
        description = first_prose_paragraph(cleaned_text)
    return trim_at_word(description, DESCRIPTION_MAX_CHARS)
