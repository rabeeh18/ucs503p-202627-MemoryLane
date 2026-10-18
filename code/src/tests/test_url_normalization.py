from backend.url_utils import normalize_url, generate_page_id


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


def test_page_id_deterministic():
    url = normalize_url("https://www.example.com/docs/guide?utm_source=x")
    first = generate_page_id("user-1", url)
    second = generate_page_id("user-1", url)
    assert first == second
    assert len(first) == 32
    assert all(c in "0123456789abcdef" for c in first)


def test_page_id_differs_per_user():
    url = normalize_url("https://example.com/a")
    assert generate_page_id("user-a", url) != generate_page_id("user-b", url)


def test_page_id_is_solr_safe_for_any_url():
    url = normalize_url("https://example.com/path with spaces/and?q=1")
    page_id = generate_page_id("u", url)
    assert " " not in page_id and "/" not in page_id and '"' not in page_id
