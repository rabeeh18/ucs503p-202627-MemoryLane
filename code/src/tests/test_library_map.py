from collections import Counter, OrderedDict
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


def test_related_topics_get_one_link_between_topics():
    heads = make_heads()
    # Make "search" lean towards "ml" so their centroids are similar.
    for h in heads:
        if "-search-" in h["page_id"]:
            v = np.array(h["page_embedding"]) + 1.0 * _axis(0)
            h["page_embedding"] = (v / np.linalg.norm(v)).tolist()
    m = build_map(heads, "k", 0).response
    topic_members = {}
    for page in m["pages"]:
        topic_members.setdefault(page["topic"], set()).add(page["id"].split("-")[1])
    assert len(m["topic_links"]) == 1
    link = m["topic_links"][0]
    assert topic_members[link["a"]] | topic_members[link["b"]] == {"ml", "search"}
    assert all(e["kind"] == "intra" for e in m["edges"])  # no page-to-page cross links


def test_topic_links_are_capped_per_topic():
    centroids = lm._normalize_rows(np.ones((6, 4)) + np.eye(6, 4) * 0.01)  # all very similar
    links = lm.build_topic_links(centroids, cross_similarity=0.5)
    degree = Counter(t for link in links for t in link)
    assert links and all(d <= lm.MAX_TOPIC_LINKS for d in degree.values())


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

def test_labels_fall_back_to_ctfidf_without_gemini(caplog):
    with caplog.at_level("WARNING"):
        m = build_map(make_heads(), "k", 0, labeler=None).response
    labels = [t["label"] for t in m["topics"]]
    assert any("Search" in l for l in labels)
    assert any("Sleep" in l or "Memory" in l for l in labels)
    assert all(1 <= len(l.split()) <= 3 for l in labels)
    assert len(set(labels)) == len(labels)
    assert "Gemini is not configured" in caplog.text


def test_labels_fall_back_when_gemini_fails(caplog):
    failing = MagicMock(side_effect=RuntimeError("quota"))
    with caplog.at_level("WARNING"):
        m = build_map(make_heads(), "k", 0, labeler=failing).response
    assert all(t["label"] for t in m["topics"])
    failing.assert_called_once()
    assert "Gemini call failed" in caplog.text and "quota" in caplog.text


def test_labeller_gets_hints_and_other_labels():
    labeler = MagicMock(side_effect=lambda groups, **kw: [f"Label {chr(65 + i)}" for i in range(len(groups))])
    cache = OrderedDict()
    build_map(make_heads(), "k", 0, labeler=labeler, label_cache=cache)
    kwargs = labeler.call_args.kwargs
    assert len(kwargs["hints"]) == len(labeler.call_args.args[0])
    assert kwargs["taken"] == []
    # Change one topic: only it is relabelled, and the others' labels are passed as taken.
    heads = make_heads()
    heads = [h for h in heads if h["page_id"] != "p-sleep-3"]
    build_map(heads, "k2", 1, labeler=labeler, label_cache=cache)
    assert len(labeler.call_args.args[0]) == 1
    assert sorted(labeler.call_args.kwargs["taken"]) == ["Label A", "Label B", "Label D"]


def test_generic_or_duplicate_gemini_labels_are_rejected(caplog):
    labeler = MagicMock(side_effect=lambda groups, **kw: ["Human patients", "Same", "Same", "Fine tuning"])
    with caplog.at_level("WARNING"):
        labels = [t["label"] for t in build_map(make_heads(), "k", 0, labeler=labeler).response["topics"]]
    assert labels[0] != "Human patients" and labels[2] != "Same"
    assert labels[1] == "Same" and labels[3] == "Fine tuning"
    assert len(set(labels)) == 4
    assert "rejected Gemini label 'Human patients'" in caplog.text


def test_gemini_labels_are_used_and_cached():
    labeler = MagicMock(side_effect=lambda groups, **kw: [f"Label {chr(65 + i)}" for i in range(len(groups))])
    cache = OrderedDict()
    m = build_map(make_heads(), "k", 0, labeler=labeler, label_cache=cache).response
    assert [t["label"] for t in m["topics"]] == ["Label A", "Label B", "Label C", "Label D"]
    groups = labeler.call_args.args[0]
    assert all(len(g) <= 10 for g in groups)
    build_map(make_heads(), "k2", 1, labeler=labeler, label_cache=cache)
    labeler.assert_called_once()  # second build reused every label


def test_partial_gemini_labels_mix_with_fallback():
    labeler = MagicMock(side_effect=lambda groups, **kw: [None] + [f"Named {i}" for i in range(1, len(groups))])
    m = build_map(make_heads(), "k", 0, labeler=labeler).response
    assert not m["topics"][0]["label"].startswith("Named")
    assert all(t["label"].startswith("Named") for t in m["topics"][1:])


