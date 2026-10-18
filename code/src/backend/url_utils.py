import urllib.parse
import hashlib

# Exact query keys dropped during normalization (utm_* is handled by prefix).
TRACKING_PARAMS = {
    'fbclid', 'gclid', 'dclid', 'msclkid', 'twclid', 'yclid',
    'igshid', 'mc_cid', 'mc_eid', '_ga', '_gl', 'ref', 'ref_src',
}


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    if (scheme == 'http' and netloc.endswith(':80')) or (scheme == 'https' and netloc.endswith(':443')):
        netloc = netloc.rsplit(':', 1)[0]

    query = parsed.query
    if query:
        query_params = urllib.parse.parse_qsl(query, keep_blank_values=True)
        filtered_params = [
            (k, v) for k, v in query_params
            if k.lower() not in TRACKING_PARAMS and not k.lower().startswith('utm_')
        ]
        filtered_params.sort(key=lambda x: (x[0], x[1]))
        query = urllib.parse.urlencode(filtered_params)

    path = parsed.path
    if path and path != '/' and path.endswith('/'):
        path = path.rstrip('/')
    elif not path:
        path = '/'

    normalized = urllib.parse.urlunparse((scheme, netloc, path, parsed.params, query, ''))
    return normalized

def generate_page_id(user_id: str, normalized_url: str) -> str:
    """Deterministic per-user page id, so two users saving one URL get separate pages."""
    return hashlib.sha256(f"{user_id}|{normalized_url}".encode('utf-8')).hexdigest()[:32]
