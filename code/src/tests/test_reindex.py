from unittest.mock import MagicMock, patch

from backend.ingest import IngestError, IngestResult
from scripts import reindex


def _source(docs):
    source = MagicMock()
    source.scan_unscoped.return_value = iter(docs)
    return source


OLD_DOCS = [
    {"id": "ex_a::chunk::1", "webpage_id": "ex_a", "url": "https://ex.com/a", "title": "A",
     "timestamp": "2024-01-01T00:00:00+00:00", "text": "second", "chunk_id": 1},
    {"id": "ex_a::chunk::0", "webpage_id": "ex_a", "url": "https://ex.com/a", "title": "A",
     "timestamp": "2024-01-01T00:00:00+00:00", "text": "first", "chunk_id": 0},
    {"id": "ex_b::chunk::0", "webpage_id": "ex_b", "url": "https://ex.com/b", "title": "B",
     "timestamp": "2024-02-01T00:00:00+00:00", "text": "only", "chunk_id": 0},
]


def test_read_pages_groups_and_orders_chunks():
    pages = {p["url"]: p for p in reindex.read_pages(_source(OLD_DOCS))}
    assert pages["https://ex.com/a"]["text"] == "first\n\nsecond"
    assert pages["https://ex.com/a"]["timestamp"] == "2024-01-01T00:00:00+00:00"
    assert pages["https://ex.com/b"]["text"] == "only"


def _result(status="saved", chunks=3):
    return IngestResult(status, "", "pid", "u", "t", "d", "ts", chunks)


def test_reindex_ingests_every_page_under_user_and_counts():
    target = MagicMock()
    outcomes = [_result(), IngestError(422, "Not enough readable text on this page")]
    with patch("scripts.reindex.ingest_page", side_effect=outcomes) as mock_ingest:
        totals = reindex.reindex(_source(OLD_DOCS), target, "sub-123", delete_user="legacy")

    target.delete_user.assert_called_once_with("legacy")
    assert mock_ingest.call_count == 2
    args, kwargs = mock_ingest.call_args_list[0]
    assert args[0] == "sub-123"
    assert kwargs["solr"] is target
    assert kwargs["fetch_youtube"] is False
    assert kwargs["timestamp"] == "2024-01-01T00:00:00+00:00"
    assert totals == {"pages": 2, "source_chunks": 3, "saved": 1, "unchanged": 0,
                      "skipped": 0, "chunks": 3, "failures": 1}


def test_dry_run_writes_nothing():
    target = MagicMock()
    with patch("scripts.reindex.ingest_page") as mock_ingest:
        totals = reindex.reindex(_source(OLD_DOCS), target, "sub", delete_user="legacy", dry_run=True)
    mock_ingest.assert_not_called()
    target.delete_user.assert_not_called()
    target.upsert_page_chunks.assert_not_called()
    assert totals["pages"] == 2


def test_source_core_is_never_written():
    source = _source(OLD_DOCS)
    with patch("scripts.reindex.ingest_page", return_value=_result()):
        reindex.reindex(source, MagicMock(), "sub", delete_user="legacy")
    source.upsert_page_chunks.assert_not_called()
    source.delete_user.assert_not_called()


def test_solr_base_from_url():
    assert reindex.solr_base_from_url("http://solr:8983/solr/memorylane_v2") == "http://solr:8983/solr"
    assert reindex.solr_base_from_url("http://localhost:8983/solr") == "http://localhost:8983/solr"


def test_main_rejects_same_core():
    try:
        reindex.main(["--source-core", "x", "--target-core", "x", "--user-id", "u"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("expected SystemExit")
