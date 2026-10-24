"""Production entry point: build the docs index if needed, then start the server.

Environment:
    DOCS_RAG_DOCS_URL    public docs root to index, e.g. https://docs.example.com/
    DOCS_RAG_MAX_PAGES   page limit for indexing (default 150)
    DOCS_RAG_INDEX       index file path (default indexes/index.json)
    DOCS_RAG_REINDEX     "1" to rebuild the index even if it exists
    PORT                 port to listen on (set by Render/Railway; default 8000)

Usage:
    py serve.py --index-only   # build step: crawl and index, then exit
    py serve.py                # start step: index if missing, then serve
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
INDEX = Path(os.environ.setdefault("DOCS_RAG_INDEX", str(HERE / "indexes" / "index.json")))


def build_index():
    url = os.environ.get("DOCS_RAG_DOCS_URL")
    if INDEX.exists() and os.environ.get("DOCS_RAG_REINDEX") != "1":
        print(f"Index exists: {INDEX}")
        return
    if not url:
        sys.exit("DOCS_RAG_DOCS_URL is not set and no index exists. Set it to the client's public docs URL.")
    pages = os.environ.get("DOCS_RAG_MAX_PAGES", "150")
    subprocess.run([sys.executable, str(HERE / "ingest.py"), url, "--max-pages", pages, "--out", str(INDEX)], check=True)


def main():
    build_index()
    if "--index-only" in sys.argv:
        return
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), app_dir=str(HERE))


if __name__ == "__main__":
    main()
