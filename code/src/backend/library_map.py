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
MAX_TOPICS = 14
REDUCED_DIMS = 50
# Topics holding more than this share of the pages (and more pages than
# SPLIT_MIN_PAGES) are split in two.
SPLIT_SHARE = 0.25
SPLIT_MIN_PAGES = 30
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

def k_range(n: int) -> tuple[int, int]:
    """Candidate topic counts: [clamp(round(sqrt(n)/2), 3, 10), min(14, n//8)].
    Small libraries (where n//8 falls below the minimum) may go up to n//4."""
    k_min = max(3, min(10, round(math.sqrt(n) / 2)))
    k_max = min(MAX_TOPICS, n // 8)
    if k_max < k_min:
        k_max = min(max(k_min, n // 4), max(2, n // 2))
    k_min = min(k_min, k_max)
    return max(2, k_min), max(2, k_max)


def choose_k(reduced: np.ndarray) -> tuple[int, np.ndarray]:
    """k-means (on unit vectors, i.e. cosine) for k in k_range(n); keep the k
    with the best silhouette score (ties go to the smaller k)."""
    n = reduced.shape[0]
    k_lo, k_hi = k_range(n)
    best = (-2.0, k_lo, None)
    for k in range(k_lo, min(k_hi, n - 1) + 1):
        labels = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=2, max_iter=150).fit_predict(reduced)
        if len(set(labels.tolist())) < 2:
            continue
        score = silhouette_score(reduced, labels, metric="cosine",
                                 sample_size=min(n, SILHOUETTE_SAMPLE), random_state=RANDOM_STATE)
        if score > best[0] + 1e-9:
            best = (score, k, labels)
    if best[2] is None:  # everything identical: one cluster
        return 1, np.zeros(n, dtype=int)
    return best[1], best[2]


def split_large(reduced: np.ndarray, labels: np.ndarray, max_share: float = SPLIT_SHARE,
                min_size: int = SPLIT_MIN_PAGES, max_rounds: int = 24) -> np.ndarray:
    """Split any topic holding more than `max_share` of the pages (and more than
    `min_size` pages) into two, repeating until none is left."""
    labels = labels.copy()
    n = len(labels)
    for _ in range(max_rounds):
        sizes = Counter(t for t in labels.tolist() if t != -1)
        big = [t for t, c in sizes.items() if c > max_share * n and c > min_size]
        if not big:
            break
        t = max(big, key=lambda x: sizes[x])
        members = np.where(labels == t)[0]
        halves = KMeans(n_clusters=2, random_state=RANDOM_STATE, n_init=2, max_iter=150).fit_predict(reduced[members])
        if len(set(halves.tolist())) < 2:
            break
        labels[members[halves == 1]] = max(sizes) + 1
    return labels


def cluster(vectors: np.ndarray, outlier_similarity: float = None) -> tuple[np.ndarray, np.ndarray]:
    """Topic index per page (-1 = unclustered) and topic centroids (unit rows),
    topics ordered by size (largest first)."""
    if outlier_similarity is None:
        outlier_similarity = MAP_OUTLIER_SIMILARITY
    n, d = vectors.shape
    reduced = _normalize_rows(_project(vectors, min(REDUCED_DIMS, n - 1, d)))

    _, labels = choose_k(reduced)
    labels = split_large(reduced, labels)

    def centroids_for(lbls):
        ids = sorted(set(lbls.tolist()) - {-1})
        return ids, np.array([_normalize(vectors[lbls == t].mean(axis=0)) for t in ids])

    ids, cents = centroids_for(labels)
    sims = np.einsum("ij,ij->i", vectors, cents[[ids.index(t) for t in labels]])
    labels = np.where(sims < outlier_similarity, -1, labels)

    # A topic must hang together: at least 2 pages whose mean pairwise
    # similarity reaches the outlier threshold squared (pairwise similarity in
    # a real topic is roughly the square of each page's similarity to the
    # centre: 0.14-0.39 on real data). A handful of unrelated pages, whose mean
    # is equally close to all of them, scores ~0 and is left unclustered.
    coherence = outlier_similarity ** 2
    for t in set(labels.tolist()) - {-1}:
        members = np.where(labels == t)[0]
        if len(members) < 2:
            labels[members] = -1
            continue
        pair = vectors[members] @ vectors[members].T
        mean_pair = (pair.sum() - np.trace(pair)) / (len(members) * (len(members) - 1))
        if mean_pair < coherence:
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
#
# Layout runs in "aspect space": x in [0, ASPECT], y in [0, 1], matching the
# canvas's 1400 x 900 world, so circles stay round. It is converted to the
# 0..1 box (x / ASPECT) at the end.

ASPECT = 1400 / 900
ELLIPSE_RATIO = 0.72          # ry = 0.72 * rx
COVERAGE = 0.30               # share of the box the ellipses cover in total
LABEL_HEIGHT = 0.045          # room above each ellipse for its label
LABEL_CHAR_WIDTH = 0.0082     # ~7.4 px per character at 13 px
LAYOUT_MARGIN = 0.03


def topic_radii(counts: Sequence[int], coverage: float = COVERAGE) -> np.ndarray:
    """(rx, ry) per topic in aspect space. Ellipse area is proportional to the
    page count, scaled so all ellipses together cover `coverage` of the box."""
    counts = np.asarray(counts, dtype=float)
    scale = math.sqrt(coverage * ASPECT / (math.pi * ELLIPSE_RATIO * max(counts.sum(), 1.0)))
    rx = scale * np.sqrt(counts)
    return np.stack([rx, rx * ELLIPSE_RATIO], axis=1)


def label_half_width(label: str, count: int) -> float:
    text = f"{label} · {count} page{'s' if count != 1 else ''}"
    return len(text) * LABEL_CHAR_WIDTH / 2


def footprints(radii: np.ndarray, half_labels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per topic: half width (ellipse or label, whichever is wider), extent
    above the centre (ellipse + label), extent below (ellipse)."""
    half_w = np.maximum(radii[:, 0], half_labels)
    return half_w, radii[:, 1] + LABEL_HEIGHT, radii[:, 1]


def spread(centres: np.ndarray, half_w: np.ndarray, up: np.ndarray, down: np.ndarray,
           iterations: int = 400, gap: float = 0.035, pull: float = 0.02) -> np.ndarray:
    """Balance topic positions: a pull toward the middle (stronger vertically, for
    the wide canvas) plus pairwise repulsion of the footprint boxes (ellipse and
    label), so labels never sit on another oval and no side is left empty."""
    pos = centres.astype(float).copy()
    k = len(pos)
    target = np.array([ASPECT / 2, 0.5])
    pull_xy = np.array([pull, pull * ASPECT])
    for _ in range(iterations):
        pos += (target - pos) * pull_xy
        moved = False
        for i in range(k):
            for j in range(i + 1, k):
                dx = pos[j, 0] - pos[i, 0]
                over_x = half_w[i] + half_w[j] + gap - abs(dx)
                top = max(pos[i, 1] - up[i], pos[j, 1] - up[j])
                bottom = min(pos[i, 1] + down[i], pos[j, 1] + down[j])
                over_y = bottom - top + gap
                if over_x <= 0 or over_y <= 0:
                    continue
                moved = True
                if over_x * 1.0 < over_y * ASPECT:
                    sign = 1.0 if dx > 0 or (dx == 0 and i < j) else -1.0
                    pos[i, 0] -= sign * over_x / 2
                    pos[j, 0] += sign * over_x / 2
                else:
                    dy = pos[j, 1] - pos[i, 1]
                    sign = 1.0 if dy > 0 or (dy == 0 and i < j) else -1.0
                    pos[i, 1] -= sign * over_y / 2
                    pos[j, 1] += sign * over_y / 2
        if not moved and _ > 40:
            break
    return pos


def pack_rows(start: np.ndarray, half_w: np.ndarray, up: np.ndarray, down: np.ndarray,
              gap: float = 0.05) -> np.ndarray:
    """Arrange topics in centred rows whose overall shape matches the canvas.

    Topics are split into horizontal bands by their PCA y and ordered by PCA x
    within a band, so related topics stay near each other. The number of rows
    is the one whose bounding box is closest to the canvas aspect ratio; each
    row is centred, so no side is left empty.
    """
    k = len(start)
    by_y = list(np.argsort(start[:, 1], kind="stable"))
    best = None
    for r in range(1, k + 1):
        rows = [sorted(map(int, band), key=lambda i: start[i, 0]) for band in np.array_split(by_y, r) if len(band)]
        widths = [sum(2 * half_w[i] for i in row) + gap * (len(row) - 1) for row in rows]
        heights = [max(up[i] for i in row) + max(down[i] for i in row) for row in rows]
        w, h = max(widths), sum(heights) + gap * (len(rows) - 1)
        score = abs(math.log((w / h) / ASPECT))
        if best is None or score < best[0] - 1e-9:
            best = (score, rows, widths, heights)
    _, rows, widths, heights = best
    pos = np.zeros((k, 2))
    total_h = sum(heights) + gap * (len(rows) - 1)
    y = 0.5 - total_h / 2
    for row, width, height in zip(rows, widths, heights):
        row_up = max(up[i] for i in row)
        x = ASPECT / 2 - width / 2
        for i in row:
            pos[i] = (x + half_w[i], y + row_up)
            x += 2 * half_w[i] + gap
        y += height + gap
    return pos


def fit_box(pos: np.ndarray, radii: np.ndarray, half_w: np.ndarray, up: np.ndarray, down: np.ndarray):
    """Uniformly scale and centre the topics (centres, radii, footprints) into
    the aspect box with a small margin."""
    lo = np.array([(pos[:, 0] - half_w).min(), (pos[:, 1] - up).min()])
    hi = np.array([(pos[:, 0] + half_w).max(), (pos[:, 1] + down).max()])
    span = np.maximum(hi - lo, 1e-9)
    avail = np.array([ASPECT - 2 * LAYOUT_MARGIN, 1 - 2 * LAYOUT_MARGIN])
    scale = min(avail[0] / span[0], avail[1] / span[1], 3.0)
    offset = np.array([LAYOUT_MARGIN, LAYOUT_MARGIN]) + (avail - span * scale) / 2
    return (pos - lo) * scale + offset, radii * scale


def layout(vectors: np.ndarray, topic_of: np.ndarray, centroids: np.ndarray, labels: Sequence[str] = ()):
    """Page positions (n, 2), topic centres (k, 2) and radii (k, 2) in the 0..1
    box (x scaled by ASPECT for the 1400 x 900 world)."""
    n = len(vectors)
    k = len(centroids)
    points = np.zeros((n, 2))
    if k == 0:
        return _scale_into(_pca_2d(vectors), 0.1, 0.9), np.zeros((0, 2)), np.zeros((0, 2))

    counts = [int((topic_of == t).sum()) for t in range(k)]
    radii = topic_radii(counts)
    labels = list(labels) + [""] * (k - len(labels))
    half_labels = np.array([label_half_width(labels[t] or "Topic", counts[t]) for t in range(k)])
    half_w, up, down = footprints(radii, half_labels)

    start = _pca_2d(centroids) if k > 1 else np.zeros((1, 2))
    start = np.stack([_scale_into(start[:, :1], 0.25 * ASPECT, 0.75 * ASPECT)[:, 0],
                      _scale_into(start[:, 1:], 0.25, 0.75)[:, 0]], axis=1)
    # Balanced rows first, then a few iterations of repulsion and centre pull
    # to loosen the grid while keeping labels clear of other ovals.
    centres = spread(pack_rows(start, half_w, up, down), half_w, up, down, iterations=30)
    scale_before = radii[:, 0].copy()
    centres, radii = fit_box(centres, radii, half_w, up, down)
    s = radii[0, 0] / scale_before[0] if scale_before[0] else 1.0
    half_w, up, down = half_w * s, up * s, down * s

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
        points[members] = centres[t] + local * radii[t] * 0.8

    # Unclustered pages sit between the two topics they are closest to.
    for i in np.where(topic_of == -1)[0]:
        sims = centroids @ vectors[i]
        order = np.argsort(-sims)
        jitter = (int(hashlib.md5(str(i).encode()).hexdigest()[:4], 16) / 0xFFFF - 0.5) * 0.08
        if k == 1:
            angle = 2 * math.pi * ((i * 0.618) % 1)
            points[i] = centres[0] + (radii[0] + 0.06) * np.array([math.cos(angle), math.sin(angle)])
        else:
            a, b = order[0], order[1]
            wa, wb = max(sims[a], 1e-3), max(sims[b], 1e-3)
            mid = (centres[a] * wa + centres[b] * wb) / (wa + wb)
            normal = np.array([-(centres[b] - centres[a])[1], (centres[b] - centres[a])[0]])
            points[i] = mid + _normalize(normal) * jitter
        points[i] = _outside_topics(points[i], centres, radii, half_w, up, down)

    to_box = np.array([1 / ASPECT, 1.0])
    points = np.clip(points * to_box, 0.01, 0.99)
    return points, centres * to_box, radii * to_box


def _inside(point: np.ndarray, centres: np.ndarray, radii: np.ndarray, half_w=None, up=None, down=None) -> bool:
    d = (point - centres) / radii
    if bool(((d ** 2).sum(axis=1) < 1.15 ** 2).any()):
        return True
    if half_w is None:
        return False
    # Also keep clear of each topic's label above its ellipse.
    in_label = ((np.abs(point[0] - centres[:, 0]) < half_w)
                & (point[1] > centres[:, 1] - up) & (point[1] < centres[:, 1] - radii[:, 1]))
    return bool(in_label.any())


def _outside_topics(point: np.ndarray, centres: np.ndarray, radii: np.ndarray,
                    half_w=None, up=None, down=None) -> np.ndarray:
    """Nudge an unclustered page out of every topic ellipse and label: try points
    on growing rings around it and keep the first one that is clear (and in the box)."""
    if not _inside(point, centres, radii, half_w, up, down):
        return point
    lo = np.array([0.02, 0.02])
    hi = np.array([ASPECT - 0.02, 0.98])
    for step in range(1, 40):
        r = 0.015 * step
        for a in range(16):
            angle = 2 * math.pi * a / 16
            candidate = point + r * np.array([math.cos(angle), math.sin(angle)])
            if (lo <= candidate).all() and (candidate <= hi).all() \
                    and not _inside(candidate, centres, radii, half_w, up, down):
                return candidate
    return point


# ---- edges ----------------------------------------------------------------------

MAX_TOPIC_LINKS = 2


def build_edges(vectors: np.ndarray, topic_of: np.ndarray, centroids: np.ndarray) -> list[tuple[int, int]]:
    """Each page links to its 2 nearest neighbours in its topic."""
    edges: set[tuple[int, int]] = set()
    for t in range(len(centroids)):
        idx = np.where(topic_of == t)[0]
        if len(idx) < 2:
            continue
        sims = vectors[idx] @ vectors[idx].T
        np.fill_diagonal(sims, -np.inf)
        for row, i in enumerate(idx):
            for col in np.argsort(-sims[row])[:INTRA_NEIGHBOURS]:
                j = idx[col]
                edges.add((min(i, j), max(i, j)))
    return sorted(edges)


def build_topic_links(centroids: np.ndarray, cross_similarity: float = None) -> list[tuple[int, int]]:
    """Pairs of related topics (centroid similarity above the threshold), the
    strongest first, with at most MAX_TOPIC_LINKS links per topic."""
    if cross_similarity is None:
        cross_similarity = MAP_CROSS_TOPIC_SIMILARITY
    k = len(centroids)
    if k < 2:
        return []
    sims = centroids @ centroids.T
    pairs = sorted(((sims[a, b], a, b) for a in range(k) for b in range(a + 1, k)
                    if sims[a, b] >= cross_similarity), reverse=True)
    degree = Counter()
    links = set()
    for _, a, b in pairs:  # strongest first; no topic gets more than MAX_TOPIC_LINKS
        if degree[a] < MAX_TOPIC_LINKS and degree[b] < MAX_TOPIC_LINKS:
            links.add((a, b))
            degree[a] += 1
            degree[b] += 1
    return sorted(links)


# ---- labels ----------------------------------------------------------------------

_WORD = re.compile(r"[a-z][a-z0-9]+")
_STOP = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "how", "its", "with",
    "from", "this", "that", "what", "when", "why", "who", "your", "about", "into", "over", "more",
    "most", "than", "then", "they", "them", "their", "there", "were", "was", "will", "would", "has",
    "have", "had", "our", "out", "use", "using", "used", "get", "via", "per", "one", "two", "three",
    "best", "guide", "introduction", "intro", "page", "pages", "home", "blog", "post", "article",
    "www", "com", "org", "net", "http", "https", "html", "wikipedia", "encyclopedia", "free", "wiki",
    "read", "online", "official", "site", "website", "news", "vs", "versus", "part", "chapter",
    "tutorial", "of", "in", "on", "to", "by", "an", "as", "at", "or", "is", "be", "it", "do", "we",
    "after", "during", "between", "within", "without", "among", "against", "through", "under", "while",
    "does", "may", "also", "both", "each", "other", "such", "these", "those", "which", "where",
}
# Words too broad to name a topic (they appear everywhere in a library).
GENERIC_WORDS = {
    "human", "humans", "patient", "patients", "study", "studies", "research", "result", "results",
    "effect", "effects", "role", "roles", "analysis", "analyses", "data", "method", "methods", "based",
    "associated", "association", "increase", "increased", "increases", "decrease", "decreased", "reduced",
    "reduces", "novel", "new", "evidence", "review", "approach", "cell", "cells", "level", "levels",
    "factor", "factors", "activity", "function", "functions", "response", "responses", "mechanism",
    "mechanisms", "potential", "specific", "induced", "dependent", "mediated", "high", "low", "early",
    "late", "case", "cases", "group", "groups", "year", "years", "type", "types", "model", "models",
    "system", "systems", "process", "processes", "role", "impact", "risk", "use", "related", "general",
    "important", "different", "large", "small", "first", "show", "shows", "find", "found", "things",
    "people", "way", "ways", "work", "works", "thing", "topic", "topics", "information", "overview",
    # Filler common in web page titles
    "getting", "started", "explained", "notes", "learned", "practical", "common", "mistakes", "simply",
    "matters", "tips", "tricks", "basics", "beginners", "complete", "ultimate", "everything", "know",
    "lessons", "things", "really", "actually", "quick", "simple", "easy", "deep", "dive",
}
ACRONYMS = {"dna", "rna", "mrna", "hiv", "covid", "ai", "api", "css", "html", "sql", "gpu", "cpu", "ml",
            "nlp", "ui", "ux", "ibm", "tnf", "il", "cd4", "cd8", "t2d", "bmi", "ptsd", "adhd", "ssd", "llm"}


def _title_case(words: Sequence[str]) -> str:
    return " ".join(w.upper() if w in ACRONYMS else w[:1].upper() + w[1:] for w in words)


def _terms(text: str) -> tuple[list[str], list[str]]:
    """Unigrams and adjacent-word bigrams that aren't stopwords or generic."""
    words = _WORD.findall((text or "").lower())
    keep = [w if (w not in _STOP and w not in GENERIC_WORDS and len(w) > 2) else None for w in words]
    unigrams = [w for w in keep if w]
    bigrams = [f"{a} {b}" for a, b in zip(keep, keep[1:]) if a and b and a[:4] != b[:4]]
    return unigrams, bigrams


def ctfidf_labels(groups: list[list[dict]]) -> list[str]:
    """Distinct Title Case labels per topic from titles (weighted 2x) and
    descriptions, using class-based TF-IDF over unigrams and bigrams:
    tf(t, c) * log(1 + A / f(t)). A frequent bigram ("Gene Expression") wins;
    otherwise the two best unigrams ("Tumor Immunity")."""
    uni, bi = [], []
    for pages in groups:
        cu, cb = Counter(), Counter()
        for p in pages:
            for weight, text in ((2, p.get("title", "")), (1, p.get("description", ""))):
                u, b = _terms(text)
                for _ in range(weight):
                    cu.update(u)
                    cb.update(b)
        uni.append(cu)
        bi.append(cb)

    def scored(counts):
        total = Counter()
        for c in counts:
            total.update(c)
        avg = (sum(sum(c.values()) for c in counts) / max(len(counts), 1)) or 1.0
        out = []
        for c in counts:
            size = sum(c.values()) or 1
            out.append(sorted((((c[t] / size) * math.log(1 + avg / total[t]), t) for t in c), reverse=True))
        return out

    uni_scores, bi_scores = scored(uni), scored(bi)
    used: set[str] = set()
    labels = []
    for i in range(len(groups)):
        candidates = []
        best_uni = uni_scores[i][0][0] if uni_scores[i] else 0.0
        for score, term in bi_scores[i][:5]:
            if bi[i][term] >= 2 * 2 and score >= 0.5 * best_uni:  # in 2+ titles (titles count twice)
                candidates.append(_title_case(term.split()))
        top = [t for _, t in uni_scores[i][:6]]
        for a_i, a in enumerate(top):
            for b in top[a_i + 1:]:
                if a[:4] != b[:4]:
                    candidates.append(_title_case([a, b]))
        candidates += [_title_case([t]) for t in top]
        label = next((c for c in candidates if c.lower() not in used), None) or f"Topic {i + 1}"
        used.add(label.lower())
        labels.append(label)
    return labels


def acceptable_label(label: str | None, taken: set[str]) -> bool:
    """A model label is used only if it is 1-3 words, not generic, and distinct."""
    if not label:
        return False
    words = label.lower().split()
    if not 1 <= len(words) <= 3 or label.lower() in taken:
        return False
    return not any(w in GENERIC_WORDS for w in words)


def label_topics(groups: list[list[dict]], labeler: Labeler | None,
                 label_cache: "OrderedDict[str, str] | None" = None) -> list[str]:
    """Final label per topic: cached, else from the labeller (Gemini), else the
    keyword fallback. Logs at WARNING whenever the fallback is used and why."""
    k = len(groups)
    fallback = ctfidf_labels(groups)
    cache_keys = [hashlib.sha1("|".join(sorted(p["page_id"] for p in g)).encode()).hexdigest() for g in groups]
    labels = [label_cache.get(ck) if label_cache is not None else None for ck in cache_keys]
    missing = [t for t in range(k) if not labels[t]]
    if missing:
        fresh: list = []
        if labeler is None:
            logger.warning(f"Topic labels: Gemini is not configured or unavailable; "
                           f"using keyword labels for {len(missing)} topic(s)")
        else:
            titles = [[p.get("title") or "" for p in groups[t][:10]] for t in missing]
            hints = [fallback[t] for t in missing]
            others = [labels[t] for t in range(k) if labels[t]]
            try:
                fresh = labeler(titles, hints=hints, taken=others) or []
                if not fresh:
                    logger.warning("Topic labels: Gemini returned no labels; using keyword labels")
            except Exception as e:  # labels must never break the map
                logger.warning(f"Topic labels: Gemini call failed ({type(e).__name__}: {e}); using keyword labels")
                fresh = []
        taken = {l.lower() for l in labels if l}
        for t, label in zip(missing, list(fresh) + [None] * (len(missing) - len(fresh))):
            if acceptable_label(label, taken):
                labels[t] = label
                taken.add(label.lower())
                if label_cache is not None:
                    label_cache[cache_keys[t]] = label
                    while len(label_cache) > 500:
                        label_cache.popitem(last=False)
            elif label:
                logger.warning(f"Topic labels: rejected Gemini label {label!r} (generic, too long or "
                               f"duplicate); using {fallback[t]!r}")
        taken = {l.lower() for l in labels if l}
        for t in range(k):
            if not labels[t]:
                choice = fallback[t] if fallback[t].lower() not in taken else f"{fallback[t]} {t + 1}"
                labels[t] = choice
                taken.add(choice.lower())
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
    k = len(centroids)
    groups = [[pages[i] for i in np.where(topic_of == t)[0]] for t in range(k)]
    model_labels = label_topics(groups, labeler, label_cache)
    points, centres, radii = layout(vectors, topic_of, centroids, model_labels)
    edges = build_edges(vectors, topic_of, centroids)
    topic_links = build_topic_links(centroids)

    topic_ids = [f"{key}-{t}" for t in range(k)]
    topics = [
        {
            "id": topic_ids[t],
            "label": model_labels[t],
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
    out_edges = [{"a": pages[a]["page_id"], "b": pages[b]["page_id"], "kind": "intra"} for a, b in edges]
    out_links = [{"a": topic_ids[a], "b": topic_ids[b]} for a, b in topic_links]
    counts.update(topics=k, unclustered=int((topic_of == -1).sum()))
    response = {"status": "ok", "version": key, "topics": topics, "pages": out_pages,
                "edges": out_edges, "topic_links": out_links, "counts": counts}
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
