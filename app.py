"""Demo chat server + embeddable website widget.

Usage:
    set DOCS_RAG_INDEX=indexes/example.json
    py -m uvicorn app:app --port 8000

Embed on any site:
    <script src="https://YOUR-HOST/widget.js" data-title="Ask the docs" async></script>
"""

import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from rag import Index, answer

STATIC = Path(__file__).parent / "static"
INDEX = Index(os.environ.get("DOCS_RAG_INDEX", "indexes/index.json"))
PRODUCT = os.environ.get("DOCS_RAG_PRODUCT", INDEX.root)
# Comma-separated sites allowed to call /ask from the widget, e.g. "https://docs.example.com". "*" allows any.
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("DOCS_RAG_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
# Questions per visitor IP per minute; every question costs LLM tokens.
RATE_LIMIT = int(os.environ.get("DOCS_RAG_RATE_LIMIT", "10"))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["POST"], allow_headers=["Content-Type"])
recent = defaultdict(deque)


class Ask(BaseModel):
    question: str


@app.post("/ask")
def ask(body: Ask, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if len(recent) > 10000:  # keep memory bounded on busy sites
        recent.clear()
    now, hits = time.monotonic(), recent[ip]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        raise HTTPException(429, "Too many questions. Please wait a minute.")
    hits.append(now)
    return answer(INDEX, body.question[:2000])


@app.get("/", response_class=HTMLResponse)
def home():
    html = (STATIC / "chat.html").read_text(encoding="utf-8")
    return html.replace("{{PRODUCT}}", PRODUCT)


@app.get("/widget.js")
def widget():
    return FileResponse(STATIC / "widget.js", media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})


@app.get("/widget-demo", response_class=HTMLResponse)
def widget_demo():
    return (STATIC / "widget-demo.html").read_text(encoding="utf-8")
