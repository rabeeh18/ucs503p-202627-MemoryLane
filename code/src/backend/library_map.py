"""Library map: topics, layout and links computed from page vectors.

Nothing here is persisted. `build_map` turns a user's page vectors into
topics (k-means, k chosen by silhouette score), a 2-D layout in a 0..1 box,
edges and labels. `MapService` caches the result per user (LRU) and is
invalidated whenever that user's library changes.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.utils.extmath import randomized_svd

from backend.config import (
    MAP_CACHE_TTL_SECONDS, MAP_CACHE_USERS, MAP_CROSS_TOPIC_SIMILARITY, MAP_MAX_PAGES,
    MAP_MIN_PAGES, MAP_OUTLIER_SIMILARITY, MIN_VECTOR_SIMILARITY,
)

logger = logging.getLogger(__name__)

RANDOM_STATE = 0
MAX_TOPICS = 12
REDUCED_DIMS = 32
SILHOUETTE_SAMPLE = 600
INTRA_NEIGHBOURS = 2
HEAD_FIELDS = "page_id,url,title,domain,timestamp,description,page_embedding"

Labeler = Callable[[list[list[str]]], "list[str | None] | None"]


# ---- helpers ------------------------------------------------------------------

def _normalize_rows(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def _normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v


def _project(m: np.ndarray, dims: int) -> np.ndarray:
    """Coordinates of the rows on their top `dims` principal components.

    Randomized SVD with a fixed seed: deterministic, and far faster than a full
    decomposition when only a few components are needed. Signs are fixed so
    repeated builds give the same picture.
    """
    n, d = m.shape
    out = np.zeros((n, dims))
    if n < 2 or dims < 1:
        return out
    centred = m - m.mean(axis=0)
    comps = min(dims, n - 1, d)
    u, sv, _ = randomized_svd(centred, n_components=comps, n_iter=4, random_state=RANDOM_STATE)
    coords = u * sv
    for j in range(coords.shape[1]):
        if coords[np.argmax(np.abs(coords[:, j])), j] < 0:
            coords[:, j] *= -1
    out[:, :comps] = coords
    return out


def _pca_2d(m: np.ndarray) -> np.ndarray:
    """2-D principal-component coordinates of the rows (zeros where undefined)."""
    return _project(m, 2)


def _scale_into(points: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Scale each axis independently into [lo, hi] (centre when flat)."""
    out = np.empty_like(points, dtype=float)
    for j in range(points.shape[1]):
        col = points[:, j]
        span = col.max() - col.min() if len(col) else 0.0
        out[:, j] = (lo + hi) / 2 if span < 1e-12 else lo + (col - col.min()) / span * (hi - lo)
    return out


# ---- clustering ----------------------------------------------------------------

def choose_k(reduced: np.ndarray) -> tuple[int, np.ndarray]:
    """k-means for k in 2..min(12, n//3); keep the k with the best silhouette
    score (ties go to the smaller k). Returns (k, labels)."""
    n = reduced.shape[0]
    k_max = max(2, min(MAX_TOPICS, n // 3))
    best = (-2.0, 2, None)
    for k in range(2, k_max + 1):
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=2, max_iter=150)
        labels = model.fit_predict(reduced)
        if len(set(labels.tolist())) < 2:
            continue
        score = silhouette_score(
            reduced, labels, sample_size=min(n, SILHOUETTE_SAMPLE), random_state=RANDOM_STATE,
        )
        if score > best[0] + 1e-9:
            best = (score, k, labels)
    if best[2] is None:  # everything identical: one cluster
        return 1, np.zeros(n, dtype=int)
    return best[1], best[2]


def cluster(vectors: np.ndarray, outlier_similarity: float = None) -> tuple[np.ndarray, np.ndarray]:
    """Topic index per page (-1 = unclustered) and topic centroids (unit rows),
    topics ordered by size (largest first)."""
    if outlier_similarity is None:
        outlier_similarity = MAP_OUTLIER_SIMILARITY
    n, d = vectors.shape
    reduced = _normalize_rows(_project(vectors, min(REDUCED_DIMS, n - 1, d)))

    _, labels = choose_k(reduced)

    def centroids_for(lbls):
        ids = sorted(set(lbls.tolist()) - {-1})
        return ids, np.array([_normalize(vectors[lbls == t].mean(axis=0)) for t in ids])

    ids, cents = centroids_for(labels)
    sims = np.einsum("ij,ij->i", vectors, cents[[ids.index(t) for t in labels]])
    labels = np.where(sims < outlier_similarity, -1, labels)

    # A topic must hang together: at least 2 pages that are, on average, as
    # similar to each other as the outlier threshold. Otherwise a handful of
    # unrelated pages (whose mean is equally close to all of them) would pose
    # as a topic; their pages become unclustered instead.
    for t in set(labels.tolist()) - {-1}:
        members = np.where(labels == t)[0]
        if len(members) < 2:
            labels[members] = -1
            continue
        pair = vectors[members] @ vectors[members].T
        mean_pair = (pair.sum() - np.trace(pair)) / (len(members) * (len(members) - 1))
        if mean_pair < outlier_similarity:
            labels[members] = -1

    # Renumber the surviving topics by size and recompute their centroids.
    sizes = Counter(t for t in labels.tolist() if t != -1)
    order = [t for t, _ in sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))]
    remap = {old: new for new, old in enumerate(order)}
    topic_of = np.array([remap.get(t, -1) for t in labels.tolist()], dtype=int)
    if not order:
        return topic_of, np.zeros((0, d))
    centroids = np.array([_normalize(vectors[topic_of == t].mean(axis=0)) for t in range(len(order))])
    return topic_of, centroids


