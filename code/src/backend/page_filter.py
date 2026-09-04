"""URL eligibility for automatic webpage capture.

Used by tests as the reference ruleset. The Chrome extension applies the same
checks client-side so sensitive pages are never POSTed in automatic mode.
Manual "Remember this page" is not filtered.
"""
from urllib.parse import urlparse

SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "linkedin.com", "reddit.com", "snapchat.com",
    "pinterest.com", "threads.net", "whatsapp.com", "discord.com",
    "tumblr.com", "bsky.app",
)

BANKING_HOST_MARKERS = (
    "paypal.com", "venmo.com", "stripe.com", "chase.com",
    "bankofamerica.com", "wellsfargo.com", "capitalone.com",
    "americanexpress.com", "amex.com", "citibank.com", "citi.com",
    "hsbc.com", "barclays.com", "revolut.com", "wise.com", "cash.app",
    "discover.com", "schwab.com", "fidelity.com", "tdbank.com",
    "ally.com", "sofi.com",
)

LOGIN_ACCOUNT_SEGMENTS = (
    "login", "log-in", "signin", "sign-in", "signup", "sign-up",
    "register", "auth", "oauth", "sso", "account", "accounts",
    "password", "forgot", "checkout", "billing", "payment", "wallet",
)

INTERNAL_SCHEMES = (
    "chrome", "chrome-extension", "edge", "about", "moz-extension",
    "brave", "devtools", "view-source", "file", "data", "javascript",
)

SEARCH_ENGINE_HOSTS = (
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com",
)

UTILITY_PATH_SEGMENTS = (
    "404", "error", "privacy", "privacy-policy", "terms", "terms-of-service",
    "tos", "cookie", "cookies", "sitemap", "sitemap.xml",
)

IGNORED_EXTENSIONS = (
    ".pdf", ".zip", ".exe", ".png", ".jpg", ".jpeg", ".mp4", ".mp3",
    ".gif", ".csv", ".json", ".xml",
)


def _host_matches(host: str, domain: str) -> bool:
    host = host.lower().removeprefix("www.")
    domain = domain.lower()
    return host == domain or host.endswith("." + domain)


def is_auto_capture_eligible(url: str) -> bool:
    """Return True if automatic capture may save this URL."""
    if not url or not url.strip():
        return False
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme in INTERNAL_SCHEMES or scheme not in ("http", "https"):
        return False

    host = (parsed.netloc or "").lower().split("@")[-1]
    if ":" in host:
        host = host.rsplit(":", 1)[0]
    host = host.removeprefix("www.")
    if not host:
        return False

    if any(_host_matches(host, d) for d in SOCIAL_HOSTS):
        return False
    if host.endswith(".bank") or "banking" in host:
        return False
    if any(_host_matches(host, d) for d in BANKING_HOST_MARKERS):
        return False
    if "bank" in host.split(".")[0]:
        return False

    path = parsed.path or "/"
    segments = [s.lower() for s in path.split("/") if s]
    if any(seg in LOGIN_ACCOUNT_SEGMENTS for seg in segments):
        return False
    if any(seg in UTILITY_PATH_SEGMENTS for seg in segments):
        return False
        
    lowered_path = path.lower()
    if any(f"/{seg}" in lowered_path for seg in ("reset-password", "forgot-password")):
        return False

    if any(lowered_path.endswith(ext) for ext in IGNORED_EXTENSIONS):
        return False

    # Search engine result pages check
    if any(_host_matches(host, d) for d in SEARCH_ENGINE_HOSTS):
        query = parsed.query.lower()
        if "/search" in lowered_path or "/results" in lowered_path or "q=" in query:
            return False

    # YouTube specific checks
    is_youtube = _host_matches(host, "youtube.com")
    is_youtu_be = _host_matches(host, "youtu.be")
    if is_youtube or is_youtu_be:
        if is_youtube:
            if not lowered_path.startswith("/watch"):
                return False
            if "v=" not in parsed.query:
                return False
        if is_youtu_be:
            if path == "/" or path == "":
                return False

    if path == "/" or path == "":
        return False

    return True
