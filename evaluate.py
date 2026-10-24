"""Run a question set against an index and write a Markdown accuracy report.

questions file: one JSON object per line:
    {"q": "How do I rotate an API key?", "answerable": true}
    {"q": "What is your CEO's phone number?", "answerable": false}

Usage:
    py evaluate.py indexes/example.json questions.jsonl --out report.md
"""

import argparse
import json
from pathlib import Path

from rag import MODELS, Index, answer, make_client


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("index")
    ap.add_argument("questions")
    ap.add_argument("--out", default="report.md")
    args = ap.parse_args()

    index, client = Index(args.index), make_client()
    rows = [json.loads(l) for l in Path(args.questions).read_text(encoding="utf-8").splitlines() if l.strip()]
    results = []
    for i, row in enumerate(rows, 1):
        try:
            res = answer(index, row["q"], client)
        except Exception as e:
            res = {"answer": f"ERROR: {type(e).__name__}: {str(e)[:200]}", "citations": [], "refused": False, "unsupported": 1}
        answerable = row.get("answerable", True)
        if answerable:
            ok = not res["refused"] and bool(res["citations"]) and res["unsupported"] == 0
        else:
            ok = res["refused"]
        results.append((row, res, ok))
        print(f"[{i}/{len(rows)}] {'PASS' if ok else 'CHECK'} {row['q']}")

    ans = [r for r in results if r[0].get("answerable", True)]
    neg = [r for r in results if not r[0].get("answerable", True)]
    pct = lambda xs: f"{100 * sum(r[2] for r in xs) / len(xs):.0f}%" if xs else "n/a"

    lines = [
        f"# Accuracy report: {index.root}",
        "",
        f"- Models (primary, then fallbacks): `{', '.join(MODELS)}`",
        f"- Questions: {len(results)} ({len(ans)} answerable, {len(neg)} out-of-scope)",
        f"- Answerable questions fully supported by verified quotes: **{pct(ans)}**",
        f"- Out-of-scope questions correctly declined: **{pct(neg)}**",
        "",
        "Automatic checks only: PASS means every sentence had a quote found verbatim in the cited doc chunk (or the question was correctly declined). "
        "A human still reviews each answer for correctness.",
        "",
    ]
    for row, res, ok in results:
        lines += [f"## {'PASS' if ok else 'CHECK'}: {row['q']}", "", res["answer"], ""]
        for n, c in enumerate(res["citations"], 1):
            lines.append(f"{n}. [{c['heading']}]({c['url']}): \"{c['quote'][:160]}\"")
        lines.append("")
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
