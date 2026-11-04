"""What a search query says about where and when a page was seen.

People remember pages by the site ("that reddit thread on..."), by when they
saw them ("the article from last week") or by the address itself. `parse_query`
finds those parts:

- site words: a word (or two or three run together, as in "rotten tomatoes")
  that names one of the user's own sites, like "reddit" for reddit.com or
  "nvidia" for docs.nvidia.com and nvidia.com. Only sites the user has saved
  pages from count, so an ordinary word rarely triggers it.
- time phrases: today, yesterday, N days/weeks/months ago, this/last week,
  month or year, recently, "on 31 august", "in march", "in 2025".
- a URL or domain typed as the query.

Search then also ranks just the matching pages (see retrieval.hybrid_search),
so these are boosts, not filters: a wrong guess costs a little ranking, never
the result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from backend.url_utils import normalize_url

# Host labels that say nothing about which site it is.
GENERIC_HOST_LABELS = {
    "www", "m", "mobile", "en", "app", "web", "docs", "doc", "blog", "api", "dev",
    "developer", "developers", "support", "help", "news", "mail", "login", "auth",
    "accounts", "account", "community", "forum", "forums", "old", "new", "beta",
}
# Second-level labels of country domains (bbc.co.uk, iitd.ac.in).
SECOND_LEVEL_SUFFIXES = {"co", "com", "org", "net", "ac", "gov", "edu", "nic", "res", "gob"}
# Short names people use for a site, mapped to a host label.
NICKNAMES = {"wiki": "wikipedia", "yt": "youtube", "gh": "github", "twitter": "x", "insta": "instagram"}
MIN_ALIAS_LENGTH = 3

# Words that only say what kind of thing it was or that it was seen. Dropped
# from the query used within the matching pages.
FILLER_WORDS = {
    "a", "an", "the", "that", "this", "those", "these", "my", "i", "me", "we", "what", "which",
    "from", "on", "in", "at", "of", "about", "for", "with", "to", "by", "during", "back", "and",
    "page", "pages", "site", "website", "webpage", "article", "articles", "post", "posts",
    "thread", "threads", "video", "videos", "link", "links", "one", "thing", "stuff",
    "saved", "save", "read", "seen", "saw", "see", "visited", "visit", "opened", "open",
    "watched", "watch", "looked", "look", "looking", "found", "checked", "check", "viewed",
    "view", "browsed", "browse", "came", "across", "bookmarked",
    "was", "were", "is", "do", "did", "had", "have", "some", "something", "any",
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
               "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "couple": 2, "few": 3}

_WORD = re.compile(r"[a-z0-9]+")
_URL_LIKE = re.compile(r"^(https?://)?([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?(/\S*)?$|^https?://\S+$")
_MONTH_NAME = "|".join(sorted(list(_MONTHS) + list(_MONTH_ABBR), key=len, reverse=True))
_FULL_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORDINAL = r"(\d{1,2})(?:st|nd|rd|th)?"
_NUMBER = r"(\d+|" + "|".join(_NUMBERS) + r")"

_TIME_PATTERNS = [
    # "31 august", "31st of aug", "on 31 august 2025"
    ("day", re.compile(rf"\b(?:on\s+)?(?:the\s+)?{_ORDINAL}\s+(?:of\s+)?({_MONTH_NAME})\b(?:\s+(\d{{4}}))?")),
    # "august 31", "aug 31st, 2025"
    ("day_md", re.compile(rf"\b(?:on\s+)?({_MONTH_NAME})\s+{_ORDINAL}\b(?:,?\s+(\d{{4}}))?")),
    ("ago", re.compile(rf"\b(?:a\s+)?{_NUMBER}\s+(day|week|month|year)s?\s+ago\b")),
    ("named", re.compile(r"\b(today|yesterday|recently|lately)\b")),
    ("this_last", re.compile(r"\b(this|last|past|previous)\s+(week|month|year|few days|couple of days)\b")),
    # "in march", "from october 2025", "last march" (a bare month name could be a topic: "march madness")
    ("month", re.compile(rf"\b(in|from|during|last|back in|early|late|mid)\s+({_FULL_MONTH})\b(?:\s+(\d{{4}}))?")),
    # "in 2024" is more often about the content ("python features in 2024"), so a
    # year counts only after "from" or with a word about saving or seeing it.
    ("year", re.compile(r"\b(in|from|during|back in)\s+(20\d\d|19\d\d)\b")),
]
_SEEN = re.compile(r"\b(saved|save|read|seen|saw|visited|opened|watched|looked|found|bookmarked)\b")


@dataclass
class QueryIntent:
    """What `parse_query` found. `text` is the query without the site, time and
    filler words, for searching within the matching pages ("" when nothing is left)."""
    text: str = ""
    domains: set[str] = field(default_factory=set)
    saved_from: datetime | None = None
    saved_until: datetime | None = None
    # For a phrase that names one day: its middle, so pages nearest it rank first.
    saved_near: datetime | None = None
    url: str | None = None

    @property
    def active(self) -> bool:
        return bool(self.domains or self.saved_from or self.url)


def site_aliases(domain: str) -> set[str]:
    """Names a person might use for a site: 'en.wikipedia.org' -> {'wikipedia'},
    'docs.nvidia.com' -> {'nvidia'}, 'rotten-tomatoes.com' -> {'rottentomatoes'}.

    Only the label before the ending counts. Subdomains are often ordinary words
    ('open.spotify.com', 'read.amazon.com', 'learn.microsoft.com') that would
    otherwise turn topic queries into site queries.
    """
    host = domain.lower().split(":")[0].strip(".")
    labels = host.split(".")
    if len(labels) > 1:
        labels = labels[:-1]  # top-level domain
        if len(labels) > 1 and labels[-1] in SECOND_LEVEL_SUFFIXES:
            labels = labels[:-1]
    label = labels[-1] if labels else ""
    name = label.replace("-", "")
    if not name or label in GENERIC_HOST_LABELS or name in FILLER_WORDS:
        return set()
    if len(name) >= MIN_ALIAS_LENGTH or name in NICKNAMES.values():
        return {name}
    return set()


def alias_index(domains) -> dict[str, set[str]]:
    """alias -> the user's domains it names."""
    index: dict[str, set[str]] = {}
    for domain in domains:
        for alias in site_aliases(domain):
            index.setdefault(alias, set()).add(domain)
    return index


