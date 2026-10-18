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


# ---- citations, junk lines, tables, description ------------------------------

from backend.cleaning import drop_junk_lines, extract_description, strip_citations, tidy_text  # noqa: E402

PROSE = "Sleep helps the brain consolidate memories formed during the day, researchers say."


def test_strip_citation_markers():
    text = "Sleep matters.[4] It helps memory[12][13] a lot[citation needed]. See note[a] too [Citation Needed]."
    assert strip_citations(text) == "Sleep matters. It helps memory a lot. See note too."


def test_strip_citations_keeps_ordinary_brackets():
    assert strip_citations("Use list[0] and [optional] args.") == "Use list[0] and [optional] args."


def test_drop_lines_that_are_symbols_or_single_words():
    text = "\n".join([PROSE, "----------", "Share", "| | |", "★ ★ ★ ★", "", "Two words"])
    assert drop_junk_lines(text) == "\n".join([PROSE, "", "Two words"])


def test_tidy_text_applies_everything():
    text = PROSE + "[3]\n\n•••\nMenu\n\n" + PROSE
    assert tidy_text(text) == PROSE + "\n\n" + PROSE


def test_tables_are_excluded_from_extraction():
    body = " ".join(f"Paragraph sentence number {i} explains the topic in detail." for i in range(12))
    html = (
        "<html><body><article><h1>Title</h1>"
        f"<p>{body}</p>"
        "<table><tr><td>TABLECELLALPHA</td><td>TABLECELLBETA</td></tr></table>"
        "</article></body></html>"
    )
    cleaned = clean_content(html, "fallback")
    assert "Paragraph sentence number 11" in cleaned
    assert "TABLECELLALPHA" not in cleaned


def test_description_prefers_meta_description():
    html = ('<html><head><meta name="description" content="A friendly guide to how sleep shapes memory.">'
            f"</head><body><p>{PROSE}</p></body></html>")
    assert extract_description(html, PROSE) == "A friendly guide to how sleep shapes memory."


def test_description_falls_back_to_first_prose_paragraph():
    cleaned = "Menu | Home\n\nShort line.\n\n" + PROSE + "\n\n" + PROSE
    assert extract_description(None, cleaned) == PROSE
    assert extract_description("<html><body></body></html>", cleaned) == PROSE


def test_description_is_capped_at_300_chars():
    long = " ".join(["This sentence is part of a very long opening paragraph."] * 12)
    description = extract_description(None, long)
    assert len(description) <= 301
    assert description.endswith("…")


def test_description_empty_when_nothing_qualifies():
    assert extract_description(None, "Home | About\nLogin") == ""
