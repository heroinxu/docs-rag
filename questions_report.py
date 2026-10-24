"""Top-questions report from the question log.

Groups near-duplicate questions ("how do I get an API key", "How to get API key?"), then lists:
the most asked questions, unanswered questions (documentation gaps), the most cited doc pages,
and volume by source and by day.

Usage:
    py questions_report.py                       # logs/questions.jsonl -> questions-report.md
    py questions_report.py --days 30 --out march.md
"""

import argparse
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qlog import PATH, read_log

STOP = set("a an the to do does did i we you it is are was be how what why when where which can could should "
           "would my our your of in on for with and or from by at as this that there any please hi hello thanks".split())
WORD = re.compile(r"[a-z0-9_]+")


def key_terms(question):
    return frozenset(w for w in WORD.findall(question.lower()) if w not in STOP and len(w) > 1)


def group(entries, threshold=0.6):
    """Greedy clustering by word-set overlap (Jaccard). Good enough for support questions."""
    groups = []  # each: {"terms", "items"}
    for e in entries:
        terms = key_terms(e["question"])
        best, best_score = None, 0.0
        for g in groups:
            union = terms | g["terms"]
            score = len(terms & g["terms"]) / len(union) if union else 1.0
            if score > best_score:
                best, best_score = g, score
        if best is not None and best_score >= threshold:
            best["items"].append(e)
        else:
            groups.append({"terms": terms, "items": [e]})
    for g in groups:
        g["label"] = Counter(i["question"].strip() for i in g["items"]).most_common(1)[0][0]
        g["answered"] = sum(i["answered"] for i in g["items"])
    return sorted(groups, key=lambda g: len(g["items"]), reverse=True)


def build_report(entries, days=None, top=20):
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        entries = [e for e in entries if datetime.fromisoformat(e["ts"]) >= cutoff]
    period = f"last {days} days" if days else "all time"
    if not entries:
        return f"# Top questions report ({period})\n\nNo questions logged yet.\n"

    total = len(entries)
    answered = sum(e["answered"] for e in entries)
    groups = group(entries)
    gaps = [g for g in groups if g["answered"] < len(g["items"])]
    pages = Counter(p for e in entries for p in e.get("pages", []))
    sources = Counter(e["source"] for e in entries)
    by_day = Counter(e["ts"][:10] for e in entries)

    out = [
        f"# Top questions report ({period})",
        "",
        f"- Questions: **{total}** ({len(groups)} distinct topics)",
        f"- Answered from the docs: **{answered}** ({100 * answered / total:.0f}%)",
        f"- Not answered: **{total - answered}**. These point to gaps in the documentation",
        f"- By channel: " + ", ".join(f"{s} {n}" for s, n in sources.most_common()),
        f"- First / last question: {min(e['ts'] for e in entries)[:16]} / {max(e['ts'] for e in entries)[:16]} UTC",
        "",
        "## Most asked",
        "",
        "| # | Question (most common wording) | Times asked | Answered |",
        "|---|---|---|---|",
    ]
    for n, g in enumerate(groups[:top], 1):
        out.append(f"| {n} | {g['label'][:120]} | {len(g['items'])} | {g['answered']}/{len(g['items'])} |")

    out += ["", "## Not answered (documentation gaps)", ""]
    if gaps:
        out += ["Users asked these, and the docs had no answer. Consider adding a page or section for each.", "",
                "| Question | Times asked |", "|---|---|"]
        gaps.sort(key=lambda g: len(g["items"]) - g["answered"], reverse=True)
        for g in gaps[:top]:
            out.append(f"| {g['label'][:120]} | {len(g['items']) - g['answered']} |")
    else:
        out.append("None. Every question was answered from the docs.")

    out += ["", "## Most cited doc pages", "", "| Page | Times cited |", "|---|---|"]
    for url, n in pages.most_common(top):
        out.append(f"| {url} | {n} |")

    out += ["", "## Questions per day", "", "| Day | Questions |", "|---|---|"]
    for day in sorted(by_day):
        out.append(f"| {day} | {by_day[day]} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=PATH)
    ap.add_argument("--days", type=int)
    ap.add_argument("--out", default="questions-report.md")
    args = ap.parse_args()
    report = build_report(read_log(args.log), args.days)
    Path(args.out).write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
