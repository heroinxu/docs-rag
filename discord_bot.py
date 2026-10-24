"""Discord bot: answers questions from the docs index, with cited sources.

Users can ask in two ways:
    /ask question:How do I rotate an API key?
    @DocsBot how do I rotate an API key?

Needs no privileged intents: Discord delivers message text to a bot when the message mentions it.

Runs inside serve.py when DISCORD_BOT_TOKEN is set (same process and index as the web server).
Standalone for local testing:
    set DISCORD_BOT_TOKEN=...
    py discord_bot.py indexes/uv.json "uv"
"""

import asyncio
import os
import re
import sys
import time
from collections import defaultdict, deque

import discord
from discord import app_commands

from qlog import log_question
from rag import Index, answer, make_client

COLOR = int(os.environ.get("DISCORD_EMBED_COLOR", "2563eb"), 16)
USER_LIMIT = int(os.environ.get("DISCORD_RATE_LIMIT", "5"))  # questions per user per minute


def build_embed(question, res, product):
    """Discord embed for one answer, kept inside Discord's limits (description 4096, field 1024)."""
    text = res["answer"]
    if len(text) > 4000:
        text = text[:3990].rsplit(" ", 1)[0] + " ..."
    embed = discord.Embed(title=question[:250], description=text, color=COLOR)
    lines, used = [], 0
    for n, c in enumerate(res["citations"], 1):
        line = f"[{n}] [{c['heading'][:80]}]({c['url']})"
        if used + len(line) + 1 > 1000:
            lines.append(f"... and {len(res['citations']) - n + 1} more")
            break
        lines.append(line)
        used += len(line) + 1
    if lines:
        embed.add_field(name="Sources", value="\n".join(lines), inline=False)
    embed.set_footer(text=f"Answers come only from the {product} docs.")
    return embed


class DocsBot(discord.Client):
    def __init__(self, index, product):
        super().__init__(intents=discord.Intents.default())
        self.index, self.product = index, product
        self.llm = make_client()
        self.recent = defaultdict(deque)
        self.tree = app_commands.CommandTree(self)

        @self.tree.command(name="ask", description=f"Ask a question about the {product} docs")
        @app_commands.describe(question="Your question")
        async def ask(interaction: discord.Interaction, question: str):
            if self.limited(interaction.user.id):
                await interaction.response.send_message("You're asking fast. Please wait a minute.", ephemeral=True)
                return
            await interaction.response.defer(thinking=True)
            embed = await self.respond(question)
            await interaction.followup.send(embed=embed)

    async def setup_hook(self):
        await self.tree.sync()

    async def on_ready(self):
        print(f"Discord bot online as {self.user} in {len(self.guilds)} server(s)")

    async def on_message(self, message):
        if message.author.bot or self.user not in message.mentions:
            return
        question = re.sub(rf"<@!?{self.user.id}>", "", message.content).strip()
        if not question:
            await message.reply("Ask me a question about the docs, e.g. `@me how do I get started?`", mention_author=False)
            return
        if self.limited(message.author.id):
            await message.reply("You're asking fast. Please wait a minute.", mention_author=False)
            return
        async with message.channel.typing():
            embed = await self.respond(question)
        await message.reply(embed=embed, mention_author=False)

    def limited(self, user_id):
        now, hits = time.monotonic(), self.recent[user_id]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= USER_LIMIT:
            return True
        hits.append(now)
        return False

    async def respond(self, question):
        try:
            res = await asyncio.to_thread(answer, self.index, question[:2000], self.llm)
            log_question(question, res, "discord")
        except Exception as e:  # never leave the user hanging on "thinking..."
            print(f"answer failed: {type(e).__name__}: {e}")
            res = {"answer": "Sorry, I couldn't answer right now. Please try again in a minute.", "citations": []}
        return build_embed(question, res, self.product)


if __name__ == "__main__":
    index_path, product = sys.argv[1], sys.argv[2]
    DocsBot(Index(index_path), product).run(os.environ["DISCORD_BOT_TOKEN"])
