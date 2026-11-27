"""What the server makes of some saved pages, for ingest_check.mjs to compare.

For each <name>.html (with <name>.url) in a folder, runs backend.ingest.ingest_page
as POST /memory does, with a stand-in Solr client and embedder that record the
chunk documents and the texts to embed, and writes the cases (inputs and
outputs) to a JSON file. The extension's local saving must produce the same.

Usage (from code/src): python -m evaluation.parity.ingest_reference <pages dir> <out.json>
"""
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.ingest import IngestError, ingest_page

USER = "parity-user"
TIMESTAMP = "2026-10-01T00:00:00.000Z"


def visible_text(html: str) -> str:
    """A rough innerText, the fallback the extension sends with the HTML."""
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", html)
    return re.sub(r"\n\s*\n+", "\n\n", text)


def case(html: str, url: str, manual: bool) -> dict:
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    request = {
        "user_id": USER, "url": url, "title": (title_match.group(1).strip() if title_match else ""),
        "content": visible_text(html), "html": html, "canonical_url": None,
        "is_manual": manual, "timestamp": TIMESTAMP,
    }
    solr = MagicMock()
    solr.get_page_head.return_value = None
    captured = []

    def embed(texts):
        captured.extend(texts)
        return [[0.0] * 384 for _ in texts]

    with patch("backend.ingest.embed_passages", side_effect=embed):
        try:
            result = ingest_page(USER, url, request["title"], request["content"], html=html,
                                 is_manual=manual, solr=solr, keep_existing=not manual,
                                 timestamp=TIMESTAMP)
            docs = [{k: v for k, v in d.items() if k not in ("embedding", "page_embedding")}
                    for d in solr.upsert_page_chunks.call_args.args[1]]
            expected = {"result": result.__dict__, "docs": docs, "embed_texts": captured}
        except IngestError as e:
            expected = {"error": {"status": e.status_code, "detail": e.detail}}
    return {"request": request, "expected": expected}


def main():
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    cases = []
    for html_file in sorted(folder.glob("*.html")):
        url = html_file.with_suffix(".url").read_text().strip()
        html = html_file.read_text(encoding="utf-8", errors="replace")
        cases.append(case(html, url, manual=True))
    out.write_text(json.dumps(cases), encoding="utf-8")
    print(f"{len(cases)} pages: " + ", ".join(
        f"{len(c['expected'].get('docs', []))} chunks" if "docs" in c["expected"] else c["expected"]["error"]["detail"]
        for c in cases))


if __name__ == "__main__":
    main()
