import logging
import re

logger = logging.getLogger(__name__)

MIN_EXTRACTED_WORDS = 50


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs, strip each line, and cap blank lines at one."""
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n').replace(' ', ' ')
    lines = [re.sub(r'[ \t\f\v]+', ' ', line).strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def word_count(text: str) -> int:
    return len((text or '').split())


def extract_main_text(html: str) -> str | None:
    """Main article text from raw HTML via trafilatura, or None if extraction fails."""
    try:
        import trafilatura
        return trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception as e:
        logger.warning(f"trafilatura extraction failed: {e}")
        return None


def clean_content(html: str | None, text: str) -> str:
    """Prefer trafilatura's extraction of `html` when it yields at least 50 words;
    otherwise fall back to the extension-provided `text`."""
    if html and html.strip():
        extracted = extract_main_text(html)
        if extracted and word_count(extracted) >= MIN_EXTRACTED_WORDS:
            return normalize_whitespace(extracted)
    return normalize_whitespace(text)
