"""The personal evaluation scripts: loading, the saved-URL check, per-category metrics, comparison."""
import io
import json

from backend.url_utils import generate_page_id, normalize_url
from evaluation import compare, evaluate, generate_eval

USER = "user-a"
SAVED = [
    "https://www.reddit.com/r/rust/comments/abc/lifetimes",
    "https://github.com/acme/widget",
    "https://docs.example.org/guide/install",
]


class FakeSolr:
    def __init__(self, urls=SAVED, user_id=USER):
        self.pages = {generate_page_id(user_id, normalize_url(u)): u for u in urls}
        self.user_id = user_id

    def get_page_head(self, page_id, user_id):
        if user_id != self.user_id or page_id not in self.pages:
            return None
        return {"page_id": page_id, "url": self.pages[page_id]}

    def scan_page_heads(self, user_id, fields, limit):
        for i, url in enumerate(self.pages.values()):
            yield {"url": url, "title": f"Page {i}", "domain": "x"}

    def _select(self, params):
        return {"facet_counts": {"facet_fields": {"user_id": ["small", 2, USER, 3]}}}


def fake_search(order):
    """A search that returns `order[query]` as the ranked URLs."""
    calls = []

    def search(query, user_id, top_k, candidate_pool, solr, snippets):
        calls.append({"query": query, "snippets": snippets})
        return [{"url": u} for u in order.get(query, [])]

    search.calls = calls
    return search


def run(queries, order):
    search = fake_search(order)
    return evaluate.evaluate(queries, 10, 50, FakeSolr(), USER, search=search), search


def test_metrics_by_category_and_rank():
    queries = [
        {"id": "a", "category": "Site", "query": "reddit rust", "relevant_urls": [SAVED[0]]},
        {"id": "b", "category": "topic", "query": "widget lib", "relevant_urls": [SAVED[1]]},
        {"id": "c", "query": "install guide", "relevant_urls": [SAVED[2]]},
    ]
    order = {
        "reddit rust": [SAVED[0], SAVED[1]],
        "widget lib": [SAVED[0], SAVED[2], SAVED[1]],
        "install guide": [SAVED[0]],
    }
    report, search = run(queries, order)

    ranks = {r["id"]: r["rank"] for r in report["details"]}
    assert ranks == {"a": 1, "b": 3, "c": None}
    assert report["metrics"]["n_queries"] == 3
    assert report["metrics"]["recall@1"] == 1 / 3
    assert report["metrics"]["recall@3"] == 2 / 3
    assert abs(report["metrics"]["mrr"] - (1 + 1 / 3) / 3) < 1e-9
    assert set(report["by_category"]) == {"site", "topic", "uncategorised"}
    assert report["by_category"]["topic"]["mrr"] == 1 / 3
    assert all(call["snippets"] is False for call in search.calls)


def test_urls_are_compared_normalised():
    queries = [{"id": "a", "query": "q", "relevant_urls": ["https://github.com/acme/widget/"]}]
    report, _ = run(queries, {"q": ["https://github.com/acme/widget#readme"]})
    assert report["details"][0]["rank"] == 1


def test_unsaved_urls_are_reported_not_scored():
    queries = [
        {"id": "gone", "query": "q1", "relevant_urls": ["https://www.reddit.com/"]},
        {"id": "half", "query": "q2", "relevant_urls": [SAVED[1], "https://nowhere.example/x"]},
        {"id": "blank", "query": "  ", "relevant_urls": [SAVED[0]]},
    ]
    report, search = run(queries, {"q2": [SAVED[1]]})

    assert [s["id"] for s in report["skipped"]["not_saved"]] == ["gone"]
    assert report["skipped"]["empty"] == ["blank"]
    assert [c["query"] for c in search.calls] == ["q2"]
    assert report["details"][0]["missing_urls"] == ["https://nowhere.example/x"]
    assert report["metrics"]["n_queries"] == 1


def test_other_users_pages_count_as_not_saved():
    queries = [{"id": "a", "query": "q", "relevant_urls": [SAVED[0]]}]
    report = evaluate.evaluate(queries, 10, 50, FakeSolr(user_id="someone-else"), USER,
                               search=fake_search({}))
    assert report["skipped"]["not_saved"][0]["id"] == "a"


def test_load_queries_from_stdin(monkeypatch):
    payload = {"queries": [{"id": "a", "query": "q", "relevant_urls": [SAVED[0]]}]}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert evaluate.load_queries("-") == payload["queries"]


def test_starter_set_has_empty_queries_and_stored_urls():
    payload = generate_eval.starter(2, FakeSolr(), USER, seed=1)
    assert len(payload["queries"]) == 2
    assert set(payload["categories"]) == set(evaluate.CATEGORIES)
    for item in payload["queries"]:
        assert item["query"] == "" and item["category"] == ""
        assert item["relevant_urls"][0] in SAVED
        assert item["title"]
    # Same seed, same sample.
    assert generate_eval.starter(2, FakeSolr(), USER, seed=1) == payload


def test_list_users_most_pages_first():
    assert generate_eval.list_users(FakeSolr()) == [(USER, 3), ("small", 2)]


def test_compare_shows_deltas_and_rank_changes():
    def report(ranks, mrr):
        details = [{"id": i, "query": f"q{i}", "rank": r} for i, r in ranks.items()]
        m = {"recall@1": 0.5, "recall@3": 0.5, "recall@5": 1.0, "recall@10": 1.0,
             "mrr": mrr, "n_queries": len(ranks)}
        return {"metrics": m, "by_category": {"site": m}, "details": details}

    before = report({"a": 4, "b": 1, "c": None}, 0.4)
    after = report({"a": 1, "b": 2, "c": None}, 0.6)
    text = "\n".join(compare.compare(before, after))

    assert "+0.200" in text
    assert "better      a    #4 -> #1" in text
    assert "worse       b    #1 -> #2" in text
    assert "  c " not in text
