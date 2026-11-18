"""Which pages automatic capture may save.

The Chrome extension applies these rules (extension/page_filter.js) before it
sends anything. The API applies them again to every automatic save
(`is_manual: false`), so an outdated or misbehaving extension still can't store
an inbox, a document editor or a login page: `auto_capture_refusal` says why a
page is refused. Manual "Remember this page" saves are never filtered.
Keep the lists identical to the extension's.
"""
import ipaddress
import re
from urllib.parse import parse_qsl, urlparse

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

# Webmail: inboxes and messages are private (kept identical to extension/page_filter.js).
EMAIL_HOSTS = (
    "mail.google.com", "inbox.google.com", "outlook.live.com", "outlook.office.com",
    "outlook.office365.com", "outlook.com", "hotmail.com", "mail.yahoo.com",
    "mail.proton.me", "protonmail.com", "mail.zoho.com", "mail.zoho.in", "mail.zoho.eu",
    "fastmail.com", "tuta.com", "tutanota.com", "mail.aol.com", "mail.yandex.com",
    "mail.yandex.ru", "gmx.com", "gmx.net", "web.de", "mail.com", "hey.com",
    "rediffmail.com", "superhuman.com",
)
EMAIL_HOST_PREFIXES = ("mail.", "webmail.", "email.")
EMAIL_PATH_SEGMENTS = ("owa", "webmail", "roundcube", "squirrelmail")

PRIVATE_APP_HOSTS = (
    "docs.google.com", "drive.google.com", "calendar.google.com", "keep.google.com",
    "classroom.google.com", "contacts.google.com", "photos.google.com", "meet.google.com",
    "chat.google.com", "myaccount.google.com", "onedrive.live.com", "sharepoint.com",
    "office.com", "teams.microsoft.com", "teams.live.com", "notion.so", "notion.site",
    "slack.com", "discord.gg", "web.whatsapp.com", "web.telegram.org", "messenger.com",
    "figma.com", "miro.com", "trello.com", "asana.com", "atlassian.net", "monday.com",
    "dropbox.com", "box.com", "icloud.com", "zoom.us", "chatgpt.com", "chat.openai.com",
    "claude.ai", "gemini.google.com", "instructure.com", "blackboard.com",
    "console.aws.amazon.com", "portal.azure.com", "console.cloud.google.com",
    "vercel.com", "netlify.app", "app.netlify.com", "dashboard.stripe.com",
)
PRIVATE_HOST_LABELS = ("moodle", "lms", "intranet", "portal", "erp", "webkiosk")
PRIVATE_PATH_SEGMENTS = (
    "dashboard", "admin", "settings", "preferences", "profile", "inbox", "messages",
    "notifications", "cart", "basket", "orders", "my-account", "myaccount", "console",
)
SECRET_PARAMS = (
    "token", "access_token", "id_token", "auth", "code", "session", "sessionid", "sid",
    "key", "apikey", "api_key", "sig", "signature", "otp", "ticket", "secret", "password",
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


def is_email_host_path(host: str, path: str) -> bool:
    """Webmail inboxes and messages, including iCloud Mail (icloud.com/mail)."""
    host = host.lower().removeprefix("www.")
    if any(_host_matches(host, d) for d in EMAIL_HOSTS):
        return True
    if host.startswith(EMAIL_HOST_PREFIXES):
        return True
    segments = [s.lower() for s in (path or "").split("/") if s]
    if _host_matches(host, "icloud.com") and segments[:1] == ["mail"]:
        return True
    return any(seg in EMAIL_PATH_SEGMENTS for seg in segments)


def _is_private_network_host(host: str) -> bool:
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified


def is_private_page(host: str, path: str, query: str) -> bool:
    """Pages that show the person's own private things: private apps, local sites,
    account areas, and links carrying a secret."""
    host = host.lower().removeprefix("www.")
    if _is_private_network_host(host):
        return True
    if any(_host_matches(host, d) for d in PRIVATE_APP_HOSTS):
        return True
    if any(label in PRIVATE_HOST_LABELS for label in host.split(".")):
        return True
    segments = [s.lower() for s in (path or "").split("/") if s]
    if any(seg in PRIVATE_PATH_SEGMENTS for seg in segments):
        return True
    return any(name.lower() in SECRET_PARAMS for name, _ in parse_qsl(query or "", keep_blank_values=True))


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
    if is_email_host_path(host, parsed.path):
        return False
    if is_private_page(host, parsed.path, parsed.query):
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


# ---- the page itself (for automatic saves) ----------------------------------------

_ROBOTS_META = re.compile(r"<meta\b[^>]*\bname\s*=\s*[\"']?(?:robots|googlebot)[\"']?[^>]*>", re.IGNORECASE)


def auto_capture_refusal(url: str, html: str | None) -> str | None:
    """Why an automatic save of this page is refused, or None if it's allowed.

    The address rules above, plus the page's robots "noindex" tag (what most
    private and logged-in pages carry). Password fields and editors are checked by
    the extension, which can tell whether they're visible: many article pages hide
    a login form in their HTML, so the server doesn't judge by that.
    """
    if not is_auto_capture_eligible(url):
        return "Automatic capture doesn't save this kind of page"
    if html:
        for tag in _ROBOTS_META.findall(html):
            if "noindex" in tag.lower():
                return "Automatic capture doesn't save pages marked noindex"
    return None
