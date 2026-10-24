"""Post a reply to a Discord message as the bot.

Usage: reply.py <channel_id> <message_id> <text>
Reads the bot token from .env and the egress proxy from proxy.env
(both in this directory). Prints the new message id on success.
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


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    channel_id, message_id, text = sys.argv[1], sys.argv[2], sys.argv[3][:1900]
    token = _load_env(os.path.join(BASE, ".env")).get("DISCORD_BOT_TOKEN", "")
    if not token:
        print("token not found", file=sys.stderr)
        return 1
    # Prefer the live process environment: proxy credentials rotate between
    # sessions, and agent sessions carry fresh ones. Fall back to proxy.env
    # (used by the systemd service, which has no shell environment).
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
    body = json.dumps(
        {
            "content": text,
            "message_reference": {"message_id": message_id},
            "allowed_mentions": {"replied_user": True, "parse": []},
        }
    ).encode()
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (https://example.org, 1.0)",
        },
    )
    with opener.open(req, timeout=30) as r:
        data = json.load(r)
    print(data.get("id", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
