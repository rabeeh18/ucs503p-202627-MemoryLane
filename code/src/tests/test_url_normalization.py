from backend.url_utils import normalize_url, generate_webpage_id


def test_lowercase_scheme_and_host():
    assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_strip_www():
    assert normalize_url("https://www.example.com/page") == "https://example.com/page"


def test_strip_tracking_params():
    url = (
        "https://example.com/a?utm_source=x&utm_medium=y&utm_custom=z"
        "&fbclid=1&gclid=2&ref=home&ref_src=tw&keep=yes"
    )
    normalized = normalize_url(url)
    assert "utm_" not in normalized
    assert "fbclid" not in normalized
    assert "gclid" not in normalized
    assert "ref=" not in normalized
    assert "ref_src" not in normalized
    assert "keep=yes" in normalized


def test_remove_fragment():
    assert normalize_url("https://example.com/page#section") == "https://example.com/page"


def test_remove_trailing_slash():
    assert normalize_url("https://example.com/page/") == "https://example.com/page"


def test_root_path_kept():
    assert normalize_url("https://example.com") == "https://example.com/"
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_sort_query_params():
    assert normalize_url("https://example.com/a?b=2&a=1") == "https://example.com/a?a=1&b=2"


def test_webpage_id_deterministic():
    url = normalize_url("https://www.example.com/docs/guide?utm_source=x")
    first = generate_webpage_id(url)
    second = generate_webpage_id(url)
    assert first == second
    assert "example.com" in first


def test_webpage_id_solr_safe():
    url = normalize_url("https://example.com/path with spaces/and?q=1")
    webpage_id = generate_webpage_id(url)
    assert " " not in webpage_id
    assert "/" not in webpage_id


def test_webpage_id_truncated_with_hash():
    long_path = "/".join(["segment"] * 80)
    url = normalize_url(f"https://example.com{long_path}")
    webpage_id = generate_webpage_id(url)
    assert len(webpage_id) <= 200
    assert "_" in webpage_id
