"""Fetch recent messages from a Discord channel as the bot.

Usage: fetch_channel.py <channel_id> [limit]
Reads the bot token from .env and the egress proxy from the live
environment first, then proxy.env (both in this directory).
Prints a JSON array of {id, author_id, author_name, content, ts}.
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


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    channel_id = sys.argv[1]
    limit = min(int(sys.argv[2]) if len(sys.argv) > 2 else 20, 100)
    msgs = api(f"/channels/{channel_id}/messages?limit={limit}")
    out = []
    for m in msgs:
        author = m.get("author", {})
        out.append(
            {
                "id": m.get("id"),
                "author_id": author.get("id"),
                "author_name": author.get("global_name") or author.get("username"),
                "content": m.get("content", ""),
                "ts": m.get("timestamp"),
            }
        )
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
