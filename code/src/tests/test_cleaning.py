from unittest.mock import patch

from backend.cleaning import clean_content, normalize_whitespace

ARTICLE = " ".join(f"word{i}" for i in range(80))
FALLBACK = "Fallback   text\t from the extension."


def test_uses_trafilatura_when_it_extracts_enough_words():
    with patch("backend.cleaning.extract_main_text", return_value=ARTICLE) as mock_extract:
        assert clean_content("<html>...</html>", FALLBACK) == ARTICLE
    mock_extract.assert_called_once_with("<html>...</html>")


def test_falls_back_to_text_when_extraction_is_short():
    with patch("backend.cleaning.extract_main_text", return_value="too short"):
        assert clean_content("<html></html>", FALLBACK) == "Fallback text from the extension."


def test_falls_back_to_text_without_html():
    with patch("backend.cleaning.extract_main_text") as mock_extract:
        assert clean_content(None, FALLBACK) == "Fallback text from the extension."
    mock_extract.assert_not_called()


def test_falls_back_when_extraction_fails():
    with patch("backend.cleaning.extract_main_text", return_value=None):
        assert clean_content("<html></html>", FALLBACK) == "Fallback text from the extension."


def test_real_trafilatura_extracts_article_body():
    body = " ".join(f"Sentence number {i} talks about memory and sleep." for i in range(20))
    html = (
        "<html><head><title>T</title></head><body>"
        "<nav>Home About Contact Login</nav>"
        f"<article><h1>Sleep and memory</h1><p>{body}</p></article>"
        "<footer>Copyright footer links</footer></body></html>"
    )
    cleaned = clean_content(html, "fallback")
    assert "Sentence number 19" in cleaned
    assert "Copyright footer" not in cleaned


def test_normalize_whitespace_collapses_blank_lines_and_spaces():
    text = "a  \t b\r\n\r\n\r\n\r\nc d\n\n\n"
    assert normalize_whitespace(text) == "a b\n\nc d"