# ---- layout --------------------------------------------------------------------

def topic_radii(counts: Sequence[int]) -> np.ndarray:
    """(rx, ry) per topic; radii grow with sqrt(page count)."""
    rx = np.array([0.045 + 0.028 * math.sqrt(c) for c in counts])
    return np.stack([rx, rx * 0.72], axis=1)


def separate(centres: np.ndarray, radii: np.ndarray, iterations: int = 200, gap: float = 1.25) -> np.ndarray:
    """Push overlapping topic ellipses apart (treated as circles of radius rx)."""
    pos = centres.astype(float).copy()
    k = len(pos)
    rng = np.random.default_rng(RANDOM_STATE)
    for _ in range(iterations):
        moved = False
        for i in range(k):
            for j in range(i + 1, k):
                need = (radii[i, 0] + radii[j, 0]) * gap
                delta = pos[j] - pos[i]
                dist = float(np.hypot(*delta))
                if dist >= need:
                    continue
                direction = delta / dist if dist > 1e-9 else _normalize(rng.normal(size=2))
                shift = direction * (need - dist) / 2
                pos[i] -= shift
                pos[j] += shift
                moved = True
        if not moved:
            break
    return pos


def fit_box(pos: np.ndarray, radii: np.ndarray, margin: float = 0.06, top_room: float = 0.05):
    """Uniformly scale and translate topics (centres and radii) into 0..1,
    leaving room above each ellipse for its label."""
    lo = (pos - radii).min(axis=0)
    hi = (pos + radii).max(axis=0)
    lo[1] -= top_room
    span = np.maximum(hi - lo, 1e-9)
    avail = 1 - 2 * margin
    scale = min(avail / span[0], avail / span[1], 2.5)
    offset = margin + (avail - span * scale) / 2
    return (pos - lo) * scale + offset, radii * scale


def layout(vectors: np.ndarray, topic_of: np.ndarray, centroids: np.ndarray):
    """Page positions (n, 2), topic centres (k, 2) and radii (k, 2) in 0..1."""
    n = len(vectors)
    k = len(centroids)
    points = np.zeros((n, 2))
    if k == 0:
        return _scale_into(_pca_2d(vectors), 0.1, 0.9), np.zeros((0, 2)), np.zeros((0, 2))

    counts = [int((topic_of == t).sum()) for t in range(k)]
    centres = _scale_into(_pca_2d(centroids), 0.2, 0.8) if k > 1 else np.array([[0.5, 0.5]])
    radii = topic_radii(counts)
    centres, radii = fit_box(separate(centres, radii), radii)

    for t in range(k):
        members = np.where(topic_of == t)[0]
        local = _pca_2d(vectors[members]) if len(members) > 2 else (
            np.array([[-1.0, 0.0], [1.0, 0.0]]) if len(members) == 2 else np.zeros((1, 2)))
        # Spread pages across the ellipse: scale by a high percentile of their
        # distances (one far page shouldn't squash the rest into the middle),
        # then pull the few beyond it back onto the rim.
        norms = np.linalg.norm(local, axis=1)
        scale = float(np.percentile(norms, 85)) if len(norms) > 4 else float(norms.max())
        if scale > 0:
            local = local / scale
            norms = np.linalg.norm(local, axis=1)
            over = norms > 1
            local[over] = local[over] / norms[over][:, None]
        points[members] = centres[t] + local * radii[t] * 0.72

    # Unclustered pages sit between the two topics they are closest to.
    for i in np.where(topic_of == -1)[0]:
        sims = centroids @ vectors[i]
        order = np.argsort(-sims)
        jitter = (int(hashlib.md5(str(i).encode()).hexdigest()[:4], 16) / 0xFFFF - 0.5) * 0.06
        if k == 1:
            angle = 2 * math.pi * ((i * 0.618) % 1)
            points[i] = centres[0] + (radii[0] + 0.06) * np.array([math.cos(angle), math.sin(angle)])
        else:
            a, b = order[0], order[1]
            wa, wb = max(sims[a], 1e-3), max(sims[b], 1e-3)
            mid = (centres[a] * wa + centres[b] * wb) / (wa + wb)
            normal = np.array([-(centres[b] - centres[a])[1], (centres[b] - centres[a])[0]])
            points[i] = mid + _normalize(normal) * jitter
        points[i] = _outside_topics(points[i], centres, radii)
    return np.clip(points, 0.02, 0.98), centres, radii


