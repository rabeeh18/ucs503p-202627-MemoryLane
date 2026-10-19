from collections import OrderedDict
from unittest.mock import MagicMock

import numpy as np
import pytest

from backend import library_map as lm
from backend.library_map import MapService, StaleMap, build_map, choose_k, cluster, ctfidf_labels

DIM = 384
TOPICS = {
    "ml": ["How neural networks learn", "Training deep learning models", "Gradient descent explained",
           "Backpropagation in neural networks", "Supervised learning basics", "Overfitting in learning models"],
    "search": ["BM25 ranking for search", "Dense vector search in Solr", "Hybrid search ranking",
               "Inverted index search basics", "Search relevance tuning"],
    "sleep": ["Why sleep matters for memory", "Sleep cycles and memory", "REM sleep and dreaming",
              "Memory consolidation during sleep"],
    "design": ["Keyboard-first interface design", "Designing accessible interfaces", "Interface design patterns",
               "Typography in interface design"],
}


def _axis(i):
    v = np.zeros(DIM)
    v[i] = 1.0
    return v


def make_heads(seed=0, noise=0.25, extra=None, prefix="p"):
    """Pages whose vectors cluster around one axis per topic."""
    rng = np.random.default_rng(seed)
    heads = []
    for t, (name, titles) in enumerate(TOPICS.items()):
        for j, title in enumerate(titles):
            v = _axis(t) + rng.normal(scale=noise / np.sqrt(DIM), size=DIM) * np.sqrt(DIM) * 0.1
            v /= np.linalg.norm(v)
            heads.append({
                "page_id": f"{prefix}-{name}-{j}", "title": title, "url": f"https://{name}.example.com/{j}",
                "domain": f"{name}.example.com", "timestamp": f"2024-01-{j + 1:02d}T00:00:00Z",
                "description": "", "page_embedding": v.tolist(),
            })
    for h in extra or []:
        heads.append(h)
    return heads


def test_clustering_is_deterministic():
    heads = make_heads()
    a = build_map(heads, "k", 0).response
    b = build_map(heads, "k", 0).response
    assert a == b


def test_clustering_finds_the_topics():
    m = build_map(make_heads(), "k", 0)
    assert m.response["counts"]["topics"] == 4
    by_topic = {}
    for page in m.response["pages"]:
        by_topic.setdefault(page["topic"], set()).add(page["id"].split("-")[1])
    assert all(len(names) == 1 for names in by_topic.values())  # no topic mixes subjects


