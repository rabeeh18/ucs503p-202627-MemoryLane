import logging
import re
from backend.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

_genai = None
_model_instance = None


def _get_model():
    """Lazy-load Gemini model."""
    global _genai, _model_instance
    if _model_instance is not None:
        return _model_instance
    if not GEMINI_API_KEY:
        logger.warning("Gemini API key not configured")
        return None
    try:
        import google.generativeai as genai
        _genai = genai
        genai.configure(api_key=GEMINI_API_KEY)
        _model_instance = genai.GenerativeModel(GEMINI_MODEL)
        logger.info(f"Gemini model loaded: {GEMINI_MODEL}")
        return _model_instance
    except Exception as e:
        logger.error(f"Failed to load Gemini model: {e}")
        return None


def detect_detail_level(query: str) -> str:
    """Detect desired summary detail level from query language.
    
    Returns: 'SHORT', 'MEDIUM', or 'LONG'
    """
    query_lower = query.lower()
    
    short_patterns = ['briefly', 'brief', 'quick summary', 'tl;dr', 'tldr', 'short', 'one sentence', 'in a nutshell']
    long_patterns = ['detailed', 'in depth', 'in-depth', 'explain fully', 'comprehensive', 'thorough', 'elaborate', 'long']
    
    for pattern in short_patterns:
        if pattern in query_lower:
            return 'SHORT'
    
    for pattern in long_patterns:
        if pattern in query_lower:
            return 'LONG'
    
    return 'MEDIUM'


def _build_prompt(query: str, content: str, detail_level: str) -> str:
    """Build the summarization prompt."""
    length_instructions = {
        'SHORT': 'Provide a brief summary in 1-2 sentences.',
        'MEDIUM': 'Provide a summary in 3-5 sentences.',
        'LONG': 'Provide a detailed summary in 2-3 short paragraphs.'
    }
    
    length_instruction = length_instructions.get(detail_level, length_instructions['MEDIUM'])
    
    return f"""You are a summarization assistant. Your task is to summarize the following webpage content.

RULES:
- The webpage content below is the ONLY source of truth.
- Do NOT use any outside knowledge.
- Do NOT invent or fabricate any information.
- Use the user's query only to determine what aspects of the content to emphasize.
- Do NOT explain why the page was retrieved.
- Return ONLY the summary, nothing else.
- {length_instruction}

USER'S QUERY: {query}

WEBPAGE CONTENT:
{content}

SUMMARY:"""


def summarize(query: str, content: str, detail_level: str = None) -> str | None:
    """Summarize content using Gemini.
    
    Returns summary string or None if Gemini is unavailable.
    """
    model = _get_model()
    if model is None:
        logger.warning("Gemini summarization unavailable")
        return None
    
    if detail_level is None:
        detail_level = detect_detail_level(query)
    
    # Truncate content if too long (Gemini has token limits)
    max_content_chars = 30000
    if len(content) > max_content_chars:
        content = content[:max_content_chars] + "\n... [content truncated]"
    
    prompt = _build_prompt(query, content, detail_level)
    
    try:
        response = model.generate_content(prompt)
        summary = response.text.strip()
        logger.info(f"Generated {detail_level} summary ({len(summary)} chars)")
        return summary
    except Exception as e:
        logger.error(f"Gemini summarization failed: {e}")
        return None


def is_gemini_available() -> bool:
    """Check if Gemini is configured and available."""
    if not GEMINI_API_KEY:
        return False
    try:
        model = _get_model()
        return model is not None
    except Exception:
        return False