def _inside(point: np.ndarray, centres: np.ndarray, radii: np.ndarray, pad: float = 1.15) -> bool:
    d = (point - centres) / radii
    return bool(((d ** 2).sum(axis=1) < pad ** 2).any())


def _outside_topics(point: np.ndarray, centres: np.ndarray, radii: np.ndarray) -> np.ndarray:
    """Nudge an unclustered page out of every topic ellipse: try points on
    growing rings around it and keep the first one that is clear (and in the box)."""
    if not _inside(point, centres, radii):
        return point
    for step in range(1, 40):
        r = 0.015 * step
        for a in range(16):
            angle = 2 * math.pi * a / 16
            candidate = point + r * np.array([math.cos(angle), math.sin(angle)])
            if (0.02 <= candidate).all() and (candidate <= 0.98).all() and not _inside(candidate, centres, radii):
                return candidate
    return point


# ---- edges ----------------------------------------------------------------------

def build_edges(vectors: np.ndarray, topic_of: np.ndarray, centroids: np.ndarray,
                cross_similarity: float = None) -> list[tuple[int, int, str]]:
    """Each page links to its 2 nearest neighbours in its topic ("intra"); any two
    topics with similar centroids get one dashed link between their closest
    pages ("cross")."""
    if cross_similarity is None:
        cross_similarity = MAP_CROSS_TOPIC_SIMILARITY
    edges: set[tuple[int, int, str]] = set()
    members = [np.where(topic_of == t)[0] for t in range(len(centroids))]
    for idx in members:
        if len(idx) < 2:
            continue
        sims = vectors[idx] @ vectors[idx].T
        np.fill_diagonal(sims, -np.inf)
        for row, i in enumerate(idx):
            for col in np.argsort(-sims[row])[:INTRA_NEIGHBOURS]:
                j = idx[col]
                edges.add((min(i, j), max(i, j), "intra"))
    if len(centroids) > 1:
        topic_sims = centroids @ centroids.T
        for a in range(len(centroids)):
            for b in range(a + 1, len(centroids)):
                if topic_sims[a, b] < cross_similarity:
                    continue
                block = vectors[members[a]] @ vectors[members[b]].T
                r, c = np.unravel_index(int(np.argmax(block)), block.shape)
                i, j = members[a][r], members[b][c]
                edges.add((min(i, j), max(i, j), "cross"))
    return sorted(edges)


# ---- labels ----------------------------------------------------------------------

_WORD = re.compile(r"[a-z][a-z0-9]{2,}")
_STOP = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "how", "its", "with",
    "from", "this", "that", "what", "when", "why", "who", "your", "about", "into", "over", "more",
    "most", "than", "then", "they", "them", "their", "there", "were", "was", "will", "would", "has",
    "have", "had", "our", "out", "new", "use", "using", "used", "get", "via", "per", "one", "two",
    "best", "guide", "introduction", "intro", "page", "pages", "home", "blog", "post", "article",
    "www", "com", "org", "net", "http", "https", "html", "wikipedia", "encyclopedia", "free", "wiki",
    "read", "online", "official", "site", "website", "news", "vs", "part", "chapter", "tutorial",
}


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall((text or "").lower()) if w not in _STOP]


