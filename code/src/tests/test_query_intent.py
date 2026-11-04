"""Site words, time phrases and URLs in search queries."""
from datetime import datetime, timezone

import pytest

from backend.query_intent import alias_index, parse_query, site_aliases

NOW = datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)
DOMAINS = [
    "en.wikipedia.org", "reddit.com", "rottentomatoes.com", "docs.nvidia.com", "nvidia.com",
    "github.com", "youtube.com", "bbc.co.uk", "x.com", "localhost:5173", "antigravity.google",
]


def day(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@pytest.mark.parametrize("domain, aliases", [
    ("en.wikipedia.org", {"wikipedia"}),
    ("docs.nvidia.com", {"nvidia"}),
    ("rotten-tomatoes.com", {"rottentomatoes"}),
    ("bbc.co.uk", {"bbc"}),
    ("localhost:5173", {"localhost"}),
    ("antigravity.google", {"antigravity"}),
    ("x.com", {"x"}),
    ("m.ab.com", set()),
])
def test_site_aliases(domain, aliases):
    assert site_aliases(domain) == aliases


def test_alias_groups_subdomains():
    assert alias_index(DOMAINS)["nvidia"] == {"docs.nvidia.com", "nvidia.com"}


@pytest.mark.parametrize("query, domains, text", [
    ("reddit post about rust lifetimes", {"reddit.com"}, "rust lifetimes"),
    ("dune reviews on rotten tomatoes", {"rottentomatoes.com"}, "dune reviews"),
    ("wiki article on GPUs", {"en.wikipedia.org"}, "gpus"),
    ("nvidia docs on cuda graphs", {"docs.nvidia.com", "nvidia.com"}, "docs cuda graphs"),
    ("that tweet from twitter", {"x.com"}, "tweet"),
    ("nvidia website", {"docs.nvidia.com", "nvidia.com"}, ""),
])
def test_site_words(query, domains, text):
    intent = parse_query(query, DOMAINS, NOW)
    assert intent.domains == domains
    assert intent.text == text
    assert intent.active


@pytest.mark.parametrize("query", [
    "how lifetimes work in rust",  # no site named
    "x ray diffraction",           # 'x' alone is too short to name x.com
    "bbc",                         # a site, but not one in this library (bbc.co.uk is left out below)
])
def test_no_site_for_ordinary_words(query):
    intent = parse_query(query, [d for d in DOMAINS if d != "bbc.co.uk"], NOW)
    assert intent.domains == set()


def test_only_the_users_sites_count():
    assert parse_query("reddit thread", ["github.com"], NOW).active is False


@pytest.mark.parametrize("query, start, end, text", [
    ("the article i read yesterday about rust", "2026-11-02", "2026-11-05", "rust"),
    ("cuda page from today", "2026-11-03T12:00", "2026-11-04T16:30", "cuda"),
    ("rust thing from 3 days ago", "2026-10-31", "2026-11-03", "rust"),
    ("a week ago about pasta", "2026-10-24", "2026-11-02", "pasta"),
    ("what i saved last week", "2026-10-21T15:30", "2026-11-04T16:30", ""),
    ("the wikipedia page i saved on 31 august", "2026-08-30", "2026-09-02", ""),
    ("aug 29 gpu page", "2026-08-28", "2026-08-31", "gpu"),
    ("memorylane page from october", "2026-10-01", "2026-11-01", "memorylane"),
    ("stuff from december", "2025-12-01", "2026-01-01", ""),
    ("notes i read in 2025", "2025-01-01", "2026-01-01", "notes"),
    ("recently saved recipes", "2026-10-21T15:30", "2026-11-04T16:30", "recipes"),
])
def test_time_phrases(query, start, end, text):
    intent = parse_query(query, DOMAINS, NOW)
    assert intent.saved_from == day(start)
    assert intent.saved_until == day(end)
    assert intent.text == text


@pytest.mark.parametrize("query", ["march madness bracket", "may the force be with you", "monday blues"])
def test_bare_month_names_are_not_dates(query):
    assert parse_query(query, DOMAINS, NOW).saved_from is None


def test_site_and_time_together():
    intent = parse_query("youtube video i watched yesterday on watercolors", DOMAINS, NOW)
    assert intent.domains == {"youtube.com"}
    assert intent.saved_from == day("2026-11-02")
    assert intent.text == "watercolors"


def test_url_query():
    intent = parse_query("https://www.github.com/tokio-rs/axum/", DOMAINS, NOW)
    assert intent.url == "https://github.com/tokio-rs/axum"
    assert intent.domains == {"github.com"}
    assert intent.text == "tokio rs axum"


def test_domain_query():
    intent = parse_query("github.com", DOMAINS, NOW)
    assert intent.url is None and intent.domains == {"github.com"} and intent.text == ""


def test_unknown_domain_like_word_is_not_a_url():
    assert parse_query("node.js", DOMAINS, NOW).active is False


def test_empty_query():
    assert parse_query("", DOMAINS, NOW).active is False


@pytest.mark.parametrize("query, is_time", [
    ("python features in 2024", False),
    ("what i saved in 2025", True),
    ("notes from 2025", True),
])
def test_years_need_from_or_a_seeing_word(query, is_time):
    assert (parse_query(query, DOMAINS, NOW).saved_from is not None) is is_time


@pytest.mark.parametrize("domain, aliases", [
    ("open.spotify.com", {"spotify"}),
    ("read.amazon.com", {"amazon"}),
    ("learn.microsoft.com", {"microsoft"}),
    ("tiet-ucs503.bvraghav.com", {"bvraghav"}),
])
def test_only_the_main_label_names_a_site(domain, aliases):
    assert site_aliases(domain) == aliases


def test_subdomain_words_do_not_trigger_site_matches():
    domains = ["open.spotify.com", "read.amazon.com", "play.google.com"]
    assert parse_query("open source license", domains, NOW).domains == set()
    assert parse_query("what i read about rust", domains, NOW).domains == set()
    assert parse_query("spotify playlist", domains, NOW).domains == {"open.spotify.com"}
