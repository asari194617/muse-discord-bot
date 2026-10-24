"""Post a standalone message to a Discord channel as the bot.

Usage: post.py <channel_id> <text>
Reads the bot token from .env in this directory; proxy from the live
environment first, then proxy.env. Prints the new message id.
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


def api(method: str, path: str, body: dict | None = None):
    token = _load_env(os.path.join(BASE, ".env")).get("DISCORD_BOT_TOKEN", "")
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
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://discord.com/api/v10{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://example.org, 1.0)",
        },
    )
    with opener.open(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    channel_id, text = sys.argv[1], sys.argv[2][:1900]
    data = api("POST", f"/channels/{channel_id}/messages", {"content": text})
    print(data.get("id", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