def ctfidf_labels(groups: list[list[dict]]) -> list[str]:
    """Keyword labels per topic from titles (weighted 2x) and descriptions,
    using class-based TF-IDF: tf(t, c) * log(1 + A / f(t))."""
    counts = []
    for pages in groups:
        c = Counter()
        for p in pages:
            for _ in range(2):
                c.update(_tokens(p.get("title", "")))
            c.update(_tokens(p.get("description", "")))
        counts.append(c)
    total = Counter()
    for c in counts:
        total.update(c)
    avg = (sum(sum(c.values()) for c in counts) / max(len(counts), 1)) or 1.0
    labels = []
    for i, c in enumerate(counts):
        size = sum(c.values())
        if not size:
            labels.append(f"Topic {i + 1}")
            continue
        scored = sorted(
            ((c[t] / size) * math.log(1 + avg / total[t]), t) for t in c
        )[::-1]
        first = scored[0][1]
        words = [first]
        for weight, term in scored[1:4]:
            if weight >= 0.5 * scored[0][0] and term[:4] != first[:4]:
                words.append(term)
                break
        label = " and ".join(words) if len(words) == 2 else first
        labels.append(label[:1].upper() + label[1:])
    return labels


# ---- the map ------------------------------------------------------------------

@dataclass
class LibraryMap:
    key: str
    version: int
    built_at: float
    response: dict
    page_ids: list[str] = field(default_factory=list)
    vectors: np.ndarray | None = None
    topic_of: np.ndarray | None = None
    centroids: np.ndarray | None = None
    topic_ids: list[str] = field(default_factory=list)

    def topic_index(self, topic_id: str) -> int | None:
        try:
            return self.topic_ids.index(topic_id)
        except ValueError:
            return None

    def topic_page_ids(self, topic_id: str) -> list[str] | None:
        t = self.topic_index(topic_id)
        if t is None:
            return None
        return [self.page_ids[i] for i in np.where(self.topic_of == t)[0]]


def _topic_label(labels_from_model, fallback, t):
    if labels_from_model and t < len(labels_from_model) and labels_from_model[t]:
        return labels_from_model[t]
    return fallback[t]


def build_map(heads: list[dict], key: str, version: int, labeler: Labeler | None = None,
              label_cache: "OrderedDict[str, str] | None" = None) -> LibraryMap:
    """Map for one user's page heads (chunk 0 docs with `page_embedding`)."""
    pages = [h for h in heads if h.get("page_embedding")]
    without_vectors = len(heads) - len(pages)
    counts = {"pages": len(pages), "topics": 0, "unclustered": 0, "without_vectors": without_vectors}
    if len(pages) < MAP_MIN_PAGES:
        return LibraryMap(key, version, time.time(), {"status": "too_few", "count": len(pages), "counts": counts})

    vectors = _normalize_rows(np.array([p["page_embedding"] for p in pages], dtype=float))
    topic_of, centroids = cluster(vectors)
    points, centres, radii = layout(vectors, topic_of, centroids)
    edges = build_edges(vectors, topic_of, centroids)
    k = len(centroids)

    groups = [[pages[i] for i in np.where(topic_of == t)[0]] for t in range(k)]
    fallback = ctfidf_labels(groups)
    # Reuse labels for topics whose pages haven't changed since the last build.
    cache_keys = [hashlib.sha1("|".join(sorted(p["page_id"] for p in g)).encode()).hexdigest() for g in groups]
    cached = [label_cache.get(ck) if label_cache is not None else None for ck in cache_keys]
    model_labels = list(cached)
    missing = [t for t in range(k) if not cached[t]]
    if missing and labeler is not None:
        titles = [[p.get("title") or "" for p in groups[t][:10]] for t in missing]
        try:
            fresh = labeler(titles) or []
        except Exception as e:  # labels must never break the map
            logger.warning(f"Topic labeller failed: {e}")
            fresh = []
        for t, label in zip(missing, fresh):
            if label:
                model_labels[t] = label
                if label_cache is not None:
                    label_cache[cache_keys[t]] = label
                    while len(label_cache) > 500:
                        label_cache.popitem(last=False)

    topic_ids = [f"{key}-{t}" for t in range(k)]
    topics = [
        {
            "id": topic_ids[t],
            "label": _topic_label(model_labels, fallback, t),
            "count": len(groups[t]),
            "x": round(float(centres[t, 0]), 4),
            "y": round(float(centres[t, 1]), 4),
            "rx": round(float(radii[t, 0]), 4),
            "ry": round(float(radii[t, 1]), 4),
        }
        for t in range(k)
    ]
    out_pages = [
        {
            "id": p["page_id"],
            "title": p.get("title") or p.get("url") or "",
            "url": p.get("url") or "",
            "domain": p.get("domain") or "",
            "saved_at": str(p.get("timestamp") or ""),
            "x": round(float(points[i, 0]), 4),
            "y": round(float(points[i, 1]), 4),
            "topic": topic_ids[topic_of[i]] if topic_of[i] >= 0 else None,
        }
        for i, p in enumerate(pages)
    ]
    out_edges = [{"a": pages[a]["page_id"], "b": pages[b]["page_id"], "kind": kind} for a, b, kind in edges]
    counts.update(topics=k, unclustered=int((topic_of == -1).sum()))
    response = {"status": "ok", "version": key, "topics": topics, "pages": out_pages,
                "edges": out_edges, "counts": counts}
    return LibraryMap(key, version, time.time(), response, [p["page_id"] for p in pages],
                      vectors, topic_of, centroids, topic_ids)


