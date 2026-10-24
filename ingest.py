"""Crawl a public docs site and save heading-level chunks to an index file.

Usage:
    py ingest.py https://docs.example.com --max-pages 150 --out indexes/example.json
"""

import argparse
import json
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

USER_AGENT = "docs-rag-demo/0.1 (+contact via Fiverr)"
SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|pdf|zip|gz|css|js|ico|woff2?|mp4)$", re.I)
CHUNK_CHARS = 2400


def fetch(session, url):
    try:
        r = session.get(url, timeout=20)
    except requests.RequestException:
        return None
    if r.status_code != 200 or "html" not in r.headers.get("content-type", "") and "xml" not in r.headers.get("content-type", ""):
        return None
    return r.text


def sitemap_urls(session, root):
    """Return page URLs from /sitemap.xml (follows one level of sitemap index)."""
    found = []
    queue = [urljoin(root, "/sitemap.xml")]
    seen = set()
    while queue:
        sm = queue.pop()
        if sm in seen:
            continue
        seen.add(sm)
        text = fetch(session, sm)
        if not text:
            continue
        try:
            tree = ElementTree.fromstring(text.encode())
        except ElementTree.ParseError:
            continue
        for loc in tree.iter():
            if loc.tag.endswith("loc") and loc.text:
                u = loc.text.strip()
                (queue if u.endswith(".xml") else found).append(u)
    return found


def in_scope(url, root):
    p, r = urlparse(url), urlparse(root)
    return p.netloc == r.netloc and p.path.startswith(r.path.rstrip("/")) and not SKIP_EXT.search(p.path)


def extract(html):
    """Return (title, [(heading, text), ...]) from the main content of a docs page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "form"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"}) or soup.body
    if main is None:
        return title, []

    sections, heading, buf = [], title, []
    for el in main.find_all(["h1", "h2", "h3", "p", "li", "pre", "td", "dt", "dd"]):
        if el.name in ("h1", "h2", "h3"):
            if buf:
                sections.append((heading, "\n".join(buf)))
            heading, buf = el.get_text(" ", strip=True), []
        elif not el.find_parent(["li", "td", "dd"]) or el.name == "pre":
            # pre: keep the code's own whitespace; syntax highlighting splits it into many spans
            text = el.get_text().strip() if el.name == "pre" else el.get_text(" ", strip=True)
            if text:
                buf.append(text)
    if buf:
        sections.append((heading, "\n".join(buf)))
    return title, sections


def chunk(sections):
    """Merge small sections and split big ones so each chunk is <= CHUNK_CHARS."""
    out = []
    for heading, text in sections:
        while len(text) > CHUNK_CHARS:
            cut = text.rfind("\n", 0, CHUNK_CHARS)
            cut = cut if cut > CHUNK_CHARS // 2 else CHUNK_CHARS
            out.append((heading, text[:cut]))
            text = text[cut:].lstrip()
        if text:
            if out and out[-1][0] == heading and len(out[-1][1]) + len(text) < CHUNK_CHARS:
                out[-1] = (heading, out[-1][1] + "\n" + text)
            else:
                out.append((heading, text))
    return out


def links(html, base, root):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        u = urldefrag(urljoin(base, a["href"]))[0]
        if in_scope(u, root):
            yield u


def crawl(root, max_pages, delay):
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    seeds = [u for u in sitemap_urls(session, root) if in_scope(u, root)]
    queue, seen, pages = deque(seeds or [root]), set(), []
    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        html = fetch(session, url)
        if not html:
            continue
        title, sections = extract(html)
        if sections:
            pages.append({"url": url, "title": title, "sections": chunk(sections)})
            print(f"[{len(pages)}/{max_pages}] {url}")
        if not seeds:
            queue.extend(u for u in links(html, url, root) if u not in seen)
        time.sleep(delay)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="docs root URL, e.g. https://docs.example.com/")
    ap.add_argument("--max-pages", type=int, default=150)
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--out", default="indexes/index.json")
    args = ap.parse_args()

    pages = crawl(args.root, args.max_pages, args.delay)
    pairs = [(p, s) for p in pages for s in p["sections"]]
    chunks = [
        {"id": i, "url": p["url"], "title": p["title"], "heading": h, "text": t}
        for i, (p, (h, t)) in enumerate(pairs)
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"root": args.root, "chunks": chunks}, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(chunks)} chunks from {len(pages)} pages to {out}")


if __name__ == "__main__":
    main()
