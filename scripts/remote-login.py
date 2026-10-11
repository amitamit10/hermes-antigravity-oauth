#!/usr/bin/env python3
"""Remote / headless login helper for the Antigravity CLI (`agy`).

`agy` signs in through an interactive OAuth flow: it prints a Google URL and
waits ~60 seconds for the authorization code on its own TTY. That is fine on a
local terminal, but unusable when the person approving is elsewhere — an SSH
session without a browser, a chat-driven agent host, anything where relaying
the code takes longer than one terminal round-trip.

This script bridges that gap with only the standard library:

  1. It spawns `agy` under a PTY (so agy believes it is interactive).
  2. It prints the OAuth URL as ``LOGIN_URL=<url>`` for easy parsing, and
     optionally writes it to ``--url-file``.
  3. It waits for the code from ``--code-file`` (polled every 0.5 s and fed
     the instant it arrives — agy is silent during its wait, so blocking on
     its output would starve the relay) or from stdin, then verifies the
     session with ``agy models``.

Because the waiter polls the code file instead of blocking on agy output, the
code is delivered even while agy sits silent in its 60-second wait — the
common failure mode of naive ``expect``-style wrappers.

Usage:
    python3 scripts/remote-login.py [--agy PATH] [--code-file PATH]
                                    [--url-file PATH] [--timeout SECONDS]

Example (approver relays the code through a chat):
    python3 scripts/remote-login.py --code-file /tmp/agy-code.txt &
    # open the printed LOGIN_URL, approve, then:
    printf '%s' '<code>' > /tmp/agy-code.txt
    wait   # exits 0 once `agy models` confirms the session
"""

from __future__ import annotations

import argparse
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import time

LOGIN_PROMPT = "Reply with exactly: OK"
URL_RE = re.compile(rb"https?://[^\s\"'<>]+")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--agy", default="agy",
                   help="Path to the agy binary (default: resolve from PATH).")
    p.add_argument("--code-file", default="",
                   help="File to poll for the authorization code. "
                        "When empty, the code is read from stdin.")
    p.add_argument("--url-file", default="",
                   help="Write the OAuth URL to this file as well as stdout.")
    p.add_argument("--timeout", type=int, default=280,
                   help="Give up after N seconds (default: 280).")
    return p.parse_args()


def resolve_agy(explicit: str) -> str:
    if os.path.isabs(explicit) and os.access(explicit, os.X_OK):
        return explicit
    found = shutil.which(explicit)
    if found:
        return found
    sys.exit(f"agy not found ({explicit!r}). Install it from https://antigravity.google/cli")


def emit_url(url: str, url_file: str) -> None:
    print(f"LOGIN_URL={url}", flush=True)
    print("\nOpen the URL above in a browser, approve with your Google "
          "account, and paste the code back.", flush=True)
    if url_file:
        with open(url_file, "w") as f:
            f.write(url)


def read_code(code_file: str) -> str:
    if code_file:
        try:
            with open(code_file) as f:
                return f.read().strip()
        except OSError:
            return ""
    return ""


def drive(agy: str, code_file: str, url_file: str, timeout: int) -> int:
    stdin_code = ""
    if not code_file:
        print("Paste the authorization code and press Enter:", flush=True)
        stdin_code = sys.stdin.readline().strip()

    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(agy, [agy, "-p", LOGIN_PROMPT, "--print-timeout", "5m"])

    buf = b""
    url: str | None = None
    code_sent = False
    deadline = time.time() + timeout
    with os.fdopen(fd, "rb", buffering=0) as pipe:
        while time.time() < deadline:
            ready, _, _ = select.select([pipe], [], [], 0.5)
            if ready:
                try:
                    chunk = pipe.read(65536)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if url is None:
                    m = URL_RE.search(buf)
                    if m and b"google" in m.group(0).lower():
                        url = m.group(0).decode()
                        emit_url(url, url_file)
            # Poll for the code on every tick — not only when agy speaks —
            # because agy is silent during its 60-second wait.
            if url is not None and not code_sent:
                code = stdin_code or (read_code(code_file) if code_file else "")
                if code:
                    os.write(pipe.fileno(), (code + "\n").encode())
                    code_sent = True
            if code_sent and b"OK" in buf[-200:]:
                break
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass

    if not code_sent:
        print("error: no authorization code arrived in time.", file=sys.stderr)
        return 1
    if b"OK" not in buf:
        tail = buf[-300:].decode(errors="ignore")
        print(f"error: agy did not confirm sign-in. tail: {tail}", file=sys.stderr)
        return 1
    return 0


def verify(agy: str) -> int:
    try:
        res = subprocess.run([agy, "models"], capture_output=True, text=True,
                             timeout=45, stdin=subprocess.DEVNULL, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        print(f"error: could not verify session: {exc}", file=sys.stderr)
        return 1
    models = [ln.split()[0] for ln in res.stdout.splitlines()
              if ln.strip() and "fetching" not in ln.lower()]
    if res.returncode == 0 and models:
        print(f"\nSigned in. {len(models)} models available.")
        return 0
    err = (res.stderr or res.stdout).strip().splitlines()
    print(f"error: sign-in did not complete ({err[-1] if err else 'no models'}).",
          file=sys.stderr)
    return 1


def main() -> int:
    args = parse_args()
    agy = resolve_agy(args.agy)
    if drive(agy, args.code_file, args.url_file, args.timeout) != 0:
        return 1
    return verify(agy)


if __name__ == "__main__":
    sys.exit(main())
