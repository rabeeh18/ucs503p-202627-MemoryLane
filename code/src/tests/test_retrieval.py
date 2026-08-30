from backend.retrieval import normalize_scores, fuse_scores, group_by_webpage
from backend.solr_client import normalize_solr_doc, unwrap_solr_value


def test_normalize_empty():
    assert normalize_scores([]) == {}


def test_normalize_single_result():
    assert normalize_scores([("a", 3.2)]) == {"a": 1.0}


def test_normalize_identical_scores():
    result = normalize_scores([("a", 5.0), ("b", 5.0)])
    assert result == {"a": 1.0, "b": 1.0}


def test_normalize_minmax():
    result = normalize_scores([("a", 0.0), ("b", 5.0), ("c", 10.0)])
    assert result["a"] == 0.0
    assert result["c"] == 1.0
    assert result["b"] == 0.5


def test_fuse_missing_method_is_zero():
    fused = fuse_scores({"a": 1.0, "b": 0.5}, {"b": 1.0, "c": 0.2}, bm25_weight=0.5, vector_weight=0.5)
    assert fused["a"] == 0.5
    assert fused["c"] == 0.1
    assert fused["b"] == 0.75


def test_fuse_no_nan():
    fused = fuse_scores({"a": 0.0}, {"a": 0.0})
    assert fused["a"] == 0.0
    assert all(v == v and v not in (float("inf"), float("-inf")) for v in fused.values())


def test_group_by_webpage_highest_chunk_wins():
    candidates = [
        {
            "id": "page1::chunk::0",
            "webpage_id": "page1",
            "url": "https://example.com/1",
            "title": "One",
            "domain": "example.com",
            "timestamp": "t1",
            "_bm25_norm": 0.2,
            "_vector_norm": 0.1,
        },
        {
            "id": "page1::chunk::1",
            "webpage_id": "page1",
            "url": "https://example.com/1",
            "title": "One",
            "domain": "example.com",
            "timestamp": "t1",
            "_bm25_norm": 0.9,
            "_vector_norm": 0.8,
        },
        {
            "id": "page2::chunk::0",
            "webpage_id": "page2",
            "url": "https://example.com/2",
            "title": "Two",
            "domain": "example.com",
            "timestamp": "t2",
            "_bm25_norm": 0.4,
            "_vector_norm": 0.4,
        },
    ]
    fused = {
        "page1::chunk::0": 0.15,
        "page1::chunk::1": 0.85,
        "page2::chunk::0": 0.40,
    }
    grouped = group_by_webpage(candidates, fused)
    assert grouped[0]["webpage_id"] == "page1"
    assert grouped[0]["fused_score"] == 0.85
    assert grouped[0]["id"] == "page1::chunk::1"
    assert grouped[1]["webpage_id"] == "page2"


def test_unwrap_single_element_list():
    assert unwrap_solr_value(["Artificial Intelligence"], "title") == "Artificial Intelligence"
    assert unwrap_solr_value(["https://example.com"], "url") == "https://example.com"
    assert unwrap_solr_value("already-scalar", "id") == "already-scalar"


def test_unwrap_keeps_embedding_vector():
    vector = [0.1] * 384
    assert unwrap_solr_value(vector, "embedding") == vector


def test_normalize_solr_doc_flattens_string_fields():
    doc = normalize_solr_doc({
        "id": "doc1",
        "title": ["Artificial Intelligence"],
        "url": ["https://example.com/ai"],
        "domain": ["example.com"],
        "webpage_id": ["example.com_ai"],
        "text": ["Some page text"],
        "timestamp": ["2024-01-01T00:00:00Z"],
        "chunk_id": [0],
        "total_chunks": [1],
        "score": 1.2,
        "embedding": [0.1, 0.2],
    })
    assert doc["title"] == "Artificial Intelligence"
    assert doc["url"] == "https://example.com/ai"
    assert doc["domain"] == "example.com"
    assert doc["webpage_id"] == "example.com_ai"
    assert doc["text"] == "Some page text"
    assert doc["timestamp"] == "2024-01-01T00:00:00Z"
    assert doc["chunk_id"] == 0
    assert doc["total_chunks"] == 1
    assert doc["score"] == 1.2
    assert doc["embedding"] == [0.1, 0.2]


def test_group_by_webpage_accepts_solr_list_fields():
    raw = {
        "id": "page1::chunk::0",
        "webpage_id": ["page1"],
        "url": ["https://example.com/1"],
        "title": ["Artificial Intelligence"],
        "domain": ["example.com"],
        "timestamp": ["t1"],
        "_bm25_norm": 0.9,
        "_vector_norm": 0.8,
    }
    doc = normalize_solr_doc(raw)
    grouped = group_by_webpage([doc], {doc["id"]: 0.9})
    assert grouped[0]["title"] == "Artificial Intelligence"
    assert grouped[0]["webpage_id"] == "page1"
