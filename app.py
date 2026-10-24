"""Demo chat server.

Usage:
    set DOCS_RAG_INDEX=indexes/example.json
    py -m uvicorn app:app --port 8000
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from rag import Index, answer

INDEX = Index(os.environ.get("DOCS_RAG_INDEX", "indexes/index.json"))
PRODUCT = os.environ.get("DOCS_RAG_PRODUCT", INDEX.root)

app = FastAPI()


class Ask(BaseModel):
    question: str


@app.post("/ask")
def ask(body: Ask):
    return answer(INDEX, body.question[:2000])


@app.get("/", response_class=HTMLResponse)
def home():
    html = (Path(__file__).parent / "static" / "chat.html").read_text(encoding="utf-8")
    return html.replace("{{PRODUCT}}", PRODUCT)
