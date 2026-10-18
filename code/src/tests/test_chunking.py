from backend.chunking import chunk_text


def _sentence(n, prefix):
    return " ".join(f"{prefix}{i}" for i in range(n)) + "."


def _sentences(count, words_each, prefix="s"):
    return " ".join(_sentence(words_each, f"{prefix}{j}w") for j in range(count))


def test_empty_content_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_content_single_chunk():
    text = _sentences(3, 10)
    chunks = chunk_text(text, max_words=150, min_words=40, overlap_words=30)
    assert chunks == [text]


def test_max_size_respected():
    text = _sentences(40, 12)  # 480 words
    chunks = chunk_text(text, max_words=150, min_words=40, overlap_words=30)
    assert len(chunks) >= 3
    for chunk in chunks[:-1]:
        assert len(chunk.split()) <= 150


def test_overlap_present():
    text = _sentences(30, 10)
    chunks = chunk_text(text, max_words=100, min_words=20, overlap_words=30)
    assert len(chunks) >= 2
    for prev, nxt in zip(chunks, chunks[1:]):
        prev_sentences = prev.split(". ")
        # The next chunk starts with the last sentences of the previous chunk
        assert nxt.startswith(prev_sentences[-1].rstrip(".")) or prev_sentences[-1] in nxt
        overlap = set(prev.split()) & set(nxt.split())
        assert 10 <= len(overlap) <= 30


def test_overlap_from_a_long_last_sentence_uses_its_tail_words():
    long_sentence = _sentence(90, "long")
    text = long_sentence + " " + _sentence(60, "next")
    chunks = chunk_text(text, max_words=100, min_words=10, overlap_words=30)
    assert len(chunks) == 2
    assert chunks[1].startswith("long60 ")
    assert len(chunks[1].split()) == 90


def test_overlap_dropped_when_it_would_exceed_max():
    text = _sentence(90, "long") + " " + _sentence(80, "next")
    chunks = chunk_text(text, max_words=100, min_words=10, overlap_words=30)
    assert len(chunks) == 2
    assert chunks[1].startswith("next0 ")
    assert all(len(c.split()) <= 100 for c in chunks)


def test_very_long_sentence_hard_split():
    text = " ".join(f"tok{i}" for i in range(1000))
    chunks = chunk_text(text, max_words=150, min_words=40, overlap_words=30)
    assert len(chunks) >= 7
    for chunk in chunks[:-1]:
        assert len(chunk.split()) <= 150
    # Every word survives
    assert {w for c in chunks for w in c.split()} == {f"tok{i}" for i in range(1000)}


def test_short_tail_merged_into_previous_chunk():
    text = _sentences(15, 10) + " " + _sentence(5, "tail")  # 150 + 5 words
    chunks = chunk_text(text, max_words=150, min_words=40, overlap_words=30)
    assert len(chunks) == 1
    assert "tail0" in chunks[0]
    assert chunks[0].count("s0w0 ") == 1


def test_merged_tail_does_not_duplicate_overlap():
    text = _sentences(15, 10) + " " + _sentence(20, "tail")
    chunks = chunk_text(text, max_words=100, min_words=40, overlap_words=30)
    words = [w for c in chunks for w in c.split()]
    assert words.count("tail0") == 1
    assert "tail19." in chunks[-1]


def test_paragraph_breaks_kept_inside_chunks():
    text = _sentence(10, "a") + "\n\n" + _sentence(10, "b")
    chunks = chunk_text(text, max_words=150, min_words=5, overlap_words=0)
    assert chunks == [_sentence(10, "a") + "\n\n" + _sentence(10, "b")]


def test_deterministic_output():
    text = "\n\n".join(_sentences(5, 20, prefix=f"p{i}") for i in range(6))
    assert chunk_text(text) == chunk_text(text)
