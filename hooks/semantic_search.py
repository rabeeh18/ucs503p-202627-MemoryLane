"""MkDocs hook: build the files for semantic (meaning-based) docs search.

After the site is built, this embeds every section of the docs with a small
*static* embedding model (Model2Vec's potion-base-8M, distilled from
bge-base-en-v1.5) and writes, under site/assets/semantic/:

    manifest.json      file names (content-hashed, so browsers re-fetch only on change)
    vocab-<hash>.txt   the tokenizer's word pieces, one per line, in id order
    table-<hash>.bin   one 256-number vector per word piece, as int8
    scales-<hash>.bin  one float32 scale per word piece (int8 * scale = the vector)
    sections-<hash>.json  every docs section: where it is, its titles, a snippet,
                       and its vector (int8, base64) with its scale

The browser (docs/assets/javascripts/semantic-*.js) tokenises a query the same
way, averages its word pieces' vectors, and compares it with every section:
no neural network runs, so a search takes a few milliseconds. Sections are
embedded from the *same* int8 table, so documents and queries match exactly.

Needs `model2vec` at build time (the model is downloaded from Hugging Face once).
"""
import base64
import hashlib
import html
import json
import logging
import os
import re

log = logging.getLogger("mkdocs.hooks.semantic_search")

MODEL = "minishlab/potion-base-8M"
MAX_TOKENS = 512           # the model's max_length: longer sections are cut
SNIPPET_CHARS = 180
OUT_DIR = os.path.join("assets", "semantic")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _plain(text: str) -> str:
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _quantise_rows(matrix):
    """int8 rows and one float32 scale per row (int8 * scale ~= the row)."""
    import numpy as np
    scales = np.abs(matrix).max(axis=1) / 127.0
    scales[scales == 0] = 1.0
    q = np.clip(np.round(matrix / scales[:, None]), -127, 127).astype(np.int8)
    return q, scales.astype(np.float32)


def _write(site_dir: str, stem: str, ext: str, data: bytes) -> str:
    name = f"{stem}-{hashlib.sha256(data).hexdigest()[:12]}.{ext}"
    with open(os.path.join(site_dir, OUT_DIR, name), "wb") as f:
        f.write(data)
    return name


def _sections(site_dir: str) -> list[dict]:
    with open(os.path.join(site_dir, "search", "search_index.json"), encoding="utf-8") as f:
        docs = json.load(f)["docs"]
    page_titles = {d["location"]: _plain(d.get("title", "")) for d in docs if "#" not in d["location"]}
    sections = []
    for d in docs:
        location = d["location"]
        title = _plain(d.get("title", ""))
        text = _plain(d.get("text", ""))
        if not (title or text):
            continue
        page = page_titles.get(location.split("#", 1)[0], "")
        sections.append({
            "location": location,
            "title": title,
            "page": page if page != title else "",
            "snippet": text[:SNIPPET_CHARS] + ("…" if len(text) > SNIPPET_CHARS else ""),
            "_text": f"{page}. {title}. {text}" if page and page != title else f"{title}. {text}",
        })
    return sections


def on_post_build(config, **kwargs):
    try:
        import numpy as np
        from model2vec import StaticModel
    except ImportError:
        log.warning("model2vec isn't installed, so the docs have no meaning-based search. "
                    "pip install model2vec")
        return

    site_dir = config["site_dir"]
    os.makedirs(os.path.join(site_dir, OUT_DIR), exist_ok=True)

    model = StaticModel.from_pretrained(MODEL)
    tokenizer = model.tokenizer
    vocab = json.loads(tokenizer.to_str())["model"]["vocab"]
    id_to_token = [None] * len(vocab)
    for token, i in vocab.items():
        id_to_token[i] = token
    unk = vocab.get("[UNK]")

    table, scales = _quantise_rows(np.asarray(model.embedding, dtype=np.float32))
    dequantised = table.astype(np.float32) * scales[:, None]

    def embed(text: str):
        ids = [i for i in tokenizer.encode(text, add_special_tokens=False).ids if i != unk][:MAX_TOKENS]
        if not ids:
            return None
        v = dequantised[ids].mean(axis=0)
        norm = np.linalg.norm(v)
        return v / norm if norm else None

    sections = []
    for s in _sections(site_dir):
        v = embed(s.pop("_text"))
        if v is None:
            continue
        q, scale = _quantise_rows(v[None, :])
        s["scale"] = float(scale[0])
        s["vector"] = base64.b64encode(q[0].tobytes()).decode("ascii")
        sections.append(s)

    manifest = {
        "model": MODEL,
        "dims": int(table.shape[1]),
        "normalize": True,
        "max_tokens": MAX_TOKENS,
        "vocab": _write(site_dir, "vocab", "txt", "\n".join(id_to_token).encode("utf-8")),
        "table": _write(site_dir, "table", "bin", table.tobytes()),
        "scales": _write(site_dir, "scales", "bin", scales.tobytes()),
        "sections": _write(site_dir, "sections", "json",
                           json.dumps(sections, ensure_ascii=False, separators=(",", ":")).encode("utf-8")),
    }
    with open(os.path.join(site_dir, OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f)
    log.info(f"Semantic search: {len(sections)} sections, {len(id_to_token)} word pieces")
