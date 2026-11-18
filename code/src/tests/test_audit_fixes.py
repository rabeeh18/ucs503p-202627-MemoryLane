"""Regression tests for the November 2026 bug audit (ML-002, -003, -006, -007, -012,
-013 and -P01). Each test names the finding it covers."""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from backend import accounts, ingest, library_moves, retrieval
from backend.ingest import IngestError, ingest_page
from backend.query_intent import parse_query
from backend.url_utils import generate_page_id, normalize_url
from backend.youtube_utils import extract_video_id

TEXT = "Sleep consolidates memory and learning in the brain during the night. " * 12
OLD, NEW = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
OTHER = "33333333-3333-3333-3333-333333333333"


class FakeSolr:
    """In-memory Solr for ingest and library moves. `visible=False` hides writes from
    counts, like Solr before its commitWithin second has passed."""

    def __init__(self, visible=True, slow_write=0.0):
        self.docs = {}
        self.visible = visible
        self.slow_write = slow_write
        self.writing = 0
        self.max_parallel_writes = 0
        self.lock = threading.Lock()

    def _mine(self, user_id):
        return [d for d in self.docs.values() if d["user_id"] == user_id]

    def get_page_head(self, page_id, user_id):
        return next((d for d in self._mine(user_id) if d["page_id"] == page_id and d["chunk_id"] == 0), None)

    def get_chunks_by_page_id(self, page_id, user_id):
        return sorted((d for d in self._mine(user_id) if d["page_id"] == page_id), key=lambda d: d["chunk_id"])

    def count_pages(self, user_id, page_ids=None):
        if not self.visible:
            return 0
        return len({d["page_id"] for d in self._mine(user_id) if page_ids is None or d["page_id"] in page_ids})

    def upsert_page_chunks(self, page_id, docs, user_id):
        with self.lock:
            self.writing += 1
            self.max_parallel_writes = max(self.max_parallel_writes, self.writing)
        time.sleep(self.slow_write)
        with self.lock:
            for d in docs:
                self.docs[d["id"]] = {k: v for k, v in d.items() if k != "embedding"}
            for key in [k for k, d in self.docs.items()
                        if d["user_id"] == user_id and d["page_id"] == page_id and d["chunk_id"] >= len(docs)]:
                del self.docs[key]
            self.writing -= 1

    def scan_page_heads(self, user_id, fields, limit, rows=500):
        return iter([d for d in self._mine(user_id) if d["chunk_id"] == 0][:limit])

    def delete_page(self, page_id, user_id):
        for key in [k for k, d in self.docs.items() if d["user_id"] == user_id and d["page_id"] == page_id]:
            del self.docs[key]


@pytest.fixture(autouse=True)
def fake_embeddings():
    with patch("backend.ingest.embed_passages", side_effect=lambda texts: [[0.1] * 384 for _ in texts]):
        yield


# ---- ML-003: concurrent saves of one page never interleave ------------------------

