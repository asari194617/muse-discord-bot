"""Resident Discord bot (asari-muse).

Run by systemd (muse-discord-bot.service). Token comes from the
DISCORD_BOT_TOKEN environment variable (loaded from .env by the unit).
Never hard-code or log the token.

Features map to the permissions granted in the Developer Portal:
threads, pin, polls, TTS messages, reactions, embeds, voice join/leave,
and scheduled events. Mention Everyone is intentionally never used.
"""

import datetime as dt
import fcntl
import json
import logging
import os
import sys
import uuid

import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("asari-muse")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
if not TOKEN:
    log.error("DISCORD_BOT_TOKEN is not set; exiting.")
    sys.exit(1)

JST = dt.timezone(dt.timedelta(hours=9))

# This VM reaches the internet through an egress proxy. discord.py needs the
# proxy passed explicitly for both REST and the gateway websocket.
PROXY = (
    os.environ.get("DISCORD_PROXY")
    or os.environ.get("HTTPS_PROXY")
    or os.environ.get("https_proxy")
    or None
)

intents = discord.Intents.default()
intents.message_content = True  # must also be enabled in the Developer Portal

# Namespace policy: this server may host other people's Muse bots, so this
# bot never occupies generic command names. Text commands require either a
# mention of this bot or the unique "!asari " prefix. Slash commands live
# under the /asari group.
bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!asari "),
    intents=intents,
    help_command=None,
    proxy=PROXY,
)


@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s).", len(synced))
    except Exception:  # sync failure should not kill the resident bot
        log.exception("Slash command sync failed")
    await bot.change_presence(activity=discord.Game(name="@メンションで対話 / !asari help"))


async def _target_message(ctx: commands.Context, arg: str | None) -> discord.Message | None:
    """Resolve a message to act on: explicit ID, replied-to message, or the command itself."""
    if arg:
        try:
            return await ctx.channel.fetch_message(int(arg))
        except (ValueError, discord.HTTPException):
            return None
    if ctx.message.reference and ctx.message.reference.message_id:
        try:
            return await ctx.channel.fetch_message(ctx.message.reference.message_id)
        except discord.HTTPException:
            return None
    return ctx.message


@bot.command(name="ping")
async def ping(ctx: commands.Context) -> None:
    latency_ms = round(bot.latency * 1000)
    embed = discord.Embed(title="Pong!", description=f"応答速度は約 {latency_ms}ms です。", color=0x5865F2)
    await ctx.reply(embed=embed)


@bot.command(name="help")
async def help_cmd(ctx: commands.Context) -> None:
    embed = discord.Embed(title="asari-muse のコマンド", color=0x5865F2)
    embed.description = (
        "呼び出し方は2通り（他のBotと名前がぶつからないよう、専用の呼び方だけに反応します）:\n"
        "メンション: `@asari-muse ping` / プレフィックス: `!asari ping`\n\n"
        "• `ping` — 生存確認\n"
        "• `thread タイトル` — このメッセージから公開スレッドを作成\n"
        "• `pin [メッセージID]` — メッセージをピン留め（返信先の指定も可）\n"
        "• `poll 質問 | 選択肢1 | 選択肢2 ...` — 投票を作成（24時間）\n"
        "• `react 絵文字` — 返信先のメッセージにリアクション\n"
        "• `tts 文章` — 読み上げ用メッセージを送信\n"
        "• `join` / `leave` — ボイスチャンネルに参加 / 退出\n"
        "• `event 名前 | 開始 | 終了 | 場所 | 説明` — サーバーイベントを作成\n"
        "  例: `!asari event 勉強会 | 2026-11-01 20:00 | 2026-11-01 21:00 | オンライン | 資料は事前に共有`\n"
        "• `/asari ping` — スラッシュコマンド版の生存確認\n"
        "• メンションして普通に話しかけると、オーナー本人だけ対話できます"
    )
    await ctx.reply(embed=embed)


@bot.command(name="thread")
async def thread_cmd(ctx: commands.Context, *, title: str) -> None:
    if not isinstance(ctx.channel, discord.TextChannel):
        await ctx.reply("テキストチャンネルで使ってください。")
        return
    thread = await ctx.message.create_thread(name=title[:100])
    await thread.send(f"{ctx.author.mention} スレッドを作成しました。ここで続きをどうぞ。")
    await ctx.reply(f"スレッドを作成しました: {thread.mention}")


@bot.command(name="pin")
async def pin_cmd(ctx: commands.Context, message_id: str | None = None) -> None:
    target = await _target_message(ctx, message_id)
    if target is None:
        await ctx.reply("ピン留めするメッセージが見つかりませんでした。")
        return
    try:
        await target.pin()
        await ctx.reply("ピン留めしました。")
    except discord.Forbidden:
        await ctx.reply("ピン留めの権限が足りませんでした。")


@bot.command(name="poll")
async def poll_cmd(ctx: commands.Context, *, spec: str) -> None:
    parts = [p.strip() for p in spec.split("|") if p.strip()]
    if len(parts) < 3:
        await ctx.reply("形式: `!poll 質問 | 選択肢1 | 選択肢2 ...`（選択肢は2〜10個）")
        return
    question, answers = parts[0], parts[1:11]
    poll = discord.Poll(question=question, duration=dt.timedelta(hours=24))
    for answer in answers:
        poll.add_answer(text=answer[:55])
    await ctx.send(poll=poll)


