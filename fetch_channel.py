"""Fetch recent messages from a Discord channel as the bot.

Usage: fetch_channel.py <channel_id> [limit]
Reads the bot token from .env and the egress proxy from the live
environment first, then proxy.env (both in this directory).
Prints a JSON array of {id, author_id, author_name, content, ts, reply_to}.
reply_to is {id, author_name, content, ts} of the referenced message when the
message is a reply, else null.
Never prints the token.
"""

import json
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))


def _load_env(path: str) -> dict:
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def api(path: str):
    env = _load_env(os.path.join(BASE, ".env"))
    token = env.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("token not found")
    proxy_env = _load_env(os.path.join(BASE, "proxy.env"))
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or proxy_env.get("HTTPS_PROXY")
        or proxy_env.get("https_proxy")
    )
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        method="GET",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://example.org, 1.0)",
        },
    )
    with opener.open(req, timeout=30) as r:
        return json.load(r)


def _fetch_refs(channel_id: str, refs: dict) -> dict:
    """Fetch referenced (replied-to) messages, deduplicated by id."""
    out = {}
    for mid, ch in refs.items():
        try:
            rm = api(f"/channels/{ch}/messages/{mid}")
            ra = rm.get("author", {})
            out[mid] = {
                "id": mid,
                "author_name": ra.get("global_name") or ra.get("username"),
                "content": rm.get("content", ""),
                "ts": rm.get("timestamp"),
            }
        except Exception:
            out[mid] = {"id": mid, "error": "fetch failed"}
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    channel_id = sys.argv[1]
    limit = min(int(sys.argv[2]) if len(sys.argv) > 2 else 20, 100)
    msgs = api(f"/channels/{channel_id}/messages?limit={limit}")
    refs = {}
    for m in msgs:
        ref = m.get("message_reference") or {}
        ref_mid = ref.get("message_id")
        if ref_mid and ref_mid not in refs:
            refs[ref_mid] = ref.get("channel_id") or channel_id
    ref_cache = _fetch_refs(channel_id, refs)
    out = []
    for m in msgs:
        author = m.get("author", {})
        ref = m.get("message_reference") or {}
        ref_mid = ref.get("message_id")
        out.append(
            {
                "id": m.get("id"),
                "author_id": author.get("id"),
                "author_name": author.get("global_name") or author.get("username"),
                "content": m.get("content", ""),
                "ts": m.get("timestamp"),
                "reply_to": ref_cache.get(ref_mid) if ref_mid else None,
            }
        )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
