"""Production entry point: build the docs index if needed, then start the server.

Environment:
    DOCS_RAG_DOCS_URL    public docs root to index, e.g. https://docs.example.com/
    DOCS_RAG_MAX_PAGES   page limit for indexing (default 150)
    DOCS_RAG_INDEX       index file path (default indexes/index.json)
    DOCS_RAG_REINDEX     "1" to rebuild the index even if it exists
    PORT                 port to listen on (set by Render/Railway; default 8000)
    DISCORD_BOT_TOKEN    optional: also run the Discord bot in the same process
    SLACK_BOT_TOKEN      optional, with SLACK_APP_TOKEN: also run the Slack bot (Socket Mode)

Usage:
    py serve.py --index-only   # build step: crawl and index, then exit
    py serve.py                # start step: index if missing, then serve
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
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


async def run(port):
    import uvicorn

    from app import INDEX as index, PRODUCT, app  # imported after build_index so the index exists

    jobs = [uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port)).serve()]
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        jobs.append(run_bot(index, PRODUCT, token))
    slack_bot, slack_app = os.environ.get("SLACK_BOT_TOKEN"), os.environ.get("SLACK_APP_TOKEN")
    if slack_bot and slack_app:
        jobs.append(run_slack(index, PRODUCT, slack_bot, slack_app))
    elif slack_bot or slack_app:
        print("Slack bot not started: set both SLACK_BOT_TOKEN and SLACK_APP_TOKEN.")
    await asyncio.gather(*jobs)


async def run_slack(index, product, bot_token, app_token):
    # Same isolation as Discord: a Slack failure must not stop the website widget.
    from slack_bot import SlackDocsBot

    try:
        await SlackDocsBot(index, product, bot_token, app_token).start()
    except Exception as e:
        detail = getattr(getattr(e, "response", None), "data", None) or e  # SlackApiError carries {"error": "invalid_auth"}
        print(f"Slack bot stopped: {type(e).__name__}: {detail}. The web server keeps running.")


async def run_bot(index, product, token):
    # A bad token or Discord outage must not take the website widget down with it.
    from discord_bot import DocsBot

    try:
        await DocsBot(index, product).start(token)
    except Exception as e:
        print(f"Discord bot stopped: {type(e).__name__}: {e}. The web server keeps running.")


def main():
    build_index()
    if "--index-only" in sys.argv:
        return
    asyncio.run(run(int(os.environ.get("PORT", "8000"))))


if __name__ == "__main__":
    main()
