#!/usr/bin/env python3
"""HTTP CONNECT helper for SSH ProxyCommand via the tailnet tunnel proxy.

Usage: ts_connect.py <host> <port>
Reads HTTPS_PROXY from the environment, rewrites its port to 3130
(the Tailscale tunnel selector), performs CONNECT, then relays
stdin/stdout to the tunnel socket. Proxy credentials come from the
environment only and are never printed.
"""
import base64
import os
import select
import socket
import sys
from urllib.parse import urlparse


def main() -> int:
    host, port = sys.argv[1], int(sys.argv[2])
    p = urlparse(os.environ["HTTPS_PROXY"])
    proxy_host = p.hostname
    proxy_port = 3130
    s = socket.create_connection((proxy_host, proxy_port), timeout=120)
    auth = ""
    if p.username:
        cred = f"{p.username}:{p.password or ''}"
        auth = "Proxy-Authorization: Basic " + base64.b64encode(cred.encode()).decode() + "\r\n"
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n{auth}\r\n"
    s.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(4096)
        if not chunk:
            print("CONNECT failed: connection closed", file=sys.stderr)
            return 1
        buf += chunk
    status_line = buf.split(b"\r\n", 1)[0].decode(errors="replace")
    if " 200 " not in status_line and not status_line.endswith(" 200"):
        print(f"CONNECT failed: {status_line}", file=sys.stderr)
        return 1
    leftover = buf.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in buf else b""
    if leftover:
        sys.stdout.buffer.write(leftover)
        sys.stdout.buffer.flush()
    # Relay stdin <-> socket until either side closes.
    s.setblocking(False)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    import fcntl
    flags = fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL)
    fcntl.fcntl(stdin.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)
    while True:
        rlist, _, _ = select.select([s, stdin], [], [], 60)
        if not rlist:
            continue
        for r in rlist:
            if r is s:
                try:
                    data = s.recv(65536)
                except BlockingIOError:
                    continue
                if not data:
                    return 0
                stdout.write(data)
                stdout.flush()
            else:
                try:
                    data = os.read(stdin.fileno(), 65536)
                except BlockingIOError:
                    continue
                if not data:
                    try:
                        s.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    # keep reading until remote closes
                    stdin_closed = True
                    # remove stdin from watch by substituting /dev/null
                    stdin = open("/dev/null", "rb")
                    continue
                s.sendall(data)


if __name__ == "__main__":
    raise SystemExit(main())
