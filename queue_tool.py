"""Queue helper for the Discord bridge worker.

Usage:
  queue_tool.py list           -> print pending entries as JSON array
  queue_tool.py done <id...>   -> remove those entries from pending, append to archive
"""

import fcntl
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
QUEUE_DIR = os.path.join(BASE, "queue")
PENDING = os.path.join(QUEUE_DIR, "pending.jsonl")
ARCHIVE = os.path.join(QUEUE_DIR, "archive.jsonl")
LOCK = os.path.join(QUEUE_DIR, "queue.lock")


def _read_lines() -> list[str]:
    if not os.path.exists(PENDING):
        return []
    with open(PENDING) as f:
        return [ln for ln in f.read().splitlines() if ln.strip()]


def main() -> int:
    os.makedirs(QUEUE_DIR, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        entries = []
        for ln in _read_lines():
            try:
                entries.append(json.loads(ln))
            except json.JSONDecodeError:
                pass
        print(json.dumps(entries, ensure_ascii=False, indent=1))
        return 0
    if cmd == "done":
        done_ids = set(sys.argv[2:])
        if not done_ids:
            print("no ids given", file=sys.stderr)
            return 2
        with open(LOCK, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            kept, done = [], []
            for ln in _read_lines():
                try:
                    entry = json.loads(ln)
                except json.JSONDecodeError:
                    kept.append(ln)
                    continue
                (done if entry.get("id") in done_ids else kept).append(ln)
            tmp = PENDING + ".tmp"
            with open(tmp, "w") as f:
                f.write("\n".join(kept) + ("\n" if kept else ""))
            os.replace(tmp, PENDING)
            if done:
                with open(ARCHIVE, "a") as f:
                    f.write("\n".join(done) + "\n")
            fcntl.flock(lock, fcntl.LOCK_UN)
        print(f"marked done: {len(done)}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
