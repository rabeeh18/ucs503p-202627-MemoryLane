"""Saving a page into the extension's local store, with the server's own code.

This runs in Pyodide inside the extension. It imports the backend's real
modules (copied into the extension at build time by tools/vendor.mjs) and calls
backend.ingest.ingest_page exactly as POST /memory does, with two stand-ins:

- the Solr client is LocalSolr: it answers "is this page stored already?" from
  the local index (`lookup_head`, a JavaScript function) and captures the chunk
  documents instead of sending them anywhere;
- embedding is deferred: the texts to embed are returned, and the extension
  embeds them with the same model (transformers.js) before storing the page.

So a page saved on the device is cleaned (trafilatura), chunked, titled and
dated exactly as the server would have done it.
"""
import json
import sys
import types


def _stub(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module


class _Offline:
    """Network clients the shared code imports but local saving never uses:
    any call fails, as a request with no network would."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        raise RuntimeError("No network access while saving locally")


def _offline(*args, **kwargs):
    raise RuntimeError("No network access while saving locally")


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("httpx", Client=_Offline, get=_offline, post=_offline, HTTPStatusError=RuntimeError)
_stub("youtube_transcript_api", YouTubeTranscriptApi=_Offline)

from backend import config, ingest  # noqa: E402  (after the stubs)
from backend.ingest import IngestError, ingest_page, resolve_canonical_url  # noqa: E402
from backend.page_filter import auto_capture_refusal  # noqa: E402
from backend.url_utils import generate_page_id, normalize_url  # noqa: E402


class LocalSolr:
    """The Solr calls ingest_page makes, answered from the local index."""

    def __init__(self, lookup_head):
        self._lookup_head = lookup_head
        self.docs = None

    def get_page_head(self, page_id, user_id):
        found = self._lookup_head(page_id)
        if found is None or not isinstance(found, str) or not found:
            return None
        return json.loads(found)

    def count_pages(self, user_id, page_ids=None):
        return 0  # the local store's limit is its size, checked by the extension

    def upsert_page_chunks(self, page_id, docs, user_id):
        self.docs = docs


def save(request_json: str, lookup_head) -> str:
    """Prepare one page. `request_json` holds what POST /memory receives plus
    `user_id`; returns {"result": ..., "docs": [...], "embed_texts": [...]}
    or {"skipped": message} or {"error": {"status", "detail"}}."""
    req = json.loads(request_json)
    if not req.get("is_manual"):
        for address in filter(None, (req.get("url"), req.get("canonical_url"))):
            reason = auto_capture_refusal(address, req.get("html"))
            if reason:
                return json.dumps({"skipped": reason})

    captured = []

    def embed(texts):
        captured.extend(texts)
        return [[0.0] * config.EMBEDDING_DIM for _ in texts]

    ingest.embed_passages = embed
    solr = LocalSolr(lookup_head)
    try:
        result = ingest_page(
            req["user_id"], req.get("url") or "", req.get("title") or "", req.get("content") or "",
            html=req.get("html"), canonical_url=req.get("canonical_url"),
            is_manual=bool(req.get("is_manual")), solr=solr,
            youtube=req.get("youtube"), keep_existing=not req.get("is_manual"),
            timestamp=req.get("timestamp"), description=req.get("description"),
            prepared_chunks=req.get("chunks"), content_hash=req.get("content_hash"),
            fetch_youtube=req.get("chunks") is None,
        )
    except IngestError as e:
        return json.dumps({"error": {"status": e.status_code, "detail": e.detail}})
    if result.status == "skipped":
        return json.dumps({"skipped": result.message})
    docs = []
    for doc in solr.docs or []:
        docs.append({k: v for k, v in doc.items() if k not in ("embedding", "page_embedding")})
    return json.dumps({"result": result.__dict__, "docs": docs, "embed_texts": captured})


def page_id_for(user_id: str, url: str, canonical_url: str | None) -> str:
    """The id a page is (or would be) stored under, as GET /memory/status works it out."""
    return generate_page_id(user_id, normalize_url(resolve_canonical_url(url, canonical_url)))


def apply_settings(settings_json: str) -> None:
    """Use the server's live chunking and model settings (GET /search-settings),
    where the modules read them, so local pages chunk exactly as server pages."""
    from backend import chunking

    settings = json.loads(settings_json)
    for name in ("CHUNK_MAX_WORDS", "CHUNK_MIN_WORDS", "CHUNK_OVERLAP_WORDS", "EMBEDDING_MODEL", "EMBEDDING_DIM"):
        if name in settings:
            setattr(config, name, settings[name])
            for module in (chunking, ingest):
                if hasattr(module, name):
                    setattr(module, name, settings[name])
