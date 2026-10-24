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

Shareable link that asks a question on load: `http://localhost:8000/?q=How+do+I+install+uv`

## 4. Website widget

Add one line to any page of the client's site:

```html
<script src="https://YOUR-HOST/widget.js" async
  data-title="Ask the docs"
  data-greeting="Hi! Ask me anything about our docs."
  data-color="#2563eb"
  data-position="right"></script>
```

A chat bubble appears in the corner. Answers show clickable sources. The widget renders in a Shadow DOM, so it can't clash with the site's CSS, and it goes full screen on phones. Try it at http://localhost:8000/widget-demo.

Server settings: `DOCS_RAG_ALLOWED_ORIGINS` (comma-separated sites allowed to call the API, default `*`; set it to the client's domain in production) and `DOCS_RAG_RATE_LIMIT` (questions per visitor IP per minute, default 10).

## 5. Static demo snapshot

```
.venv\Scripts\python snapshot.py indexes/uv.json "uv (Astral)" demo.html "How do I migrate from pip to a uv project?" "What is Astral's annual revenue?"
```

Runs real questions through the engine and saves a static chat page (no server needed) that you can screenshot or send.

## Deploying for a client

See [DEPLOY.md](DEPLOY.md): Render Blueprint (`render.yaml`), any VPS via `serve.py`, widget install, settings and the handover checklist.

## How it works

- `ingest.py`: crawl, strip nav/footers, split by headings into chunks of at most 2,400 characters.
- `rag.py`: BM25 keyword retrieval (top 8 chunks), then Gemini with JSON output. For each sentence, Gemini returns the chunk number it used plus a verbatim quote. The code checks every quote against the chunk text, drops citations that don't match, and marks sentences with no verified quote as `[unverified]`. The system prompt forbids outside knowledge and makes it say "I couldn't find this in the docs." when the answer is missing.
- `app.py` + `static/chat.html`: FastAPI server + minimal chat UI with clickable sources.
- `static/widget.js`: embeddable chat widget for client websites (CORS + per-IP rate limit on the server).
- `discord_bot.py`: Discord bot (`/ask` and @mentions) with linked sources; runs inside `serve.py` when `DISCORD_BOT_TOKEN` is set.
- `slack_bot.py`: Slack bot (`/ask` and @mentions in threads, Socket Mode, no public URL needed); runs inside `serve.py` when `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` are set.
- `qlog.py` + `questions_report.py`: question log (no personal data) and top-questions report (most asked, unanswered = docs gaps, most cited pages); also served at `/admin/questions` behind `DOCS_RAG_ADMIN_TOKEN`.
- `evaluate.py`: question set to Markdown report.

Settings (env vars): `DOCS_RAG_MODEL` (comma-separated, primary then fallbacks; default `gemini-3.8-flash,gemini-3.5-flash,gemini-flash-latest,gemini-3.5-flash-lite`), `DOCS_RAG_TOP_K` (default 8), `DOCS_RAG_TIMEOUT_MS` (per-request timeout, default 40000). Overloaded, rate-limited, timed-out or retired models fall back to the next one.

## Roadmap

- Embedding-based hybrid retrieval (BM25 + vectors) for paraphrased questions
- Scheduled re-crawl to keep the index in sync