@pytest.mark.parametrize("n", [10, 14, 30, 60])
def test_k_selection_stays_in_range(n):
    rng = np.random.default_rng(n)
    reduced = rng.normal(size=(n, 8))
    k, labels = choose_k(reduced)
    assert 2 <= k <= min(12, n // 3)
    assert len(labels) == n


def test_outliers_are_unclustered_and_placed_between_topics():
    odd = _axis(200)  # unrelated to every topic
    outlier = {"page_id": "odd", "title": "Recipe for bread", "url": "https://bread.example.com",
               "domain": "bread.example.com", "timestamp": "2024-02-01T00:00:00Z", "page_embedding": odd.tolist()}
    m = build_map(make_heads(extra=[outlier]), "k", 0).response
    page = next(p for p in m["pages"] if p["id"] == "odd")
    assert page["topic"] is None
    assert m["counts"]["unclustered"] == 1
    assert 0 <= page["x"] <= 1 and 0 <= page["y"] <= 1
    for topic in m["topics"]:  # not inside any topic ellipse
        dx, dy = (page["x"] - topic["x"]) / topic["rx"], (page["y"] - topic["y"]) / topic["ry"]
        assert dx * dx + dy * dy > 0.5


def test_layout_is_inside_the_unit_box_and_topics_do_not_overlap():
    m = build_map(make_heads(), "k", 0).response
    for p in m["pages"]:
        assert 0 <= p["x"] <= 1 and 0 <= p["y"] <= 1
    topics = m["topics"]
    for i in range(len(topics)):
        for j in range(i + 1, len(topics)):
            a, b = topics[i], topics[j]
            assert np.hypot(a["x"] - b["x"], a["y"] - b["y"]) >= (a["rx"] + b["rx"]) * 0.99
    # Bigger topics get bigger ellipses (radius grows with sqrt(count)).
    by_count = sorted(topics, key=lambda t: t["count"])
    assert by_count[0]["rx"] <= by_count[-1]["rx"]


def test_edges_link_neighbours_within_topics():
    m = build_map(make_heads(), "k", 0).response
    topic_of = {p["id"]: p["topic"] for p in m["pages"]}
    intra = [e for e in m["edges"] if e["kind"] == "intra"]
    assert intra
    assert all(topic_of[e["a"]] == topic_of[e["b"]] for e in intra)
    degree = {}
    for e in intra:
        degree[e["a"]] = degree.get(e["a"], 0) + 1
        degree[e["b"]] = degree.get(e["b"], 0) + 1
    assert all(d >= 1 for d in degree.values())


def test_cross_edges_join_similar_topics_only():
    heads = make_heads()
    # Make "search" lean towards "ml" so their centroids are similar.
    for h in heads:
        if "-search-" in h["page_id"]:
            v = np.array(h["page_embedding"]) + 1.0 * _axis(0)
            h["page_embedding"] = (v / np.linalg.norm(v)).tolist()
    m = build_map(heads, "k", 0).response
    topic_of = {p["id"]: p["topic"] for p in m["pages"]}
    cross = [e for e in m["edges"] if e["kind"] == "cross"]
    assert len(cross) == 1
    names = {e.split("-")[1] for e in (cross[0]["a"], cross[0]["b"])}
    assert names == {"ml", "search"}
    assert topic_of[cross[0]["a"]] != topic_of[cross[0]["b"]]


def test_too_few_pages():
    heads = make_heads()[:9]
    assert build_map(heads, "k", 0).response == {
        "status": "too_few", "count": 9,
        "counts": {"pages": 9, "topics": 0, "unclustered": 0, "without_vectors": 0},
    }


def test_pages_without_vectors_are_counted_not_mapped():
    heads = make_heads()
    heads.append({"page_id": "old", "title": "Saved before vectors", "page_embedding": None})
    m = build_map(heads, "k", 0).response
    assert m["counts"]["without_vectors"] == 1
    assert all(p["id"] != "old" for p in m["pages"])


# ---- labels ------------------------------------------------------------------

def test_labels_fall_back_to_ctfidf_without_gemini():
    m = build_map(make_heads(), "k", 0, labeler=None).response
    labels = {t["label"] for t in m["topics"]}
    assert any("Search" in l for l in labels)
    assert any("Sleep" in l or "Memory" in l for l in labels)
    assert all(1 <= len(l.split()) <= 3 for l in labels)


def test_labels_fall_back_when_gemini_fails():
    failing = MagicMock(side_effect=RuntimeError("quota"))
    m = build_map(make_heads(), "k", 0, labeler=failing).response
    assert all(t["label"] for t in m["topics"])
    failing.assert_called_once()


def test_gemini_labels_are_used_and_cached():
    labeler = MagicMock(side_effect=lambda groups: [f"Label {i}" for i in range(len(groups))])
    cache = OrderedDict()
    m = build_map(make_heads(), "k", 0, labeler=labeler, label_cache=cache).response
    assert [t["label"] for t in m["topics"]] == ["Label 0", "Label 1", "Label 2", "Label 3"]
    groups = labeler.call_args.args[0]
    assert all(len(g) <= 10 for g in groups)
    build_map(make_heads(), "k2", 1, labeler=labeler, label_cache=cache)
    labeler.assert_called_once()  # second build reused every label


def test_partial_gemini_labels_mix_with_fallback():
    labeler = MagicMock(side_effect=lambda groups: [None] + ["Named"] * (len(groups) - 1))
    m = build_map(make_heads(), "k", 0, labeler=labeler).response
    assert m["topics"][0]["label"] != "Named"
    assert all(t["label"] == "Named" for t in m["topics"][1:])


def test_ctfidf_prefers_distinctive_words():
    groups = [
        [{"title": "Neural networks and learning"}, {"title": "Learning with neural networks"}],
        [{"title": "Sleep and memory"}, {"title": "Memory during sleep"}],
    ]
    labels = ctfidf_labels(groups)
    assert labels[0].split()[0] in ("Neural", "Networks", "Learning")
    assert labels[1].split()[0] in ("Sleep", "Memory")


# ---- service: cache, topics, search --------------------------------------------

def _service_solr(heads):
    solr = MagicMock()
    solr.scan_page_heads.side_effect = lambda user_id, fields, limit: iter(heads)
    return solr


def test_service_caches_until_invalidated():
    service = MapService(ttl_seconds=600)
    solr = _service_solr(make_heads())
    first = service.get("u", solr)
    assert service.get("u", solr) is first
    assert solr.scan_page_heads.call_count == 1
    service.invalidate("u")
    second = service.get("u", solr)
    assert second is not first
    assert second.response["version"] != first.response["version"]
    assert solr.scan_page_heads.call_count == 2


def test_service_ttl_expires():
    service = MapService(ttl_seconds=0)
    solr = _service_solr(make_heads())
    service.get("u", solr)
    service.get("u", solr)
    assert solr.scan_page_heads.call_count == 2


def test_service_is_an_lru_per_user():
    service = MapService(max_users=2)
    solr = _service_solr(make_heads())
    for user in ("a", "b", "c"):
        service.get(user, solr)
    assert service.peek("a") is None
    assert service.peek("b") is not None and service.peek("c") is not None


def test_topic_page_ids_and_staleness():
    service = MapService()
    m = service.get("u", _service_solr(make_heads()))
    topic = m.response["topics"][0]
    ids = service.topic_page_ids("u", topic["id"])
    assert len(ids) == topic["count"]
    with pytest.raises(StaleMap):
        service.topic_page_ids("u", "nope-0")
    service.invalidate("u")
    with pytest.raises(StaleMap):
        service.topic_page_ids("u", topic["id"])
    with pytest.raises(StaleMap):
        service.topic_page_ids("other-user", topic["id"])


def test_collection_search_finds_a_topic_from_a_paraphrase():
    """'neural nets' isn't a label, but its (mocked) embedding sits near the ML pages."""
    labeler = MagicMock(side_effect=lambda groups: [
        "Machine learning" if any("neural" in t.lower() for t in g) else
        "Search and retrieval" if any("search" in t.lower() for t in g) else
        "Sleep and memory" if any("sleep" in t.lower() for t in g) else "Interface design"
        for g in groups
    ])
    service = MapService()
    solr = _service_solr(make_heads())
    neural_nets = _axis(0) * 0.8 + _axis(300) * 0.6  # mostly the ML direction
    found = service.search("u", solr, neural_nets, labeler, min_similarity=0.55)
    assert found["topics"][0]["label"] == "Machine learning"
    assert all(t["score"] >= 0.55 for t in found["topics"])
    assert found["pages"] and all("-ml-" in p for p in found["pages"])


def test_collection_search_with_no_match():
    service = MapService()
    found = service.search("u", _service_solr(make_heads()), _axis(350), None, min_similarity=0.55)
    assert found["topics"] == [] and found["pages"] == []


def test_build_time_for_2000_pages():
    rng = np.random.default_rng(1)
    centers = rng.normal(size=(6, DIM))
    heads = []
    for i in range(2000):
        v = centers[i % 6] + rng.normal(scale=0.9, size=DIM)
        heads.append({"page_id": f"p{i}", "title": f"Page {i}", "page_embedding": (v / np.linalg.norm(v)).tolist()})
    build_map(heads, "warm", 0)
    import time
    started = time.perf_counter()
    m = build_map(heads, "k", 0)
    elapsed = time.perf_counter() - started
    assert m.response["counts"]["pages"] == 2000
    assert elapsed < 2.0  # ~0.5 s on a dev laptop; generous for slow CI machines


def test_unrelated_pages_do_not_form_a_topic():
    """Four mutually unrelated pages are each 0.5 similar to their mean, which
    would pass the outlier threshold; the coherence rule leaves them unclustered."""
    extra = [
        {"page_id": f"odd{i}", "title": f"Unrelated {i}", "url": f"https://x.example.com/{i}",
         "domain": "x.example.com", "timestamp": "2024-02-01T00:00:00Z", "page_embedding": _axis(300 + i).tolist()}
        for i in range(4)
    ]
    m = build_map(make_heads(extra=extra), "k", 0).response
    assert m["counts"]["topics"] == 4
    assert m["counts"]["unclustered"] == 4
    assert all(p["topic"] is None for p in m["pages"] if p["id"].startswith("odd"))
