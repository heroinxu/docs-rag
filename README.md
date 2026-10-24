# docs-rag

Grounded docs assistant: crawls a public documentation site and answers questions only from it, with a citation for every claim. It powers the free demos in the Fiverr gig.

## Setup (Windows)

```
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
setx GEMINI_API_KEY "..."   (your key from aistudio.google.com; restart the terminal after)
```

## 1. Index a docs site

```
.venv\Scripts\python ingest.py https://docs.astral.sh/uv/ --max-pages 150 --out indexes/uv.json
```

It reads `/sitemap.xml` when present and otherwise follows links under the root path. The default delay between requests is 0.5s, so it stays polite to the docs host.

## 2. Run the chat demo

```
set DOCS_RAG_INDEX=indexes/uv.json
set DOCS_RAG_PRODUCT=uv (Astral)
.venv\Scripts\python -m uvicorn app:app --port 8000
```

Open http://localhost:8000.

## 3. Accuracy report

```
.venv\Scripts\python evaluate.py indexes/uv.json questions.example.jsonl --out report.md
```

The report counts answerable questions that came back with citations and out-of-scope questions that were declined. A human still reviews each answer.

## How it works

- `ingest.py`: crawl, strip nav/footers, split by headings into chunks of at most 2,400 characters.
- `rag.py`: BM25 keyword retrieval (top 8 chunks), then Gemini with JSON output. For each sentence, Gemini returns the chunk number it used plus a verbatim quote. The code checks every quote against the chunk text, drops citations that don't match, and marks sentences with no verified quote as `[unverified]`. The system prompt forbids outside knowledge and makes it say "I couldn't find this in the docs." when the answer is missing.
- `app.py` + `static/chat.html`: FastAPI server + minimal chat UI with clickable sources.
- `evaluate.py`: question set to Markdown report.

Settings (env vars): `DOCS_RAG_MODEL` (default `gemini-3.8-flash`), `DOCS_RAG_TOP_K` (default 8).

## Roadmap

- Embedding-based hybrid retrieval (BM25 + vectors) for paraphrased questions
- Discord / Slack bot front-ends
- Scheduled re-crawl to keep the index in sync
- Embeddable `<script>` widget
