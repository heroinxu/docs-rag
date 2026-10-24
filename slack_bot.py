"""Slack bot: answers questions from the docs index, with linked sources.

Users can ask in two ways:
    /ask How do I rotate an API key?
    @DocsBot how do I rotate an API key?      (answers in a thread)

Uses Socket Mode, so the bot needs no public URL: it connects out to Slack.
Needs two tokens from the Slack app: SLACK_BOT_TOKEN (xoxb-...) and SLACK_APP_TOKEN (xapp-...).

Runs inside serve.py when both tokens are set (same process and index as the web server).
Standalone for local testing:
    py slack_bot.py indexes/uv.json "uv"
"""

import asyncio
import os
import re
import sys
import time
from collections import defaultdict, deque

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from qlog import log_question
from rag import Index, answer, make_client

USER_LIMIT = int(os.environ.get("SLACK_RATE_LIMIT", "5"))  # questions per user per minute
MENTION = re.compile(r"<@[A-Z0-9]+>")


def esc(text):
    # Slack mrkdwn needs &, < and > escaped; everything else passes through.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_blocks(question, res, product):
    """Slack Block Kit message for one answer, inside Slack's limits (3000 chars per text block)."""
    text = esc(res["answer"])
    if len(text) > 2900:
        text = text[:2890].rsplit(" ", 1)[0] + " ..."
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{esc(question[:200])}*"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]
    lines, used = [], 0
    for n, c in enumerate(res["citations"], 1):
        line = f"[{n}] <{c['url']}|{esc(c['heading'][:80])}>"
        if used + len(line) + 1 > 2800:
            lines.append(f"... and {len(res['citations']) - n + 1} more")
            break
        lines.append(line)
        used += len(line) + 1
    if lines:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*Sources*\n" + "\n".join(lines)}})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"Answers come only from the {esc(product)} docs."}]})
    return blocks


class SlackDocsBot:
    def __init__(self, index, product, bot_token, app_token):
        self.index, self.product, self.app_token = index, product, app_token
        self.llm = make_client()
        self.recent = defaultdict(deque)
        self.app = AsyncApp(token=bot_token)
        self.app.command("/ask")(self.on_command)
        self.app.event("app_mention")(self.on_mention)

    def limited(self, user_id):
        now, hits = time.monotonic(), self.recent[user_id]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= USER_LIMIT:
            return True
        hits.append(now)
        return False

    async def respond_blocks(self, question):
        try:
            res = await asyncio.to_thread(answer, self.index, question[:2000], self.llm)
            log_question(question, res, "slack")
        except Exception as e:  # never leave the user without a reply
            print(f"answer failed: {type(e).__name__}: {e}")
            res = {"answer": "Sorry, I couldn't answer right now. Please try again in a minute.", "citations": []}
        return build_blocks(question, res, self.product), res["answer"][:200]

    async def on_command(self, ack, command, respond):
        question = (command.get("text") or "").strip()
        if not question:
            await ack("Usage: `/ask How do I get started?`")
            return
        if self.limited(command["user_id"]):
            await ack("You're asking fast. Please wait a minute.")
            return
        await ack()  # Slack needs an ack within 3 seconds; the answer follows
        blocks, fallback = await self.respond_blocks(question)
        await respond(response_type="in_channel", blocks=blocks, text=fallback)

    async def on_mention(self, event, say):
        question = MENTION.sub("", event.get("text", "")).strip()
        thread = event.get("thread_ts") or event["ts"]
        if not question:
            await say(text="Ask me a question about the docs, e.g. `@me how do I get started?`", thread_ts=thread)
            return
        if self.limited(event.get("user", "?")):
            await say(text="You're asking fast. Please wait a minute.", thread_ts=thread)
            return
        blocks, fallback = await self.respond_blocks(question)
        await say(blocks=blocks, text=fallback, thread_ts=thread)

    async def start(self):
        # Check both tokens once up front: with a bad token the Socket Mode client retries forever.
        who = await self.app.client.auth_test()
        await self.app.client.apps_connections_open(app_token=self.app_token)
        print(f"Slack bot online as {who['user']} in workspace {who['team']}")
        await AsyncSocketModeHandler(self.app, self.app_token).start_async()


if __name__ == "__main__":
    index_path, product = sys.argv[1], sys.argv[2]
    bot = SlackDocsBot(Index(index_path), product, os.environ["SLACK_BOT_TOKEN"], os.environ["SLACK_APP_TOKEN"])
    asyncio.run(bot.start())