# ---- per-user cache ----------------------------------------------------------------

class StaleMap(Exception):
    """The client's topic id refers to a map that is no longer current."""


class MapService:
    """LRU of built maps keyed by user; a per-user version bumps on every save
    or delete so the next request rebuilds. A TTL also covers changes made by
    other processes (re-index and backfill scripts)."""

    def __init__(self, max_users: int = None, ttl_seconds: float = None):
        self.max_users = max_users or MAP_CACHE_USERS
        self.ttl = ttl_seconds if ttl_seconds is not None else MAP_CACHE_TTL_SECONDS
        self._maps: OrderedDict[str, LibraryMap] = OrderedDict()
        self._versions: dict[str, int] = {}
        self._labels: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()

    def version(self, user_id: str) -> int:
        return self._versions.get(user_id, 0)

    def invalidate(self, user_id: str) -> None:
        with self._lock:
            self._versions[user_id] = self.version(user_id) + 1
            self._maps.pop(user_id, None)

    def _fresh(self, entry: LibraryMap | None, user_id: str) -> bool:
        return (entry is not None and entry.version == self.version(user_id)
                and time.time() - entry.built_at < self.ttl)

    def peek(self, user_id: str) -> LibraryMap | None:
        """The cached map if it is still current; never builds."""
        with self._lock:
            entry = self._maps.get(user_id)
            return entry if self._fresh(entry, user_id) else None

    def get(self, user_id: str, solr, labeler: Labeler | None = None) -> LibraryMap:
        entry = self.peek(user_id)
        if entry is not None:
            with self._lock:
                self._maps.move_to_end(user_id)
            return entry
        version = self.version(user_id)
        heads = list(solr.scan_page_heads(user_id, HEAD_FIELDS, MAP_MAX_PAGES))
        key = hashlib.sha1(f"{user_id}|{version}|{time.time()}".encode()).hexdigest()[:8]
        started = time.perf_counter()
        built = build_map(heads, key, version, labeler, self._labels)
        logger.info(f"Built library map: {len(heads)} pages in {(time.perf_counter() - started) * 1000:.0f} ms")
        with self._lock:
            if self.version(user_id) == version:  # not invalidated while building
                self._maps[user_id] = built
                self._maps.move_to_end(user_id)
                while len(self._maps) > self.max_users:
                    self._maps.popitem(last=False)
        return built

    def topic_page_ids(self, user_id: str, topic_id: str) -> list[str]:
        """Page ids of a topic in the current map; StaleMap if the map has changed."""
        entry = self.peek(user_id)
        if entry is None or entry.vectors is None:
            raise StaleMap()
        ids = entry.topic_page_ids(topic_id)
        if ids is None:
            raise StaleMap()
        return ids

    def search(self, user_id: str, solr, query_vector: Sequence[float],
               labeler: Labeler | None = None, min_similarity: float = None) -> dict:
        """Topics and pages close to a query vector, using the cached map."""
        if min_similarity is None:
            min_similarity = MIN_VECTOR_SIMILARITY
        entry = self.get(user_id, solr, labeler)
        if entry.vectors is None or not len(entry.topic_ids):
            return {"version": entry.response.get("version"), "topics": [], "pages": []}
        q = _normalize(np.asarray(query_vector, dtype=float))
        page_sims = entry.vectors @ q
        centroid_sims = entry.centroids @ q
        topics = []
        for t, topic in enumerate(entry.response["topics"]):
            member_sims = np.sort(page_sims[entry.topic_of == t])[::-1][:3]
            # A topic matches its centre or a few of its pages: names that aren't
            # the label ("neural nets" for "Machine learning") still land.
            score = max(float(centroid_sims[t]), float(member_sims.mean()) if len(member_sims) else -1.0)
            if score >= min_similarity:
                topics.append({"id": topic["id"], "label": topic["label"], "score": round(score, 4)})
        topics.sort(key=lambda t: -t["score"])
        pages = [entry.page_ids[i] for i in np.argsort(-page_sims) if page_sims[i] >= min_similarity]
        return {"version": entry.response["version"], "topics": topics, "pages": pages}


map_service = MapService()
