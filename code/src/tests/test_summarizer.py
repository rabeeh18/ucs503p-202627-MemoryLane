"""Turning Gemini's response into the summary text."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend import summarizer


def _response(*parts):
    """A response whose single candidate has these parts (str, or (str, thought))."""
    objs = []
    for p in parts:
        text, thought = (p, False) if isinstance(p, str) else p
        objs.append(SimpleNamespace(text=text, thought=thought))
    # .text joins with newlines, as google.generativeai's quick accessor does.
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=objs))],
        text="\n".join(o.text for o in objs),
    )


def test_parts_split_mid_word_are_joined_without_a_line_break():
    response = _response("The Try Guys hosted a debate where they humor", "ously argued about straws.")
    assert summarizer._response_text(response) == "The Try Guys hosted a debate where they humorously argued about straws."


def test_thought_parts_are_left_out():
    response = _response(("Let me think about this page...", True), "A short summary.")
    assert summarizer._response_text(response) == "A short summary."


def test_falls_back_to_the_sdk_text_without_parts():
    response = SimpleNamespace(candidates=[], text="Only text.")
    assert summarizer._response_text(response) == "Only text."


def test_summarize_returns_the_joined_text():
    model = MagicMock()
    model.generate_content.return_value = _response("Part one ", "and two.\n\nNew paragraph.")
    with patch("backend.summarizer._get_model", return_value=model):
        assert summarizer.summarize("q", "page text") == "Part one and two.\n\nNew paragraph."
