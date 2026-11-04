"""Compare two evaluation reports (before and after a search change).

Standard library only, so it runs anywhere, including the server's own Python:
    python3 evaluation/compare.py evaluation/personal_baseline.json evaluation/personal_report.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KS = [1, 3, 5, 10]


def _rank(rank):
    return f"#{rank}" if rank else "-"


def compare(before: dict, after: dict) -> list[str]:
    lines = [f"{'':16}{'n':>4}" + "".join(f"{'R@' + str(k):>14}" for k in KS) + f"{'MRR':>16}"]
    names = ["all"] + sorted(set(before.get("by_category", {})) | set(after.get("by_category", {})))
    for name in names:
        b = before["metrics"] if name == "all" else before.get("by_category", {}).get(name)
        a = after["metrics"] if name == "all" else after.get("by_category", {}).get(name)
        if not a:
            continue
        cells = []
        for key, width, fmt in [(f"recall@{k}", 14, ".2f") for k in KS] + [("mrr", 16, ".3f")]:
            delta = a[key] - b[key] if b else 0.0
            sign = f"{delta:+{fmt}}" if b and abs(delta) > 1e-9 else ""
            cells.append(f"{format(a[key], fmt) + (' ' + sign if sign else ''):>{width}}")
        lines.append(f"{name:16}{a['n_queries']:>4}" + "".join(cells))

    old = {r["id"]: r for r in before.get("details", [])}
    changed = []
    for r in after.get("details", []):
        prev = old.get(r["id"])
        if prev is None or prev.get("query") != r.get("query"):
            continue
        if prev.get("rank") != r.get("rank"):
            better = (r["rank"] or 99) < (prev["rank"] or 99)
            changed.append((not better, r["id"], prev.get("rank"), r.get("rank"), r["query"]))
    if changed:
        lines.append("")
        lines.append("Rank changes (first relevant result):")
        for worse, qid, was, now, query in sorted(changed):
            mark = "worse " if worse else "better"
            lines.append(f"  {mark} {qid:>6}  {_rank(was):>4} -> {_rank(now):<4} {query}")
    return lines


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    before, after = (json.loads(Path(p).read_text(encoding="utf-8")) for p in argv)
    print("\n".join(compare(before, after)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
