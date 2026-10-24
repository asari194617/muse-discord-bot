"""Per-channel conversation history for the Discord bridge worker.

Usage:
  history.py show <channel_id> [count]   -> last N entries as JSON
  history.py add <channel_id> <role> <author> <text>
"""

import datetime as dt
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
HIST_DIR = os.path.join(BASE, "queue", "history")


def _path(channel_id: str) -> str:
    return os.path.join(HIST_DIR, f"{channel_id}.jsonl")


def main() -> int:
    os.makedirs(HIST_DIR, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "show" and len(sys.argv) >= 3:
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        path = _path(sys.argv[2])
        entries = []
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        print(json.dumps(entries[-n:], ensure_ascii=False, indent=1))
        return 0
    if cmd == "add" and len(sys.argv) >= 6:
        entry = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "role": sys.argv[3],
            "author": sys.argv[4],
            "text": sys.argv[5][:1500],
        }
        with open(_path(sys.argv[2]), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print("ok")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