def test_ctfidf_prefers_distinctive_bigrams_in_title_case():
    groups = [
        [{"title": "Neural networks for vision"}, {"title": "Training neural networks"}, {"title": "Neural networks explained"}],
        [{"title": "Sleep and memory"}, {"title": "Memory during sleep"}],
    ]
    labels = ctfidf_labels(groups)
    assert labels[0] == "Neural Networks"
    assert set(labels[1].split()) == {"Sleep", "Memory"}


def test_ctfidf_skips_generic_science_words():
    groups = [
        [{"title": "A study of human cells in patients"}, {"title": "Human cells and insulin resistance study"},
         {"title": "Patients with insulin resistance"}],
        [{"title": "Tumour immunity in patients"}, {"title": "Human tumour immunity results"}],
    ]
    labels = ctfidf_labels(groups)
    for label in labels:
        assert not {"Human", "Patients", "Study", "Cells", "Results"} & set(label.split())
    assert labels[0] == "Insulin Resistance"
    assert labels[1] == "Tumour Immunity"


def test_ctfidf_labels_are_distinct():
    groups = [[{"title": "Vector search basics"}, {"title": "Vector search tuning"}]] * 3
    labels = ctfidf_labels(groups)
    assert len(set(labels)) == 3


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
    labeler = MagicMock(side_effect=lambda groups, **kw: [
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


def _centres_heads(n, centres, seed=0, scale=0.9):
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(centres, DIM))
    heads = []
    for i in range(n):
        v = base[i % centres] + rng.normal(scale=scale, size=DIM)
        heads.append({"page_id": f"s{i}", "title": f"Page {i}", "page_embedding": (v / np.linalg.norm(v)).tolist()})
    return heads


def test_300_pages_from_9_centres_give_7_to_11_topics():
    m = build_map(_centres_heads(300, 9), "k", 0).response
    assert 7 <= m["counts"]["topics"] <= 11


@pytest.mark.parametrize("n,expected", [(10, (3, 3)), (24, (3, 3)), (278, (8, 14)), (300, (9, 14)), (2000, (10, 14))])
def test_k_range(n, expected):
    assert lm.k_range(n) == expected


def test_oversized_topics_are_split():
    rng = np.random.default_rng(0)
    reduced = lm._normalize_rows(rng.normal(size=(200, 8)))
    labels = np.zeros(200, dtype=int)
    labels[:20] = 1  # one topic holds 90% of the pages
    split = lm.split_large(reduced, labels)
    sizes = Counter(split.tolist())
    assert all(c <= 0.25 * 200 or c <= 30 for c in sizes.values())
    assert len(sizes) > 2


def test_small_topics_are_not_split():
    labels = np.array([0] * 30 + [1] * 10)
    reduced = lm._normalize_rows(np.random.default_rng(1).normal(size=(40, 4)))
    assert (lm.split_large(reduced, labels) == labels).all()


def _label_box(t):
    w = len(f"{t['label']} · {t['count']} pages") * 7.4
    cx, top = t["x"] * 1400, t["y"] * 900 - t["ry"] * 900 - 12
    return cx - w / 2, top - 13, cx + w / 2, top + 3


def test_layout_is_balanced_area_proportional_and_labels_clear():
    m = build_map(_centres_heads(300, 9), "k", 0).response
    topics = m["topics"]
    # Ellipse area (in world px) is proportional to the page count.
    ratios = [t["rx"] * 1400 * t["ry"] * 900 / t["count"] for t in topics]
    assert max(ratios) / min(ratios) == pytest.approx(1.0, rel=1e-3)
    # Centred both ways, and spread over most of the box in both directions.
    lo_x = min(t["x"] - t["rx"] for t in topics); hi_x = max(t["x"] + t["rx"] for t in topics)
    lo_y = min(t["y"] - t["ry"] for t in topics); hi_y = max(t["y"] + t["ry"] for t in topics)
    assert (lo_x + hi_x) / 2 == pytest.approx(0.5, abs=0.06)
    assert (lo_y + hi_y) / 2 == pytest.approx(0.5, abs=0.06)
    assert hi_x - lo_x > 0.5 and hi_y - lo_y > 0.5
    # No topic label sits on another topic's oval.
    for a in topics:
        x0, y0, x1, y1 = _label_box(a)
        for b in topics:
            if a is b:
                continue
            cx, cy, rx, ry = b["x"] * 1400, b["y"] * 900, b["rx"] * 1400, b["ry"] * 900
            nx, ny = min(max(cx, x0), x1), min(max(cy, y0), y1)
            assert ((nx - cx) / rx) ** 2 + ((ny - cy) / ry) ** 2 >= 1, (a["label"], b["label"])
