#!/usr/bin/env python3
"""Sync the remote bot's queue into the local bridge queue.

Design (post-migration): the bot runs on dcon2027 and appends owner
mentions/claims to ~/asari-muse/queue/pending.jsonl THERE. This script
mirrors that file locally over SSH (Tailscale), then rebuilds the local
queue/pending.jsonl as: remote entries whose id is NOT in the local
archive.jsonl (i.e. not yet processed by the bridge worker).

When every remote entry is already archived, the remote pending file is
truncated over SSH under the bot's flock so it stays small.

Usage: sync_remote_queue.py [--base DIR]   (default: this script's dir)
Prints one JSON status line. Exits 0 even on sync failure (status field
reports it) so the hook can decide to stay silent.
"""
import json
import os
import subprocess
import sys

SSH_BASE = ["ssh", "-F", "/home/hatch/.ssh/config",
            "-o", "ConnectTimeout=20", "-o", "BatchMode=yes", "dcon2027"]
REMOTE_PENDING = "/home/asari194617/asari-muse/queue/pending.jsonl"
REMOTE_TRUNCATE = (
    "python3 - <<'PY'\n"
    "import fcntl\n"
    "base='/home/asari194617/asari-muse/queue'\n"
    "lock=open(base+'/queue.lock','a')\n"
    "fcntl.flock(lock, fcntl.LOCK_EX)\n"
    "open(base+'/pending.jsonl','w').close()\n"
    "fcntl.flock(lock, fcntl.LOCK_UN)\n"
    "print('truncated')\n"
    "PY"
)


def fetch_remote() -> list[dict]:
    out = subprocess.run(
        SSH_BASE + [f"cat {REMOTE_PENDING} 2>/dev/null || true"],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ssh cat failed rc={out.returncode}")
    entries = []
    for ln in out.stdout.splitlines():
        ln = ln.strip()
        if ln:
            entries.append(json.loads(ln))
    return entries


def main() -> int:
    base = os.path.dirname(os.path.abspath(__file__))
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1]
    qdir = os.path.join(base, "queue")
    os.makedirs(qdir, exist_ok=True)
    pending_path = os.path.join(qdir, "pending.jsonl")
    archive_path = os.path.join(qdir, "archive.jsonl")

    archived_ids = set()
    if os.path.exists(archive_path):
        with open(archive_path) as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    try:
                        archived_ids.add(json.loads(ln)["id"])
                    except (json.JSONDecodeError, KeyError):
                        pass

    try:
        remote = fetch_remote()
    except Exception as e:  # sync failure: keep local state untouched
        print(json.dumps({"sync": "failed", "error": str(e)[:200]}))
        return 0

    unprocessed = [e for e in remote if e.get("id") not in archived_ids]
    tmp = pending_path + ".tmp"
    with open(tmp, "w") as f:
        for e in unprocessed:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, pending_path)

    truncated = False
    if remote and not unprocessed:
        try:
            r = subprocess.run(SSH_BASE + [REMOTE_TRUNCATE],
                               capture_output=True, text=True, timeout=60)
            truncated = r.returncode == 0
        except Exception:
            truncated = False

    print(json.dumps({"sync": "ok", "remote": len(remote),
                      "pending": len(unprocessed), "truncated": truncated}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
