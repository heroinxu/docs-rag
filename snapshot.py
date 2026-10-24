"""Run real questions through the engine and save a static chat page with the answers.

Used for gig images and for demo screenshots in Fiverr Brief replies.

Usage:
    py snapshot.py indexes/uv.json "uv (Astral)" out.html "How do I use uv in GitHub Actions?" ["Second question" ...]
"""

import html
import re
import sys
from pathlib import Path

from rag import Index, answer, make_client


def render(question, res):
    parts = [f'<div class="msg user">{html.escape(question)}</div>', '<div class="msg bot">', html.escape(res["answer"])]
    if res["citations"]:
        parts.append('<div class="cites">')
        for n, c in enumerate(res["citations"], 1):
            quote = c["quote"][:90] + ("..." if len(c["quote"]) > 90 else "")
            parts.append(f'<a href="{html.escape(c["url"])}">[{n}] {html.escape(c["heading"])}: "{html.escape(quote)}"</a>')
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)  # .msg uses white-space: pre-wrap, so no newlines between tags


def main():
    index_path, product, out, *questions = sys.argv[1:]
    index, client = Index(index_path), make_client()
    page =(Path(__file__).parent / "static" / "chat.html").read_text(encoding="utf-8")
    log = []
    for q in questions:
        res = answer(index, q, client)
        print(f"{q}\n  -> {len(res['citations'])} verified citations, {res['unsupported']} unverified sentences")
        log.append(render(q, res))
    page = page.replace("{{PRODUCT}}", html.escape(product))
    page = page.replace('<div id="log"></div>', '<div id="log">' + "\n".join(log) + "</div>")
    page = re.sub(r"<script>.*?</script>", "", page, flags=re.S)
    Path(out).write_text(page, encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
