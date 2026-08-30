import urllib.parse
import hashlib
import re

def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    
    query = parsed.query
    if query:
        query_params = urllib.parse.parse_qsl(query, keep_blank_values=True)
        tracking_exact = {'fbclid', 'gclid', 'ref', 'ref_src'}
        filtered_params = [
            (k, v) for k, v in query_params
            if k.lower() not in tracking_exact and not k.lower().startswith('utm_')
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
    raw_id = raw_id.replace('/', '_')
    raw_id = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', raw_id)
    raw_id = re.sub(r'_+', '_', raw_id)
    raw_id = raw_id.strip('_')
    
    if len(raw_id) > 200:
        hash_str = hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()[:16]
        raw_id = f"{raw_id[:180]}_{hash_str}"
        
    return raw_id
