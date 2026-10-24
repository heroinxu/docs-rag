# Deploying for a client

One deployment per client: a small web service that indexes their docs at build time, serves the chat API and the widget script, and only accepts calls from their domain.

Tested locally (build step, start step, health check, origin restriction). The Render Blueprint follows Render's documented format, but it hasn't been run on a live Render account yet, so watch the first deploy's logs.

---

## Before you start (ask the client)

| Need | Why |
|---|---|
| Public docs URL | What gets indexed |
| The domain(s) where the widget will appear, e.g. `https://docs.example.com` | Only these sites may call the API |
| Who pays for hosting and AI usage | Recommended: the client creates the Render and Google AI Studio accounts, so the bills and keys are theirs from day one |
| Brand color and widget title | Widget look |

Recommended setup: **the client owns the accounts and invites you** (Render team member, or they paste the key into Render themselves). Never send API keys over Fiverr chat.

---

## Option A: Render (recommended)

1. **Repo:** fork `github.com/heroinxu/docs-rag` into the client's GitHub (or a private repo you transfer at handover).
2. **Render:** Dashboard, then **New**, then **Blueprint**, then pick the repo. Render reads `render.yaml`.
3. **Fill in the prompted values:**
   - `GEMINI_API_KEY`: the client's key from aistudio.google.com
   - `DOCS_RAG_DOCS_URL`: e.g. `https://docs.example.com/`
   - `DOCS_RAG_PRODUCT`: product name shown in the chat page title
   - `DOCS_RAG_ALLOWED_ORIGINS`: e.g. `https://docs.example.com,https://www.example.com`
4. **Deploy.** The build log should end with `Saved N chunks from M pages`. If it shows `0 chunks`, the docs site is probably JavaScript-rendered; see Troubleshooting.
5. **Check:** open `https://YOUR-SERVICE.onrender.com/health`. It should return `{"ok": true, "chunks": N}`. Then open the root URL and ask 3 real questions.
6. **Pick a plan.** Free web services on Render spin down when idle, so the first question after a quiet period is slow. For a client's live docs site, use a paid instance. Check current prices at render.com/pricing.

**Updating the docs index:** trigger **Manual Deploy**. The build command sets `DOCS_RAG_REINDEX=1`, so every deploy re-crawls; the start step reuses that index. To schedule it, use a Render Cron Job or the client's CI calling Render's deploy hook.

## Option B: Railway or any VPS

The same two commands work anywhere with Python 3.11 or newer:

```
pip install -r requirements.txt && python serve.py --index-only   # build
python serve.py                                                   # start (listens on $PORT)
```

On a VPS, run the start command under systemd or a process manager, behind Caddy or nginx for HTTPS. The widget must be served over HTTPS, or browsers block it on HTTPS docs sites.

---

## Install the widget on the client's site

Send them this one line. It goes before `</body>`, or in their docs platform's "custom script" setting:

```html
<script src="https://YOUR-SERVICE.onrender.com/widget.js" async
  data-title="Ask the docs" data-color="#2563eb"></script>
```

Most docs platforms (Docusaurus, Mintlify, GitBook, ReadMe) have a custom-script or custom-HTML setting. Check that platform's own docs for the exact place.

## Discord bot (Premium)

The bot runs in the same service as the website widget and uses the same index. Users ask with `/ask question:...` or by mentioning the bot (`@DocsBot how do I...`). Answers arrive as an embed with linked sources. No privileged intents are needed.

**Steps (done by the client, or by you with their Discord account access):**

1. Go to discord.com/developers/applications, click **New Application** and name it (e.g. "Example Docs").
2. Open the **Bot** tab and click **Reset Token**. Copy the token; it's shown once. Leave all "Privileged Gateway Intents" **off**.
3. Invite it to the server. Copy the **Application ID** from **General Information**, then open:
   ```
   https://discord.com/oauth2/authorize?client_id=APPLICATION_ID&scope=bot+applications.commands&permissions=84992
   ```
   `84992` = View Channels + Send Messages + Embed Links + Read Message History.
4. In Render, go to the service's **Environment**, add `DISCORD_BOT_TOKEN` = the token, and save. The service restarts.
5. Check the service log for `Discord bot online as ...`. The `/ask` command can take a few minutes to appear the first time.

If the token is wrong, the log shows `Discord bot stopped: LoginFailure ...`, and the website widget keeps working.

Bot settings: `DISCORD_RATE_LIMIT` (questions per user per minute, default 5) and `DISCORD_EMBED_COLOR` (hex without `#`, default `2563eb`).

## Settings reference

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | (required) | AI provider key |
| `DOCS_RAG_DOCS_URL` | (required for indexing) | Docs root to crawl |
| `DOCS_RAG_MAX_PAGES` | 150 | Crawl limit: 150 Basic, 1,000 Standard, 5,000 Premium |
| `DOCS_RAG_ALLOWED_ORIGINS` | `*` | Sites allowed to call the API. **Always set this in production** |
| `DOCS_RAG_RATE_LIMIT` | 10 | Questions per visitor IP per minute |
| `DOCS_RAG_PRODUCT` | docs URL | Name on the chat page |
| `DOCS_RAG_MODEL` | Gemini fallback list | Models, comma-separated, tried in order |
| `DOCS_RAG_TIMEOUT_MS` | 40000 | Per-request timeout before falling back |
| `DOCS_RAG_REINDEX` | (off) | `1` forces a re-crawl even if an index exists |

## Troubleshooting

- **`0 chunks` after the build:** the site renders its content with JavaScript, or blocks crawlers. Ask the client for a Markdown or HTML export, or for the docs' GitHub repo.
- **Widget shows "Sorry, something went wrong":** open the browser console. A CORS error means the site's domain is missing from `DOCS_RAG_ALLOWED_ORIGINS` (include `https://` and no trailing slash).
- **Slow answers:** the Gemini models are overloaded. The server falls back automatically. If it persists, set `DOCS_RAG_MODEL` to a faster model first.
- **"Too many questions":** the rate limit is working. Raise `DOCS_RAG_RATE_LIMIT` if real users hit it.

## Handover checklist (send with the delivery)

- [ ] Service URL, health URL and the widget embed line
- [ ] Accounts: who owns Render, Google AI Studio and the GitHub repo
- [ ] How to update the index (Manual Deploy) and how often
- [ ] Accuracy report (Standard: 50 questions, Premium: 200), from `evaluate.py`
- [ ] Monthly cost estimate: hosting plan + AI usage (Gemini pricing at ai.google.dev)
- [ ] What happens when docs change, and when to re-index
