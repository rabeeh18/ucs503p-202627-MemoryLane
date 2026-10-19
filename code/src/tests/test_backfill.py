from unittest.mock import MagicMock, patch

import pytest

from backend.ingest import IngestError, page_vector
from scripts import backfill_page_vectors as backfill


def _head(page_id, user="user-a", vector=None):
    return {"page_id": page_id, "user_id": user, "url": f"https://e.com/{page_id}", "title": f"T {page_id}",
            "timestamp": "2024-03-01T10:00:00Z", "description": f"desc {page_id}", "page_embedding": vector}


def _solr(heads):
    solr = MagicMock()
    solr.scan_unscoped.side_effect = lambda fields, filters=None: iter(heads)
    solr.get_chunks_by_page_id.side_effect = lambda page_id, user: [
        {"text": "second part", "chunk_id": 1}, {"text": "first part", "chunk_id": 0},
    ]
    return solr


def test_only_pages_without_vectors_are_reingested_from_stored_text():
    solr = _solr([_head("p1"), _head("p2", vector=[0.1, 0.2]), _head("p3")])
    with patch("scripts.backfill_page_vectors.ingest_page") as mock_ingest:
        totals = backfill.backfill(solr, log=lambda *_: None)
    assert totals == {"pages": 3, "already_done": 1, "todo": 2, "backfilled": 2, "failures": 0}
    assert [c.args[0] for c in mock_ingest.call_args_list] == ["user-a", "user-a"]
    args, kwargs = mock_ingest.call_args_list[0]
    assert args[1:] == ("https://e.com/p1", "T p1", "first part\n\nsecond part")
    assert kwargs["force"] is True               # every chunk is rewritten
    assert kwargs["fetch_youtube"] is False
    assert kwargs["timestamp"] == "2024-03-01T10:00:00Z"
    assert kwargs["description"] == "desc p1"
    assert kwargs["solr"] is solr


def test_never_uses_atomic_updates():
    solr = _solr([_head("p1")])
    with patch("scripts.backfill_page_vectors.ingest_page"):
        backfill.backfill(solr, log=lambda *_: None)
    # No partial "set" updates are ever sent to Solr by the script itself.
    for call in solr.method_calls:
        assert call[0] not in ("_update", "upsert_page_chunks")


def test_scan_is_limited_to_chunk_zero_and_the_user():
    solr = _solr([])
    backfill.backfill(solr, user_id="user-a", log=lambda *_: None)
    filters = solr.scan_unscoped.call_args.kwargs["filters"]
    assert filters == ["chunk_id:0", "{!term f=user_id}user-a"]


def test_dry_run_writes_nothing():
    solr = _solr([_head("p1")])
    with patch("scripts.backfill_page_vectors.ingest_page") as mock_ingest:
        totals = backfill.backfill(solr, dry_run=True, log=lambda *_: None)
    mock_ingest.assert_not_called()
    assert totals["todo"] == 1


def test_failures_are_counted_and_the_run_continues():
    solr = _solr([_head("p1"), _head("p2")])
    with patch("scripts.backfill_page_vectors.ingest_page",
               side_effect=[IngestError(422, "Not enough readable text on this page"), None]):
        totals = backfill.backfill(solr, log=lambda *_: None)
    assert totals["failures"] == 1 and totals["backfilled"] == 1


def test_progress_is_printed():
    lines = []
    with patch("scripts.backfill_page_vectors.ingest_page"):
        backfill.backfill(_solr([_head(f"p{i}") for i in range(12)]), log=lines.append)
    assert any("[10/12]" in line for line in lines)
    assert any("[12/12]" in line for line in lines)


def test_rejects_bad_user_id():
    with pytest.raises(SystemExit):
        backfill.main(["--user-id", "not ok"])


def test_page_vector_is_normalised_mean():
    vec = page_vector([[1.0, 0.0], [0.0, 1.0]])
    assert vec == pytest.approx([2 ** -0.5, 2 ** -0.5])