def test_saves_for_one_user_are_serialised():
    solr = FakeSolr(slow_write=0.05)
    errors = []

    def save(text):
        try:
            ingest_page(OLD, "https://example.com/a", "A", text, solr=solr)
        except Exception as e:  # pragma: no cover - surfaced below
            errors.append(e)

    threads = [threading.Thread(target=save, args=(TEXT * n,)) for n in (1, 3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert solr.max_parallel_writes == 1
    head = solr.get_page_head(generate_page_id(OLD, normalize_url("https://example.com/a")), OLD)
    chunks = solr.get_chunks_by_page_id(head["page_id"], OLD)
    assert head["total_chunks"] == len(chunks)  # one complete version, never a mix


# ---- ML-013: the page limit holds even before Solr shows new pages ----------------

def test_page_limit_counts_pages_solr_doesnt_show_yet():
    solr = FakeSolr(visible=False)
    ingest_page(OLD, "https://example.com/1", "One", TEXT, solr=solr, max_pages=1)
    with pytest.raises(IngestError) as e:
        ingest_page(OLD, "https://example.com/2", "Two", TEXT, solr=solr, max_pages=1)
    assert e.value.status_code == 403


def test_concurrent_new_pages_cant_both_pass_the_limit():
    solr = FakeSolr(visible=False, slow_write=0.05)
    outcomes = []

    def save(n):
        try:
            ingest_page(OLD, f"https://example.com/{n}", "P", TEXT, solr=solr, max_pages=1)
            outcomes.append("saved")
        except IngestError as e:
            outcomes.append(e.status_code)

    threads = [threading.Thread(target=save, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(map(str, outcomes)) == ["403", "saved"]


# ---- ML-006: an exact URL keeps its case-sensitive parts --------------------------

def test_url_query_keeps_case_of_path_and_query():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    intent = parse_query(url, ["youtube.com"])
    assert intent.url == normalize_url(url)
    assert generate_page_id("u", intent.url) == generate_page_id("u", normalize_url(url))


def test_url_query_still_ignores_host_case():
    intent = parse_query("HTTPS://Example.COM/Docs/Page", ["example.com"])
    assert intent.url == normalize_url("https://example.com/Docs/Page")


# ---- ML-007: a zero weight turns a retriever off ---------------------------------

def _chunk(doc_id, page, **extra):
    return {"id": doc_id, "page_id": page, "url": f"https://example.com/{page}", "title": page,
            "domain": "example.com", "timestamp": "t", "text": f"cats {doc_id}", **extra}


@pytest.mark.parametrize("bm25_weight,vector_weight,expected", [(1.0, 0.0, ["keyword"]), (0.0, 1.0, ["vector"])])
def test_ablation_runs_only_use_the_enabled_retriever(bm25_weight, vector_weight, expected):
    solr = MagicMock()
    solr.bm25_search.return_value = [_chunk("keyword::0", "keyword")]
    solr.knn_search.return_value = [_chunk("vector::0", "vector", score=0.95)]
    retrieval._cached_query_embedding.cache_clear()
    with patch("backend.retrieval.BM25_WEIGHT", bm25_weight), \
         patch("backend.retrieval.VECTOR_WEIGHT", vector_weight), \
         patch("backend.retrieval.QUERY_INTENT_ENABLED", False), \
         patch("backend.retrieval.KEYWORD_FULL_MATCH", 0.0), \
         patch("backend.retrieval.embed_query", return_value=[0.1] * 384):
        results = retrieval.hybrid_search("cats", "user-a", solr=solr, snippets=False)
    assert [r["page_id"] for r in results] == expected
    assert solr.bm25_search.called == (bm25_weight > 0)


# ---- ML-012: /live/ links ----------------------------------------------------------

def test_live_links_are_youtube_videos():
    assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_video_id("https://www.youtube.com/live/not-an-id") is None


# ---- ML-002: pages saved before linking move into the linked library ---------------

@pytest.fixture
def linking(monkeypatch):
    monkeypatch.setattr(accounts, "COGNITO_DOMAIN", "https://auth.example.com")
    accounts.reset_for_tests()
    yield
    accounts.reset_for_tests()


def _as(people):
    def fetch(token):
        sub = token.removeprefix("tok-")
        return {"sub": sub, **people[sub]}
    return patch.object(accounts, "fetch_userinfo", side_effect=fetch)


def test_linking_a_previously_unverified_sign_in_queues_a_move(linking, monkeypatch):
    people = {OLD: {"email": "ana@example.com", "email_verified": "false"},
              NEW: {"email": "ana@example.com", "email_verified": "true"}}
    with _as(people):
        assert accounts.library_for(OLD, f"tok-{OLD}") == OLD   # unverified: its own library
        assert accounts.library_for(NEW, f"tok-{NEW}") == NEW   # starts the email's library
        people[OLD]["email_verified"] = "true"
        monkeypatch.setattr(accounts, "UNVERIFIED_RECHECK_SECONDS", 0)
        assert accounts.library_for(OLD, f"tok-{OLD}") == NEW   # now linked
    assert accounts.pending_moves() == [(OLD, NEW)]
    assert accounts.moves_into(NEW) == [OLD]
    assert accounts.moves_waiting.is_set()


def test_move_carries_pages_across_and_keeps_newer_saves(linking):
    solr = FakeSolr()
    ingest_page(OLD, "https://example.com/only-old", "Old page", TEXT, solr=solr, timestamp="2026-11-01T00:00:00Z")
    ingest_page(OLD, "https://example.com/both", "Old copy", TEXT, solr=solr, timestamp="2026-11-01T00:00:00Z")
    ingest_page(NEW, "https://example.com/both", "Newer copy", TEXT, solr=solr, timestamp="2026-11-05T00:00:00Z")

    totals = library_moves.move_library(OLD, NEW, solr)

    assert totals == {"moved": 1, "kept_newer": 1, "failed": 0}
    assert solr._mine(OLD) == []
    titles = {d["url"]: d["title"] for d in solr._mine(NEW) if d["chunk_id"] == 0}
    assert titles == {"https://example.com/only-old": "Old page", "https://example.com/both": "Newer copy"}
    moved = solr.get_page_head(generate_page_id(NEW, "https://example.com/only-old"), NEW)
    assert str(moved["timestamp"]).startswith("2026-11-01")  # keeps its original save time


def test_run_pending_finishes_moves_and_retries_on_failure(linking):
    with accounts._lock:
        db = accounts._db()
        with db:
            db.execute("INSERT INTO library_moves (old, new, created_at) VALUES (?, ?, 0)", (OLD, NEW))
    broken = MagicMock()
    broken.scan_page_heads.side_effect = RuntimeError("solr down")
    assert library_moves.run_pending(broken) == 0
    assert accounts.pending_moves() == [(OLD, NEW)]  # kept for the next sweep
    assert library_moves.run_pending(FakeSolr()) == 1
    assert accounts.pending_moves() == []


# ---- ML-P01: a changed email stops linking to the old library ---------------------

def test_changed_email_releases_the_old_address(linking, monkeypatch):
    people = {OLD: {"email": "ana@example.com", "email_verified": "true"},
              OTHER: {"email": "ana@example.com", "email_verified": "true"}}
    with _as(people):
        assert accounts.library_for(OLD, f"tok-{OLD}") == OLD
        # Ana changes her email; the daily re-check notices.
        people[OLD]["email"] = "ana@new.example.com"
        monkeypatch.setattr(accounts, "REVALIDATE_SECONDS", 0)
        assert accounts.library_for(OLD, f"tok-{OLD}") == OLD
        # Someone who later verifies the old address doesn't get Ana's library.
        assert accounts.library_for(OTHER, f"tok-{OTHER}") == OTHER
    assert accounts.email_for(OLD) == "ana@new.example.com"


def test_revalidation_failure_keeps_the_library(linking, monkeypatch):
    with _as({OLD: {"email": "ana@example.com", "email_verified": "true"}}):
        assert accounts.library_for(OLD, f"tok-{OLD}") == OLD
    monkeypatch.setattr(accounts, "REVALIDATE_SECONDS", 0)
    with patch.object(accounts, "fetch_userinfo", side_effect=accounts.LinkUnavailable("down")):
        assert accounts.library_for(OLD, f"tok-{OLD}") == OLD


def test_known_sign_in_isnt_rechecked_within_a_day(linking):
    with _as({OLD: {"email": "ana@example.com", "email_verified": "true"}}) as fetch:
        accounts.library_for(OLD, f"tok-{OLD}")
        accounts.library_for(OLD, f"tok-{OLD}")
    assert fetch.call_count == 1
