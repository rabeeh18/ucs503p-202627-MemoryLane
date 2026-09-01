import urllib.parse
import hashlib
import re

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

def generate_webpage_id(normalized_url: str) -> str:
    parsed = urllib.parse.urlparse(normalized_url)
    domain = parsed.netloc
    path = parsed.path

    raw_id = f"{domain}_{path}"
    if parsed.query:
        query_hash = hashlib.sha256(parsed.query.encode('utf-8')).hexdigest()[:8]
        raw_id = f"{raw_id}_{query_hash}"
    raw_id = raw_id.replace('/', '_')
    raw_id = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', raw_id)
    raw_id = re.sub(r'_+', '_', raw_id)
    raw_id = raw_id.strip('_')

    if len(raw_id) > 200:
        hash_str = hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()[:16]
        raw_id = f"{raw_id[:180]}_{hash_str}"

    return raw_id