def _months_back(now: datetime, month: int, year: int | None) -> int:
    """The year of the latest `month` not after now, unless `year` is given."""
    if year:
        return year
    return now.year if month <= now.month else now.year - 1


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    return start, end


def _day_range(now: datetime, month: int, day: int, year: int | None):
    year = year or (now.year if (month, day) <= (now.month, now.day) else now.year - 1)
    try:
        start = datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None
    # A day either side: the saved time is UTC and the person's day may not be.
    return start - timedelta(days=1), start + timedelta(days=2)


def _number(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBERS.get(word, 1)


def _time_range(kind: str, m: re.Match, now: datetime):
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind in ("day", "day_md"):
        if kind == "day":
            day, month_name, year = m.group(1), m.group(2), m.group(3)
        else:
            month_name, day, year = m.group(1), m.group(2), m.group(3)
        month = _MONTHS.get(month_name) or _MONTH_ABBR.get(month_name)
        return _day_range(now, month, int(day), int(year) if year else None)
    if kind == "ago":
        n, unit = _number(m.group(1)), m.group(2)
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        slack = {"day": 1, "week": 4, "month": 15, "year": 120}[unit]
        center = today - timedelta(days=days)
        return center - timedelta(days=slack), center + timedelta(days=slack + 1)
    if kind == "named":
        word = m.group(1)
        if word == "today":
            return today - timedelta(hours=12), now + timedelta(hours=1)
        if word == "yesterday":
            return today - timedelta(days=2), today + timedelta(days=1)
        return now - timedelta(days=14), now + timedelta(hours=1)
    if kind == "this_last":
        which, unit = m.group(1), m.group(2)
        span = {"week": 7, "month": 31, "year": 366, "few days": 4, "couple of days": 3}[unit]
        back = span if which == "this" or unit in ("few days", "couple of days") else 2 * span
        return now - timedelta(days=back), now + timedelta(hours=1)
    if kind == "month":
        month = _MONTHS[m.group(2)]
        year = int(m.group(3)) if m.group(3) else None
        if m.group(1) == "last" and not year:
            year = now.year - 1 if month >= now.month else now.year
        return _month_range(_months_back(now, month, year), month)
    if kind == "year":
        if m.group(1) != "from" and not _SEEN.search(m.string):
            return None
        year = int(m.group(2))
        return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return None


def _names_one_day(kind: str, m: re.Match) -> bool:
    return kind in ("day", "day_md") or (kind == "named" and m.group(1) in ("today", "yesterday"))         or (kind == "ago" and m.group(2) == "day")


def _find_time(query: str, now: datetime):
    """(start, end, middle if it names one day, span of the phrase) for the first
    time phrase, or None."""
    for kind, pattern in _TIME_PATTERNS:
        for m in pattern.finditer(query):
            found = _time_range(kind, m, now)
            if found:
                start, end = found
                near = start + (end - start) / 2 if _names_one_day(kind, m) else None
                return start, end, near, m.span()
    return None


def _url_intent(query: str, domains) -> tuple[str | None, set[str]]:
    """A query that is a URL or a domain: (normalised URL if it has a path, its domain if saved)."""
    token = query.strip()
    if " " in token or not _URL_LIKE.match(token):
        return None, set()
    parsed = urlparse(token if "://" in token else "https://" + token)
    host = parsed.netloc.lower().removeprefix("www.")
    saved = {d for d in domains if d == host}
    has_path = parsed.path not in ("", "/") or bool(parsed.query)
    return (normalize_url(parsed.geturl()) if has_path else None), saved


def parse_query(query: str, domains, now: datetime | None = None) -> QueryIntent:
    """Find site words, a time phrase or a URL in `query`. `domains` are the
    sites the user has saved pages from."""
    now = now or datetime.now(timezone.utc)
    lowered = (query or "").lower()
    intent = QueryIntent()

    url, url_domains = _url_intent(lowered, domains)
    if url or url_domains:
        intent.url, intent.domains = url, url_domains
        path = urlparse(url).path if url else ""
        intent.text = " ".join(w for w in _WORD.findall(path) if w not in FILLER_WORDS)
        return intent

    time_found = _find_time(lowered, now)
    if time_found:
        intent.saved_from, intent.saved_until, intent.saved_near, (start, end) = time_found
        lowered = lowered[:start] + " " + lowered[end:]

    words = _WORD.findall(lowered)
    aliases = alias_index(domains)
    used = [False] * len(words)
    # Longest run first, so "rotten tomatoes" wins over a site named "rotten".
    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            if any(used[i:i + size]):
                continue
            name = "".join(words[i:i + size])
            if size == 1:
                if name in NICKNAMES:
                    name = NICKNAMES[name]
                elif len(name) < MIN_ALIAS_LENGTH:
                    continue
            if name in aliases:
                intent.domains |= aliases[name]
                used[i:i + size] = [True] * size

    intent.text = " ".join(w for w, u in zip(words, used) if not u and w not in FILLER_WORDS)
    return intent
