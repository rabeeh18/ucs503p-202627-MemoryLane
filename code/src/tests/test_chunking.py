from backend.chunking import chunk_text


def _words(n, prefix="word"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_short_content_single_chunk():
    text = _words(50)
    chunks = chunk_text(text, min_words=300, max_words=500)
    assert len(chunks) == 1
    assert chunks[0].split() == text.split()


def test_empty_content():
    assert chunk_text("") == [""]
    assert chunk_text("   ") == [""]


def test_huge_paragraph_split_by_sentences():
    sentences = [f"{_words(80, prefix=f's{i}w')}." for i in range(8)]
    text = " ".join(sentences)
    chunks = chunk_text(text, min_words=300, max_words=500)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.split()) <= 500


def test_many_paragraphs_accumulate():
    paragraphs = [_words(80, prefix=f"p{i}w") for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, min_words=300, max_words=500)
    assert len(chunks) >= 2
    for chunk in chunks[:-1]:
        assert 80 <= len(chunk.split()) <= 500


def test_very_long_sentence_hard_split():
    text = _words(1200, prefix="tok")
    chunks = chunk_text(text, min_words=300, max_words=500)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.split()) <= 500


def test_tiny_final_chunk_merged():
    first = _words(500, prefix="a")
    tiny = _words(20, prefix="b")
    text = first + "\n\n" + tiny
    chunks = chunk_text(text, min_words=300, max_words=500)
    assert len(chunks) == 1
    assert "b0" in chunks[0]


def test_deterministic_output():
    text = "\n\n".join(_words(120, prefix=f"p{i}w") for i in range(6))
    assert chunk_text(text) == chunk_text(text)
