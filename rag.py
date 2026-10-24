"""Retrieval (BM25) + grounded answering with Gemini and verified quote citations.

Gemini has no API-enforced citations, so the model must return, for every
sentence, the chunk number it used plus a verbatim quote. Each quote is checked
against the chunk text; citations that don't match are dropped and the sentence
is flagged as unsupported.
"""

import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

# Comma-separated; later models are fallbacks when earlier ones are overloaded.
MODELS = [m.strip() for m in os.environ.get("DOCS_RAG_MODEL", "gemini-3.8-flash,gemini-3.5-flash,gemini-flash-latest,gemini-3.5-flash-lite").split(",") if m.strip()]
MODEL = MODELS[0]
RETRYABLE = {429, 500, 503, 504}
SKIP_MODEL = {404}  # model retired for this key: move on to the next one
TOP_K = int(os.environ.get("DOCS_RAG_TOP_K", "8"))
NOT_FOUND = "I couldn't find this in the docs."

SYSTEM = f"""You are a documentation assistant for a software product.
Answer ONLY from the numbered documentation chunks in the user message.
For every sentence of your answer, list the chunk number(s) that support it and copy a short verbatim quote (5-25 words, exact characters) from that chunk.
If the chunks do not contain the answer, set found=false and answer exactly: "{NOT_FOUND}"
Do not use outside knowledge. Do not guess API names, parameters, limits or prices.
Be concise and technical. For how-to questions, give the concrete steps and exact commands from the docs.
Answer in the language the user writes in; quotes stay in the docs' language."""


class Citation(BaseModel):
    chunk: int
    quote: str


class Sentence(BaseModel):
    text: str
    citations: list[Citation]


class Answer(BaseModel):
    found: bool
    sentences: list[Sentence]


TOKEN = re.compile(r"[a-z0-9_]+")
SPACE = re.compile(r"\s+")


def tokenize(text):
    return TOKEN.findall(text.lower())


def normalize(text):
    return SPACE.sub(" ", text).strip().lower()


class Index:
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.root = data["root"]
        self.chunks = data["chunks"]
        self.docs = [tokenize(f'{c["title"]} {c["heading"]} {c["heading"]} {c["text"]}') for c in self.chunks]
        self.avgdl = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def search(self, query, k=TOP_K, k1=1.5, b=0.75):
        q = tokenize(query)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = sum(
                self.idf.get(t, 0) * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / self.avgdl))
                for t in q if t in tf
            )
            if s > 0:
                scores.append((s, i))
        scores.sort(reverse=True)
        picked = [i for _, i in scores[:k]]
        # Pull more sections from the pages of the top 2 hits: how-to steps often sit
        # several sections below the intro that matches the query best.
        rank = {i: r for r, (_, i) in enumerate(scores)}
        top_pages = {self.chunks[i]["url"] for i in picked[:2]}
        extra = sorted(
            (j for j, c in enumerate(self.chunks) if c["url"] in top_pages and j not in picked),
            key=lambda j: rank.get(j, len(rank)),
        )
        return [self.chunks[i] for i in picked + extra[:8]]


def generate(client, contents, config):
    """Try each model in MODELS, two attempts each, on overload/rate-limit errors."""
    last = None
    for model in MODELS:
        for attempt in range(2):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config)
            except errors.APIError as e:
                last = e
                if e.code in SKIP_MODEL:
                    break
                if e.code not in RETRYABLE:
                    raise
                time.sleep(2 * (attempt + 1))
    raise last


def answer(index, question, client=None):
    """Return {"answer", "citations", "refused", "unsupported", "sources"}."""
    client = client or genai.Client()
    hits = index.search(question)
    if not hits:
        return {"answer": NOT_FOUND, "citations": [], "refused": True, "unsupported": 0, "sources": []}

    context = "\n\n".join(
        f'<chunk number="{n}" page="{c["url"]}" section="{c["heading"]}">\n{c["text"]}\n</chunk>'
        for n, c in enumerate(hits, 1)
    )
    response = generate(
        client,
        f"{context}\n\nQuestion: {question}",
        types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=Answer,
            temperature=0,
        ),
    )
    result = response.parsed
    if not isinstance(result, Answer):
        return {"answer": "The assistant returned an invalid response. Please retry.", "citations": [], "refused": True, "unsupported": 0, "sources": []}
    if not result.found or not result.sentences:
        return {"answer": NOT_FOUND, "citations": [], "refused": True, "unsupported": 0, "sources": []}

    parts, citations, unsupported = [], [], 0
    for sentence in result.sentences:
        marks = []
        for cit in sentence.citations:
            if not 1 <= cit.chunk <= len(hits):
                continue
            src = hits[cit.chunk - 1]
            if normalize(cit.quote) and normalize(cit.quote) in normalize(src["text"]):
                citations.append({"url": src["url"], "heading": src["heading"], "quote": cit.quote.strip()})
                marks.append(f"[{len(citations)}]")
        if not marks:
            unsupported += 1
            marks.append("[unverified]")
        parts.append(f'{sentence.text.strip()} {" ".join(marks)}')
    return {
        "answer": " ".join(parts),
        "citations": citations,
        "refused": False,
        "unsupported": unsupported,
        "sources": [{"url": c["url"], "heading": c["heading"]} for c in hits],
    }