@bot.command(name="react")
async def react_cmd(ctx: commands.Context, emoji: str) -> None:
    target = await _target_message(ctx, None)
    if target is ctx.message:
        await ctx.reply("リアクションをつけたいメッセージに返信してから使ってください。")
        return
    try:
        await target.add_reaction(emoji)
    except discord.HTTPException:
        await ctx.reply("その絵文字ではリアクションできませんでした。")


@bot.command(name="tts")
async def tts_cmd(ctx: commands.Context, *, text: str) -> None:
    await ctx.send(text[:500], tts=True)


@bot.command(name="join")
async def join_cmd(ctx: commands.Context) -> None:
    voice = ctx.author.voice if isinstance(ctx.author, discord.Member) else None
    if not voice or not voice.channel:
        await ctx.reply("先にボイスチャンネルに入ってから呼んでください。")
        return
    channel = voice.channel
    if ctx.voice_client is None:
        await channel.connect()
        await ctx.reply(f"{channel.name} に参加しました。")
    else:
        await ctx.voice_client.move_to(channel)
        await ctx.reply(f"{channel.name} に移動しました。")


@bot.command(name="leave")
async def leave_cmd(ctx: commands.Context) -> None:
    if ctx.voice_client is not None:
        await ctx.voice_client.disconnect()
        await ctx.reply("ボイスチャンネルから退出しました。")
    else:
        await ctx.reply("ボイスチャンネルに参加していません。")


@bot.command(name="event")
async def event_cmd(ctx: commands.Context, *, spec: str) -> None:
    if ctx.guild is None:
        await ctx.reply("サーバー内で使ってください。")
        return
    parts = [p.strip() for p in spec.split("|")]
    if len(parts) < 5:
        await ctx.reply("形式: `!event 名前 | 開始 | 終了 | 場所 | 説明`（日時は `2026-11-01 20:00` の形）")
        return
    name, start_s, end_s, location, description = parts[:5]
    try:
        start = dt.datetime.strptime(start_s, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
        end = dt.datetime.strptime(end_s, "%Y-%m-%d %H:%M").replace(tzinfo=JST)
    except ValueError:
        await ctx.reply("日時の形式が違うようです。例: `2026-11-01 20:00`")
        return
    try:
        event = await ctx.guild.create_scheduled_event(
            name=name[:100],
            description=description[:1000],
            start_time=start,
            end_time=end,
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location=location[:100],
        )
        await ctx.reply(f"イベントを作成しました: {event.name}（{start:%m/%d %H:%M}〜）")
    except discord.Forbidden:
        await ctx.reply("イベント作成の権限が足りませんでした。")
    except discord.HTTPException as exc:
        await ctx.reply(f"イベントを作成できませんでした: {exc.text}")


asari_group = discord.app_commands.Group(name="asari", description="asari-muse のコマンド")


@asari_group.command(name="ping", description="Botの生存確認をします")
async def ping_slash(interaction: discord.Interaction) -> None:
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 応答速度は約 {latency_ms}ms です。")


bot.tree.add_command(asari_group)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_DIR = os.path.join(BASE_DIR, "queue")
PENDING_PATH = os.path.join(QUEUE_DIR, "pending.jsonl")
LOCK_PATH = os.path.join(QUEUE_DIR, "queue.lock")
OWNER_PATH = os.path.join(BASE_DIR, "owner.json")


def _owner_id() -> str | None:
    try:
        with open(OWNER_PATH) as f:
            return str(json.load(f).get("owner_id") or "") or None
    except Exception:
        return None


def _enqueue(entry: dict) -> None:
    os.makedirs(QUEUE_DIR, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(LOCK_PATH, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(PENDING_PATH, "a") as f:
            f.write(line)
        fcntl.flock(lock, fcntl.LOCK_UN)


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    mentioned = bot.user is not None and bot.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    if mentioned or is_dm:
        content = message.clean_content
        if bot.user is not None:
            content = content.replace(f"@{bot.user.display_name}", "").strip()
        owner = _owner_id()
        entry = {
            "id": uuid.uuid4().hex,
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "guild_id": str(message.guild.id) if message.guild else None,
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
            "author_id": str(message.author.id),
            "author_name": message.author.display_name,
            "content": content[:1500],
        }
        first_word = content.split(maxsplit=1)[0].lower() if content else ""
        is_command_call = first_word in {c.name for c in bot.commands}
        if owner is None:
            entry["kind"] = "claim"
            _enqueue(entry)
            await message.reply("オーナー登録の確認用に記録しました。登録が終わるまで少し待ってください。")
        elif str(message.author.id) == owner:
            if not is_command_call:
                entry["kind"] = "chat"
                _enqueue(entry)
                try:
                    await message.add_reaction("👀")
                except discord.HTTPException:
                    pass
        elif mentioned:
            await message.reply("私はオーナー専用のBotです。コマンドは `!asari help` を見てください。")
    await bot.process_commands(message)


if __name__ == "__main__":
    bot.run(TOKEN, log_handler=None)
